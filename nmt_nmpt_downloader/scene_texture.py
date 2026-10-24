"""Render visible project backgrounds asynchronously, embed texture in local HTML."""
import base64
import json
from pathlib import Path

from qgis.PyQt.QtCore import QObject, QSize, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.core import (QgsCoordinateReferenceSystem, QgsMapRendererParallelJob, QgsMapSettings,
                       QgsProject, QgsRectangle)

from .core import atomic_json


class SceneTextures(QObject):
    status = pyqtSignal(str)
    completed = pyqtSignal(object)

    def __init__(self, report, parent=None):
        super().__init__(parent)
        self.report, self.job = report, None
        self.index, self.canceled = 0, False
        project = QgsProject.instance()
        self.layers = []
        for layer in project.layerTreeRoot().layerOrder():
            node = project.layerTreeRoot().findLayer(layer.id())
            if node and node.isVisible() and not layer.customProperty('nmt_nmpt/atlas_run', '') and not layer.customProperty('nmt_nmpt/index_folder', ''):
                self.layers.append(layer)

    def start(self):
        QTimer.singleShot(0, self.next_map)

    def next_map(self):
        if self.canceled:
            self.completed.emit(dict(canceled=True))
            return
        if not self.layers:
            self.completed.emit(dict(error='Brak widocznych podkładów projektu do tekstury 3D; pozostawiono kolory wysokości.'))
            return
        details = self.report.get('details', [])
        if self.index >= len(details):
            atomic_json(Path(self.report['report_dir']) / 'report.json', self.report)
            self.completed.emit(dict(completed=True))
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
            settings.setBackgroundColor(QColor('#b6c6b0'))
            settings.setLayers(self.layers)
            self.job = QgsMapRendererParallelJob(settings)
            self.job.finished.connect(self.rendered)
            self.job.start()
        except Exception as exc:
            self.fail(exc)

    def rendered(self):
        if self.canceled:
            self.job = None
            self.completed.emit(dict(canceled=True))
            return
        try:
            errors = [e.message for e in self.job.errors()]
            if errors:
                raise ValueError('; '.join(errors))
            item = self.report['details'][self.index]
            path = Path(self.report['report_dir']) / ('tekstura_' + item['model'] + '.png')
            if not self.job.renderedImage().save(str(path), 'PNG'):
                raise ValueError('Nie można zapisać tekstury 3D')
            data = 'data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode('ascii')
            scene = Path(item['scene'])
            document = scene.read_text(encoding='utf-8')
            marker = '/*SCENE_TEXTURE*/null'
            if marker not in document:
                raise ValueError('Brak znacznika tekstury w scenie')
            scene.write_text(document.replace(marker, json.dumps(data)), encoding='utf-8')
            item['texture'] = str(path)
            item['texture_layers'] = [layer.name() for layer in self.layers]
            self.job = None
            self.index += 1
            QTimer.singleShot(0, self.next_map)
        except Exception as exc:
            self.fail(exc)

    def fail(self, exc):
        self.job = None
        self.completed.emit(dict(error=str(exc)))

    def cancel(self):
        self.canceled = True
        if self.job:
            self.job.cancelWithoutBlocking()
