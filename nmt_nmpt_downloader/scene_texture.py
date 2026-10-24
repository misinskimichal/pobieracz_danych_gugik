"""Render visible project backgrounds asynchronously, embed texture in local HTML."""
import base64
import json
from pathlib import Path
import threading
import math

import numpy as np
import requests
from osgeo import gdal, osr

from qgis.PyQt.QtCore import QObject, QSize, QTimer, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QImage
from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem, QgsMapRendererParallelJob, QgsMapSettings,
                       QgsProject, QgsRectangle, QgsTask)

from .core import Canceled, atomic_json, check_cancel

ORTO_WMS = 'https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMS/StandardResolution'


def webmercator_bounds(bounds):
    source, target = osr.SpatialReference(), osr.SpatialReference()
    source.ImportFromEPSG(2180)
    target.ImportFromEPSG(3857)
    for crs in (source, target):
        crs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    transform = osr.CoordinateTransformation(source, target)
    points = []
    for f in np.linspace(0, 1, 17):
        x, y = bounds[0]+f*(bounds[2]-bounds[0]), bounds[1]+f*(bounds[3]-bounds[1])
        points.extend([transform.TransformPoint(x, bounds[1]), transform.TransformPoint(x, bounds[3]),
                       transform.TransformPoint(bounds[0], y), transform.TransformPoint(bounds[2], y)])
    # Keep the request bbox short and enclosing; warp back to the exact analysis bounds below.
    return [math.floor(min(p[0] for p in points)), math.floor(min(p[1] for p in points)),
            math.ceil(max(p[0] for p in points)), math.ceil(max(p[1] for p in points))]


def reproject_image(image, source_bounds, target_bounds, pixels):
    if image.isNull():
        raise ValueError('Geoportal nie zwrócił obrazu ortofotomapy')
    image = image.convertToFormat(QImage.Format_RGBA8888)
    data = image.constBits()
    data.setsize(image.byteCount())
    values = np.frombuffer(data, np.uint8).reshape(image.height(), image.bytesPerLine())[:, :image.width()*4].reshape(image.height(), image.width(), 4)
    source = gdal.GetDriverByName('MEM').Create('', image.width(), image.height(), 4, gdal.GDT_Byte)
    source.SetGeoTransform((source_bounds[0], (source_bounds[2]-source_bounds[0])/image.width(), 0,
                            source_bounds[3], 0, -(source_bounds[3]-source_bounds[1])/image.height()))
    crs = osr.SpatialReference()
    crs.ImportFromEPSG(3857)
    source.SetProjection(crs.ExportToWkt())
    for index, color in enumerate([gdal.GCI_RedBand, gdal.GCI_GreenBand, gdal.GCI_BlueBand, gdal.GCI_AlphaBand]):
        source.GetRasterBand(index+1).WriteArray(values[:, :, index])
        source.GetRasterBand(index+1).SetColorInterpretation(color)
    warped = gdal.Warp('', source, format='MEM', dstSRS='EPSG:2180', outputBounds=target_bounds,
                       width=pixels[0], height=pixels[1], resampleAlg='bilinear', outputType=gdal.GDT_Byte)
    if warped is None:
        raise ValueError('Nie można dopasować ortofotomapy do EPSG:2180')
    array = np.ascontiguousarray(warped.ReadAsArray().transpose(1, 2, 0))
    return QImage(array.data, array.shape[1], array.shape[0], array.strides[0], QImage.Format_RGBA8888).copy()


def texture_quality(image):
    if image.isNull():
        raise ValueError('Usługa nie zwróciła poprawnego obrazu ortofotomapy')
    sample = image.scaled(256, 256, Qt.KeepAspectRatio, Qt.FastTransformation).convertToFormat(QImage.Format_RGBA8888)
    data = sample.constBits()
    data.setsize(sample.byteCount())
    pixels = np.frombuffer(data, np.uint8).reshape(sample.height(), sample.bytesPerLine())[:, :sample.width()*4].reshape(-1, 4)
    opaque = pixels[:, 3] > 8
    coverage = float(opaque.mean())
    if coverage < .005:
        raise ValueError('Źródło zwróciło pustą/przezroczystą teksturę. Sprawdź zasięg i dostępność ortofotomapy.')
    rgb = pixels[opaque, :3].astype(np.int16)
    span = int(np.ptp(rgb, axis=0).max())
    chroma = int(np.max(np.max(rgb, axis=1) - np.min(rgb, axis=1)))
    if span <= 2 and chroma <= 8:
        raise ValueError('Źródło zwróciło jednolite szare/białe tło zamiast rozpoznawalnej ortofotomapy. Wybierz inną warstwę lub Geoportal.')
    return dict(coverage_fraction=round(coverage, 4), sampled_range=span,
                width=image.width(), height=image.height())


def embed_texture(report, item, image, sources, mode):
    info = texture_quality(image)
    path = Path(report['report_dir']) / ('tekstura_' + item['model'] + '.png')
    temporary = path.with_suffix('.tmp.png')
    if not image.save(str(temporary), 'PNG'):
        raise ValueError('Nie można zapisać tekstury ortofotomapy')
    temporary.replace(path)
    data = 'data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode('ascii')
    scene = Path(item['scene'])
    document = scene.read_text(encoding='utf-8')
    marker = '/*SCENE_TEXTURE*/null'
    if marker not in document:
        raise ValueError('Scena nie ma miejsca na nową teksturę. Odśwież samą scenę 3D i spróbuj ponownie.')
    temporary_html = scene.with_suffix('.tmp.html')
    temporary_html.write_text(document.replace(marker, json.dumps(data)), encoding='utf-8')
    temporary_html.replace(scene)
    item.update(texture=str(path), texture_layers=sources, texture_info=dict(info, mode=mode))


def ortho_candidate(project):
    candidates = []
    for layer in project.mapLayers().values():
        if layer.type() != layer.RasterLayer or not layer.isValid() or layer.customProperty('nmt_nmpt/atlas_run', ''):
            continue
        name = layer.name().lower()
        score = 10 if any(word in name for word in ['orto', 'ortho', 'satellite', 'satelit']) else 1 if layer.bandCount() >= 3 else 0
        if score:
            candidates.append((score, layer))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


class GeoportalTextureTask(QgsTask):
    status = pyqtSignal(str)
    completed = pyqtSignal(object)

    def __init__(self, report):
        super().__init__('Ortofotomapa Geoportal do sceny 3D', QgsTask.CanCancel)
        self.report, self.event, self.result = report, threading.Event(), None

    def run(self):
        try:
            with requests.Session() as session:
                for number, item in enumerate(self.report.get('details', [])):
                    check_cancel(self.event)
                    bounds = item['scene_bounds']
                    width, height = bounds[2]-bounds[0], bounds[3]-bounds[1]
                    pixels = [max(1, round(2048 * value / max(width, height))) for value in (width, height)]
                    self.status.emit(f'Geoportal: ortofotomapa {item["model"]}, {number+1}/{len(self.report["details"])}')
                    mercator = webmercator_bounds(bounds)
                    params = dict(SERVICE='WMS', REQUEST='GetMap', VERSION='1.3.0', CRS='EPSG:3857',
                                  BBOX=','.join(map(str, mercator)), WIDTH=pixels[0], HEIGHT=pixels[1],
                                  LAYERS='Raster', STYLES='', FORMAT='image/jpeg')
                    with session.get(ORTO_WMS, params=params, timeout=(10, 45), stream=True) as response:
                        response.raise_for_status()
                        data = bytearray()
                        for chunk in response.iter_content(65536):
                            check_cancel(self.event)
                            data.extend(chunk)
                            if len(data) > 32 * 1024 * 1024:
                                raise ValueError('Odpowiedź ortofotomapy przekracza 32 MB')
                    check_cancel(self.event)
                    image = reproject_image(QImage.fromData(bytes(data)), mercator, bounds, pixels)
                    embed_texture(self.report, item, image, ['Geoportal GUGiK · ORTO StandardResolution'], 'geoportal')
            atomic_json(Path(self.report['report_dir']) / 'report.json', self.report)
            self.result = dict(completed=True)
            return True
        except Canceled:
            self.result = dict(canceled=True)
        except Exception as exc:
            self.result = dict(error='Ortofotomapa Geoportal: ' + str(exc))
        return False

    def cancel(self):
        self.event.set()
        super().cancel()

    def finished(self, success):
        self.completed.emit(self.result or dict(canceled=True))


class SceneTextures(QObject):
    status = pyqtSignal(str)
    completed = pyqtSignal(object)

    def __init__(self, report, parent=None, layers=None):
        super().__init__(parent)
        self.report, self.job = report, None
        self.index, self.canceled, self.geo_task = 0, False, None
        project = QgsProject.instance()
        options = report.get('scene_view_options') or report.get('options', {})
        self.mode = options.get('scene_texture_mode', 'visible')
        self.layers, self.clones = list(layers or []), []
        if self.mode == 'layer' and layers is None:
            original = project.mapLayer(options.get('scene_texture_layer_id', ''))
            if original is not None and original.type() == original.RasterLayer:
                clone = original.clone()
                clone.setScaleBasedVisibility(False)
                clone.setOpacity(1)
                self.layers, self.clones = [clone], [clone]
        elif self.mode == 'visible' and layers is None:
            for layer in project.layerTreeRoot().layerOrder():
                node = project.layerTreeRoot().findLayer(layer.id())
                if node and node.isVisible() and not layer.customProperty('nmt_nmpt/atlas_run', '') and not layer.customProperty('nmt_nmpt/index_folder', ''):
                    self.layers.append(layer)

    def start(self):
        if self.mode == 'geoportal':
            self.geo_task = GeoportalTextureTask(self.report)
            self.geo_task.status.connect(self.status)
            self.geo_task.completed.connect(self.finish)
            QgsApplication.taskManager().addTask(self.geo_task)
        else:
            QTimer.singleShot(0, self.next_map)

    def finish(self, result):
        self.geo_task = None
        self.layers = []
        for clone in self.clones:
            clone.deleteLater()
        self.clones = []
        self.completed.emit(result)

    def next_map(self):
        if self.canceled:
            self.finish(dict(canceled=True))
            return
        if not self.layers:
            self.finish(dict(error='Nie wybrano ortofotomapy. Wskaż warstwę rastrową lub wybierz Geoportal online.'))
            return
        details = self.report.get('details', [])
        if self.index >= len(details):
            atomic_json(Path(self.report['report_dir']) / 'report.json', self.report)
            self.finish(dict(completed=True))
            return
        try:
            item = details[self.index]
            self.status.emit(f'Tekstura 3D w tle: {item["model"]}, {self.index+1}/{len(details)}')
            settings = QgsMapSettings()
            settings.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:2180'))
            extent = QgsRectangle(*item['scene_bounds'])
            width, height = extent.width(), extent.height()
            settings.setOutputSize(QSize(max(1, round(2048 * width / max(width, height))),
                                         max(1, round(2048 * height / max(width, height)))))
            settings.setExtent(extent)
            settings.setBackgroundColor(QColor(Qt.transparent))
            settings.setFlag(QgsMapSettings.RenderBlocking, True)
            settings.setLayers(self.layers)
            self.job = QgsMapRendererParallelJob(settings)
            self.job.finished.connect(self.rendered)
            self.job.start()
        except Exception as exc:
            self.fail(exc)

    def rendered(self):
        if self.canceled:
            self.job = None
            self.finish(dict(canceled=True))
            return
        try:
            errors = [e.message for e in self.job.errors()]
            if errors:
                raise ValueError('; '.join(errors))
            item = self.report['details'][self.index]
            embed_texture(self.report, item, self.job.renderedImage(), [layer.name() for layer in self.layers], self.mode)
            self.job = None
            self.index += 1
            QTimer.singleShot(0, self.next_map)
        except Exception as exc:
            self.fail(exc)

    def fail(self, exc):
        self.job = None
        self.finish(dict(error=str(exc)))

    def cancel(self):
        self.canceled = True
        if self.geo_task:
            self.geo_task.cancel()
        if self.job:
            self.job.cancelWithoutBlocking()
