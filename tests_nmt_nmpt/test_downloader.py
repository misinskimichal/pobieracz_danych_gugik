import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np  # noqa: E402
from osgeo import gdal  # noqa: E402
from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransformContext,  # noqa: E402
                       QgsFeature, QgsGeometry, QgsProject, QgsRectangle, QgsVectorLayer, QgsVectorLayerFeatureSource)
from nmt_nmpt_downloader.core import (  # noqa: E402
    Tile, SOURCES, build_buffers, inspect_raster, parse_description, plan_tiles, save_geotiff, ServiceError)
from nmt_nmpt_downloader.engine import Engine  # noqa: E402

APP = QgsApplication([], False)
APP.initQgis()
gdal.DontUseExceptions()
CONTEXT = QgsCoordinateTransformContext()


def tearDownModule():
    # In standalone PyQGIS the application owns the task manager and provider registry.
    # Clean it up while Python is still alive, after deferred QObject deletion.
    from qgis.PyQt.QtCore import QCoreApplication, QEvent
    APP.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QgsProject.instance().clear()
    APP.exitQgis()


def layer_for(rectangles):
    layer = QgsVectorLayer('Polygon?crs=EPSG:2180', 'działki', 'memory')
    features = []
    for rect in rectangles:
        feature = QgsFeature()
        feature.setGeometry(QgsGeometry.fromRect(QgsRectangle(*rect)))
        features.append(feature)
    layer.dataProvider().addFeatures(features)
    return layer


def options(root, **kwargs):
    result = dict(resources=['NMT', 'NMPT'], height='PL-EVRF2007-NH', resolution=1,
                  radius=0, pixels=8, workers=2, reuse=True, feature_ids=None,
                  folders={'NMT': str(root / 'NMT'), 'NMPT': str(root / 'NMPT')}, report_folder=str(root / 'reports'))
    result.update(kwargs)
    return result


def asc(tile, nodata=False):
    values = np.full((tile.pixels, tile.pixels), 123.45)
    if nodata:
        values[0, 0] = -9999
    return (f'ncols {tile.pixels}\nnrows {tile.pixels}\nxllcorner {tile.bbox[0]}\n'
            f'yllcorner {tile.bbox[1]}\ncellsize {tile.resolution}\nNODATA_value -9999\n'
            + '\n'.join(' '.join(str(v) for v in row) for row in values) + '\n').encode()


def description(coverage):
    return f'''<CoverageDescription xmlns="http://www.opengis.net/wcs" xmlns:gml="http://www.opengis.net/gml">
<CoverageOffering><name>{coverage}</name><domainSet><spatialDomain><gml:Envelope srsName="EPSG:2180">
<gml:pos>0 0</gml:pos><gml:pos>1000000 1000000</gml:pos></gml:Envelope>
<gml:RectifiedGrid><gml:offsetVector>1 0</gml:offsetVector><gml:offsetVector>0 -1</gml:offsetVector></gml:RectifiedGrid>
</spatialDomain></domainSet><supportedFormats><formats>image/x-aaigrid</formats></supportedFormats>
</CoverageOffering></CoverageDescription>'''.encode()


class Handler(BaseHTTPRequestHandler):
    counts = Counter()
    active = 0
    peak = 0
    lock = threading.Lock()
    block = False
    started = threading.Event()
    release = threading.Event()
    mode = ''
    resolutions = {}

    def log_message(self, *args):
        pass

    def do_GET(self):
        p = {k.upper(): v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        coverage = p['COVERAGE']
        if p['REQUEST'] == 'DescribeCoverage':
            content = description(coverage)
            if coverage in self.resolutions:
                native = self.resolutions[coverage]
                content = content.replace(b'<gml:offsetVector>1 0', f'<gml:offsetVector>{native} 0'.encode())
                content = content.replace(b'<gml:offsetVector>0 -1', f'<gml:offsetVector>0 -{native}'.encode())
            status = 200
        else:
            resource = 'NMT' if coverage.startswith('DTM') else 'NMPT'
            bbox = list(map(float, p['BBOX'].split(',')))
            res = float(p['RESX'])
            pixels = round((bbox[2] - bbox[0]) / res)
            tile = Tile(resource, 'PL-EVRF2007-NH', res, round(bbox[0] / (pixels * res)),
                        round(bbox[1] / (pixels * res)), pixels)
            key = resource, tile.x
            with self.lock:
                self.counts[key] += 1
                count = self.counts[key]
                type(self).active += 1
                type(self).peak = max(type(self).peak, self.active)
            if self.block:
                self.started.set()
                self.release.wait(5)
            else:
                self.release.wait(0.04)
            status = 503 if key == ('NMT', 0) and count == 1 else 404 if key == ('NMPT', 1) else 200
            content = asc(tile, nodata=(key == ('NMT', 1))) if status == 200 else b'not available'
            if self.mode == 'empty':
                status = 200
                content = asc(tile).replace(b'123.45', b'-9999')
            elif self.mode == 'height_fallback':
                status = 200
                content = asc(tile).replace(b'123.45', b'-9999') if 'EVRF2007' in coverage else asc(tile)
            elif self.mode == 'xml':
                status = 200
                content = b'<ServiceExceptionReport><ServiceException>Invalid coverage</ServiceException></ServiceExceptionReport>'
            with self.lock:
                type(self).active -= 1
        self.send_response(status)
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            pass


class DownloaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        Handler.counts.clear()
        Handler.active = Handler.peak = 0
        Handler.block = False
        Handler.mode = ''
        Handler.resolutions = {}
        Handler.started.clear()
        Handler.release.clear()
        base = f'http://127.0.0.1:{self.server.server_port}'
        self.patcher = patch.dict(SOURCES, {'NMT': (base + '/NMT', 'DTM'), 'NMPT': (base + '/NMPT', 'DSM')})
        self.patcher.start()

    def tearDown(self):
        Handler.release.set()
        self.patcher.stop()
        self.tmp.cleanup()

    def engine(self, opts=None, rects=None):
        layer = layer_for(rects or [(0, 0, 16, 8)])
        return Engine(QgsVectorLayerFeatureSource(layer), layer.crs(), CONTEXT, opts or options(self.root))

    def test_overlapping_buffers_deduplicate_and_disjoint_do_not_fill_gap(self):
        geometries = [QgsGeometry.fromRect(QgsRectangle(0, 0, 8, 8)),
                      QgsGeometry.fromRect(QgsRectangle(0, 0, 16, 8)),
                      QgsGeometry.fromRect(QgsRectangle(800, 800, 808, 808))]
        tiles = plan_tiles(geometries, ['NMT', 'NMPT'], 'PL-EVRF2007-NH', {'NMT': 1, 'NMPT': 1},
                           8, threading.Event())
        self.assertEqual(len(tiles), 6)
        self.assertEqual(len({t.name for t in tiles}), 6)

    def test_real_metric_buffer_and_selected_features(self):
        layer = layer_for([(637000, 486000, 637100, 486100), (100, 100, 200, 200)])
        selected = [next(layer.getFeatures()).id()]
        buffers, issues = build_buffers(QgsVectorLayerFeatureSource(layer), layer.crs(), CONTEXT, selected,
                                        20000, threading.Event(), lambda _: None)
        self.assertEqual(issues, [])
        self.assertEqual(len(buffers), 1)
        self.assertAlmostEqual(buffers[0].boundingBox().width(), 40100)

    def test_geographic_point_layer_transforms_before_metric_buffer(self):
        layer = QgsVectorLayer('Point?crs=EPSG:4326', 'GPS', 'memory')
        feature = QgsFeature()
        feature.setGeometry(QgsGeometry.fromWkt('POINT (21 52)'))
        layer.dataProvider().addFeatures([feature])
        buffers, issues = build_buffers(QgsVectorLayerFeatureSource(layer), layer.crs(), CONTEXT, None,
                                        20000, threading.Event(), lambda _: None)
        self.assertEqual(issues, [])
        self.assertAlmostEqual(buffers[0].boundingBox().width(), 40000)
        self.assertGreater(buffers[0].boundingBox().xMinimum(), 500000)

    def test_description_and_wrong_orthoimagery_error(self):
        result = parse_description(description('DTM_PL-EVRF2007-NH'), 'DTM_PL-EVRF2007-NH')
        self.assertEqual(result['native_resolution'], 1)
        with self.assertRaises(ServiceError):
            parse_description(b'<ServiceExceptionReport><ServiceException>Coverage Orthoimagery not found</ServiceException></ServiceExceptionReport>', 'DTM_PL-EVRF2007-NH')

    def test_float_heights_nodata_mask_and_wrong_cache_signature(self):
        tile = Tile('NMT', 'PL-EVRF2007-NH', 1, 0, 0, 8)
        source, target = self.root / 'test.asc', self.root / 'test.tif'
        source.write_bytes(asc(tile, True))
        aoi = QgsGeometry.fromRect(QgsRectangle(*tile.bbox))
        stats, mask = inspect_raster(source, tile, aoi)
        self.assertEqual(stats['nodata_cells'], 1)
        self.assertEqual(mask.sum(), 1)
        save_geotiff(source, target, tile)
        ds = gdal.Open(str(target))
        self.assertEqual(ds.GetRasterBand(1).DataType, gdal.GDT_Float32)
        self.assertAlmostEqual(float(ds.ReadAsArray()[1, 1]), 123.45, places=3)
        ds = None
        inspect_raster(target, tile, aoi, True)
        with self.assertRaises(ValueError):
            inspect_raster(target, Tile('NMPT', tile.height, 1, 0, 0, 8), aoi, True)
        # The one missing pixel outside the AOI must not count as a missing requested pixel.
        stats, _ = inspect_raster(source, tile, QgsGeometry.fromRect(QgsRectangle(0, 0, 8, 4)))
        self.assertEqual(stats['nodata_cells'], 0)
        self.assertEqual(stats['requested_cells'], 32)

    def test_end_to_end_retry_missing_continue_reports_and_reuse(self):
        result = self.engine().run()
        self.assertEqual(result['state'], 'completed_with_gaps', result)
        self.assertEqual(result['planned_tiles'], 4)
        self.assertEqual(result['counts'], {'downloaded': 2, 'partial': 1, 'failed': 1})
        self.assertEqual(Handler.counts[('NMT', 0)], 2)
        self.assertGreaterEqual(Handler.peak, 2)
        report = Path(result['report_dir'])
        self.assertTrue((report / 'report.md').exists())
        self.assertEqual(len(json.loads((report / 'obszary_problemowe.geojson').read_text())['features']), 2)
        self.assertEqual(len(list((report / 'masks').glob('*.tif'))), 1)
        actual = gdal.Open(str(next((self.root / 'NMT').glob('*.tif'))))
        self.assertEqual(actual.GetProjection().find('2180') >= 0, True)
        actual = None
        self.assertFalse(list(self.root.rglob('*.lock')))
        self.assertFalse(list(self.root.rglob('*.part')))
        before = Handler.counts.copy()
        second = self.engine().run()
        self.assertEqual(second['counts'], {'reused': 2, 'partial': 1, 'failed': 1})
        for key in [('NMT', 0), ('NMT', 1), ('NMPT', 0)]:
            self.assertEqual(Handler.counts[key], before[key])

    def test_cancellation_preserves_diagnostics_and_releases_folder_locks(self):
        Handler.block = True
        engine = self.engine()
        thread = threading.Thread(target=engine.run)
        thread.start()
        self.assertTrue(Handler.started.wait(5))
        engine.cancel_event.set()
        Handler.release.set()
        thread.join(8)
        self.assertFalse(thread.is_alive())
        self.assertEqual(engine.report['state'], 'canceled')
        self.assertTrue((engine.report_dir / 'report.json').exists())
        self.assertFalse(list(self.root.rglob('*.lock')))
        self.assertFalse(list(self.root.rglob('*.part')))

    def test_existing_unknown_file_is_not_overwritten(self):
        opts = options(self.root, resources=['NMT'])
        folder = Path(opts['folders']['NMT'])
        folder.mkdir()
        target = folder / Tile('NMT', 'PL-EVRF2007-NH', 1, 0, 0, 8).name
        target.write_bytes(b'user file')
        result = self.engine(opts, [(0, 0, 8, 8)]).run()
        self.assertEqual(result['counts'], {'failed': 1})
        self.assertEqual(target.read_bytes(), b'user file')

    def test_dialog_instantiates_and_validates_resource_folders(self):
        from qgis.PyQt.QtWidgets import QMainWindow
        from nmt_nmpt_downloader.plugin import DownloadDialog
        window = QMainWindow()
        layer = layer_for([(0, 0, 8, 8)])
        QgsProject.instance().addMapLayer(layer)

        class Iface:
            def mainWindow(self): return window
            def activeLayer(self): return layer
        dialog = DownloadDialog(Iface())
        self.assertFalse(dialog.nmt.isChecked())
        self.assertTrue(dialog.nmpt.isChecked())
        dialog.nmt.setChecked(True)
        dialog.layer.setLayer(layer)
        dialog.nmt_folder.edit.setText(str(self.root / 'same'))
        dialog.nmpt_folder.edit.setText(str(self.root / 'same'))
        dialog.report_folder.edit.setText(str(self.root / 'reports'))
        with self.assertRaises(ValueError):
            dialog.options()
        dialog.nmpt_folder.edit.setText(str(self.root / 'NMPT'))
        _, opts = dialog.options()
        self.assertEqual(opts['radius'], 20000)
        self.assertEqual(opts['resources'], ['NMT', 'NMPT'])
        dialog.deleteLater()
        QgsProject.instance().removeMapLayer(layer.id())

    def test_all_nodata_reported_without_saving_empty_model(self):
        Handler.mode = 'empty'
        result = self.engine(options(self.root, resources=['NMT']), [(0, 0, 8, 8)]).run()
        self.assertEqual(result['state'], 'completed_with_gaps')
        self.assertEqual(result['counts'], {'missing': 1})
        self.assertEqual(result['tiles'][0]['nodata_cells'], 64)
        self.assertFalse(list((self.root / 'NMT').glob('*.tif')))
        self.assertTrue(Path(result['tiles'][0]['gap_mask']).exists())

    def test_http_200_wcs_exception_is_failed_not_saved_as_raster(self):
        Handler.mode = 'xml'
        result = self.engine(options(self.root, resources=['NMT']), [(0, 0, 8, 8)]).run()
        self.assertEqual(result['counts'], {'failed': 1})
        self.assertIn('Invalid coverage', result['tiles'][0]['reason'])
        self.assertFalse(list((self.root / 'NMT').glob('*.tif')))

    def test_qgis_task_executes_on_background_thread_and_emits_completion(self):
        from qgis.PyQt.QtCore import QEventLoop, QTimer
        from nmt_nmpt_downloader.plugin import DownloadTask
        layer = layer_for([(0, 0, 8, 8)])
        task = DownloadTask(QgsVectorLayerFeatureSource(layer), layer.crs(), CONTEXT, options(self.root))
        loop = QEventLoop()
        results, stats = [], []
        task.stats.connect(stats.append)

        def completed(result):
            results.append(result)
            loop.quit()
        task.completed.connect(completed)
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        timeout.start(12000)
        QgsApplication.taskManager().addTask(task)
        loop.exec()
        timeout.stop()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['state'], 'completed')
        self.assertEqual(results[0]['counts'], {'downloaded': 2})
        self.assertTrue(stats)

    def test_resolution_closest_and_strict_mode(self):
        from nmt_nmpt_downloader.catalog import Variant, choose_variants
        variants = [Variant('NMT', 'PL-EVRF2007-NH', value, 'https://example.org', 'DTM') for value in (1, 5)]
        self.assertEqual(choose_variants(variants, 4, 'PL-EVRF2007-NH')[0].resolution, 5)
        self.assertEqual(choose_variants(variants, 2, 'PL-EVRF2007-NH')[0].resolution, 1)
        with self.assertRaises(ServiceError):
            choose_variants(variants, 2, 'PL-EVRF2007-NH', strict=True)

    def test_independent_resource_resolutions_heights_and_rejection(self):
        settings = {'NMT': dict(resolution=5, height='PL-KRON86-NH', strict_resolution=False, alternate_height=False),
                    'NMPT': dict(resolution=0.5, height='PL-EVRF2007-NH', strict_resolution=True, alternate_height=False)}
        Handler.resolutions = {'DSM_PL-EVRF2007-NH': 0.5}
        result = self.engine(options(self.root, resource_settings=settings), [(0, 0, 8, 8)]).run()
        self.assertEqual(result['resolutions_m'], {'NMT': 1, 'NMPT': 0.5})
        self.assertTrue(all(t['height'] == 'PL-KRON86-NH' for t in result['tiles'] if t['resource'] == 'NMT'))
        self.assertTrue(all(t['resolution_m'] == 0.5 for t in result['tiles'] if t['resource'] == 'NMPT'))
        settings['NMT']['strict_resolution'] = True
        second = self.engine(options(self.root, resources=['NMT'], resource_settings=settings), [(0, 0, 8, 8)]).run()
        self.assertEqual(second['counts'], {'failed': 1})

    def test_height_fallback_keeps_actual_height_and_aligned_extent(self):
        Handler.mode = 'height_fallback'
        Handler.resolutions = {'DTM_PL-KRON86-NH': 5}
        settings = {'NMT': dict(resolution=1, height='PL-EVRF2007-NH', strict_resolution=False, alternate_height=True)}
        result = self.engine(options(self.root, resources=['NMT'], resource_settings=settings), [(0, 0, 8, 8)]).run()
        self.assertEqual(result['state'], 'completed', result)
        record = result['tiles'][0]
        self.assertEqual(record['height'], 'PL-KRON86-NH')
        self.assertEqual(record['resolution_m'], 5)
        self.assertTrue(record['fallback_used'])
        self.assertEqual(len(record['alternatives']), 2)
        self.assertEqual(record['alternatives'][0]['bbox_2180'], record['bbox_2180'])
        self.assertIn('KRON86', record['file'])

    def wait_until(self, predicate, timeout_ms=7000):
        from qgis.PyQt.QtCore import QEventLoop, QTimer
        loop = QEventLoop()
        timer, timeout = QTimer(), QTimer()
        timer.setInterval(20)
        timer.timeout.connect(lambda: loop.quit() if predicate() else None)
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        timer.start()
        timeout.start(timeout_ms)
        loop.exec()
        timer.stop()
        timeout.stop()
        self.assertTrue(predicate())

    def index_raster(self, folder, x=0, name=None):
        tile = Tile('NMT', 'PL-EVRF2007-NH', 1, x, 0, 8)
        source = self.root / 'index_source.asc'
        source.write_bytes(asc(tile))
        folder.mkdir(exist_ok=True)
        target = folder / (name or tile.name)
        save_geotiff(source, target, tile)
        return target

    def test_folder_index_tracks_add_delete_modify_and_loads_rasters(self):
        from nmt_nmpt_downloader.coverage import CoverageManager
        from qgis.core import QgsRasterLayer
        folder = self.root / 'NMT'
        first = self.index_raster(folder)
        manager = CoverageManager()
        try:
            layer = manager.ensure(str(folder), 'NMT')
            self.wait_until(lambda: layer.featureCount() == 1)
            feat = next(layer.getFeatures())
            self.assertEqual(feat['uklad_wys'], 'PL-EVRF2007-NH')
            self.assertEqual(feat.geometry().boundingBox().xMinimum(), 0)
            second = self.index_raster(folder, 1)
            self.wait_until(lambda: layer.featureCount() == 2)
            self.index_raster(folder, 2, first.name)
            self.wait_until(lambda: min(f.geometry().boundingBox().xMinimum() for f in layer.getFeatures()) == 8)
            second.unlink()
            self.wait_until(lambda: layer.featureCount() == 1)
            report = {'tiles': [dict(resource='NMT', file=str(first), status='downloaded')]}
            manager.show_results(report)
            self.wait_until(lambda: any(isinstance(item, QgsRasterLayer) for item in QgsProject.instance().mapLayers().values()))
            before = len(QgsProject.instance().mapLayers())
            manager.show_results(report)
            APP.processEvents()
            self.assertEqual(len(QgsProject.instance().mapLayers()), before)
        finally:
            manager.stop()
            QgsProject.instance().clear()

    def test_index_survives_project_save_and_restores_sync(self):
        from nmt_nmpt_downloader.coverage import CoverageManager
        folder = self.root / 'NMT'
        raster = self.index_raster(folder)
        manager = CoverageManager()
        project = QgsProject.instance()
        try:
            layer = manager.ensure(str(folder), 'NMT')
            self.wait_until(lambda: layer.featureCount() == 1)
            self.assertTrue(project.write(str(self.root / 'test.qgz')))
        finally:
            manager.stop()
        project.clear()
        self.assertTrue(project.read(str(self.root / 'test.qgz')))
        restored = next(iter(project.mapLayers().values()))
        self.assertEqual(restored.featureCount(), 1)
        new_manager = CoverageManager()
        try:
            raster.unlink()
            self.wait_until(lambda: restored.featureCount() == 0)
        finally:
            new_manager.stop()
            project.clear()

    def test_gui_download_then_show_map_and_automatic_indexes(self):
        from qgis.PyQt.QtWidgets import QMainWindow
        from qgis.gui import QgsMapCanvas
        from qgis.core import QgsRasterLayer
        from nmt_nmpt_downloader.coverage import CoverageManager
        from nmt_nmpt_downloader.plugin import DownloadDialog
        window, canvas = QMainWindow(), QgsMapCanvas()
        canvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:2180'))
        layer = layer_for([(0, 0, 8, 8)])
        QgsProject.instance().addMapLayer(layer)

        class Iface:
            def mainWindow(self): return window
            def activeLayer(self): return layer
            def mapCanvas(self): return canvas

        manager = CoverageManager(Iface())
        dialog = DownloadDialog(Iface(), manager)
        original_radius = dialog.radius.value()
        try:
            dialog.nmt.setChecked(True)
            dialog.radius.setValue(0)
            dialog.nmt_folder.edit.setText(str(self.root / 'NMT'))
            dialog.nmpt_folder.edit.setText(str(self.root / 'NMPT'))
            dialog.report_folder.edit.setText(str(self.root / 'reports'))
            dialog.pixels.addItem('8 px test', 8)
            dialog.pixels.setCurrentIndex(dialog.pixels.count() - 1)
            for control in dialog.resource_controls.values():
                control.select_resolution(1)
            with patch('nmt_nmpt_downloader.plugin.QMessageBox.information'), patch('nmt_nmpt_downloader.plugin.QMessageBox.warning'):
                dialog.start()
                self.wait_until(lambda: dialog.task is None and dialog.last_report is not None)
                self.assertEqual(dialog.last_report['state'], 'completed')
                self.assertTrue(dialog.map_button.isEnabled())
                self.wait_until(lambda: len(manager.entries) == 2 and all(e['layer'].featureCount() == 1 for e in manager.entries.values()))
                dialog.map_button.click()
                self.wait_until(lambda: sum(isinstance(item, QgsRasterLayer) for item in QgsProject.instance().mapLayers().values()) == 2)
                self.assertGreaterEqual(canvas.extent().xMaximum(), 8)
        finally:
            dialog.settings.setValue('nmt_nmpt/radius', original_radius)
            manager.stop()
            QgsProject.instance().clear()
            dialog.deleteLater()
            canvas.deleteLater()

    def test_visibility_automatic_native_download_and_cache_reuse(self):
        from nmt_nmpt_downloader.visibility import VisibilityEngine
        Handler.resolutions = {'DSM_PL-EVRF2007-NH': 0.5, 'DSM_PL-KRON86-NH': 0.5, 'DTM_PL-EVRF2007-NH': 5}

        def point(x, y):
            layer = QgsVectorLayer('Point?crs=EPSG:2180', 'test', 'memory')
            feature = QgsFeature()
            feature.setGeometry(QgsGeometry.fromWkt(f'POINT ({x} {y})'))
            layer.dataProvider().addFeatures([feature])
            return layer

        turbine, receiver = point(102.25, 100.25), point(100.25, 100.25)
        config = dict(radius=20000, eye=1.7, hub=20, diameter=0, target='hub', use_nmpt=True,
                      detail_mode='full', detail_radius=1000, detail_centers='both',
                      height='PL-EVRF2007-NH', curvature=False, auto_download=True, workers=2, pixels=8,
                      folders={r: str(self.root / r) for r in ('NMT', 'NMPT')}, report_folder=str(self.root / 'reports'))

        def run():
            return VisibilityEngine(QgsVectorLayerFeatureSource(turbine), turbine.crs(),
                                    QgsVectorLayerFeatureSource(receiver), receiver.crs(), CONTEXT, config).run()

        first = run()
        self.assertEqual(first['state'], 'completed', first)
        self.assertEqual(first['counts'], {'visible_modeled': 1})
        self.assertTrue(all(r['resolution'] == 0.5 for r in first['rasters']['NMPT']))
        self.assertTrue(all(r['resolution'] == 5 for r in first['rasters']['NMT']))
        self.assertEqual(len(first['downloads']), 2)
        previous = Handler.counts.copy()
        second = run()
        self.assertEqual(second['counts'], {'visible_modeled': 1})
        self.assertEqual(Handler.counts, previous, 'Drugi przebieg nie powinien pobierać ponownie poprawnych kafli')

    def test_circular_atlas_downloads_ground_and_surface_without_receivers(self):
        from nmt_nmpt_downloader.atlas import AtlasEngine
        Handler.resolutions = {'DSM_PL-EVRF2007-NH': 0.5}
        layer = QgsVectorLayer('Point?crs=EPSG:2180', 'turbina', 'memory')
        feature = QgsFeature()
        feature.setGeometry(QgsGeometry.fromWkt('POINT (100.25 100.25)'))
        layer.dataProvider().addFeatures([feature])
        opts = dict(models=[dict(resource='NMPT', radius=2, resolution=1, height='PL-EVRF2007-NH')],
                    source_settings={r: dict(resolution=0, height='PL-EVRF2007-NH', strict_resolution=False,
                                             alternate_height=False) for r in ['NMT', 'NMPT']},
                    folders={r: str(self.root / r) for r in ['NMT', 'NMPT']},
                    report_folder=str(self.root / 'reports'), pixels=8, workers=2,
                    auto_download=True, eye=1.7, hub=120, diameter=160, curvature=False)
        report = AtlasEngine(QgsVectorLayerFeatureSource(layer), layer.crs(), CONTEXT, opts).run()
        self.assertEqual(report['state'], 'completed', report.get('fatal_error'))
        self.assertEqual([d['resource'] for d in report['downloads']], ['NMT', 'NMPT'])
        self.assertEqual(report['products'][0]['summary']['unknown_cells'], 0)


class VisibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.event = threading.Event()
        self.config = dict(radius=20000, eye=1.7, hub=20, diameter=0, target='hub',
                           detail_mode='full', detail_centers='both', detail_radius=5,
                           use_nmpt=True, height='PL-EVRF2007-NH', curvature=False,
                           refraction=1 / 7, tolerance=0.25, auto_download=False,
                           folders={r: str(self.root / r) for r in ('NMT', 'NMPT')},
                           report_folder=str(self.root / 'reports'))
        self.receiver = dict(id='r1', x=1.25, y=2.25, representative=False)
        self.turbine = dict(id='t1', x=39.25, y=2.25, hub=20, diameter=0, representative=False)
        self.raster('NMT', np.zeros((4, 40)), 1)
        self.raster('NMPT', np.zeros((8, 80)), 0.5)
        self.stores = []

    def tearDown(self):
        for store in self.stores:
            store.close()
        QgsProject.instance().clear()
        self.tmp.cleanup()

    def raster(self, resource, values, resolution, height='PL-EVRF2007-NH', name='test.tif', origin=(0, 4)):
        from osgeo import osr
        folder = self.root / resource
        folder.mkdir(exist_ok=True)
        path = folder / name
        ds = gdal.GetDriverByName('GTiff').Create(str(path), values.shape[1], values.shape[0], 1, gdal.GDT_Float32)
        ds.SetGeoTransform((origin[0], resolution, 0, origin[1], 0, -resolution))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(2180)
        ds.SetProjection(srs.ExportToWkt())
        ds.SetMetadataItem('RESOURCE', resource)
        ds.SetMetadataItem('HEIGHT_SYSTEM', height)
        band = ds.GetRasterBand(1)
        band.SetNoDataValue(-9999)
        band.WriteArray(values)
        ds = None
        return path

    def store(self, resource):
        from nmt_nmpt_downloader.visibility import RasterStore
        store = RasterStore(self.config['folders'][resource], resource, self.config['height'], self.event)
        self.stores.append(store)
        return store

    def analyze(self):
        from nmt_nmpt_downloader.visibility import analyze_pair
        return analyze_pair(self.receiver, self.turbine, self.store('NMT'), self.store('NMPT'), self.config, self.event)

    def test_nmpt_tree_half_meter_wide_blocks_with_flat_terrain(self):
        values = np.zeros((8, 80))
        values[:, 20] = 15
        self.raster('NMPT', values, 0.5)
        result = self.analyze()
        self.assertEqual(result['status'], 'blocked_detail')
        self.assertAlmostEqual(result['detail_valid_percent'], 100)
        self.assertTrue(8 < result['blocker_distance_m'] < 10)
        self.assertLess(result['clearance_m'], -1)

    def test_local_detail_does_not_confirm_unchecked_middle(self):
        values = np.zeros((8, 80))
        values[:, 20] = 15  # Outside the two 5 m detail intervals.
        self.raster('NMPT', values, 0.5)
        self.config.update(detail_mode='local', detail_radius=5)
        result = self.analyze()
        self.assertEqual(result['status'], 'potential_visible_partial_detail')
        self.assertAlmostEqual(result['detail_required_percent'], 100 * 10 / 38)
        self.config['detail_mode'] = 'full'
        self.assertEqual(self.analyze()['status'], 'blocked_detail')

    def test_local_detail_near_observer_detects_tree(self):
        values = np.zeros((8, 80))
        values[:, 5] = 10
        self.raster('NMPT', values, 0.5)
        self.config.update(detail_mode='local', detail_centers='receivers')
        self.assertEqual(self.analyze()['status'], 'blocked_detail')

    def test_full_valid_model_and_terrain_only_have_distinct_statuses(self):
        self.assertEqual(self.analyze()['status'], 'visible_modeled')
        self.config['use_nmpt'] = False
        result = self.analyze()
        self.assertEqual(result['status'], 'visible_terrain_only')
        self.assertEqual(result['detail_required_percent'], 0)

    def test_top_of_rotor_and_hub_are_different_targets(self):
        values = np.zeros((8, 80))
        values[:, 40] = 15
        self.raster('NMPT', values, 0.5)
        self.turbine['diameter'] = 80
        self.assertEqual(self.analyze()['status'], 'blocked_detail')
        self.config['target'] = 'tip'
        self.assertEqual(self.analyze()['status'], 'visible_modeled')

    def test_missing_nmpt_is_unknown_not_zero_and_local_omission_is_different(self):
        values = np.zeros((8, 80))
        values[:, 20:25] = -9999
        self.raster('NMPT', values, 0.5)
        result = self.analyze()
        self.assertEqual(result['status'], 'unknown_required_data')
        self.assertLess(result['detail_valid_percent'], 100)
        self.config.update(detail_mode='local')
        self.assertEqual(self.analyze()['status'], 'potential_visible_partial_detail')

    def test_known_terrain_block_can_prove_occlusion_despite_nmpt_gap(self):
        values = np.zeros((4, 40))
        values[:, 10] = 40
        self.raster('NMT', values, 1)
        self.raster('NMPT', np.full((8, 80), -9999), 0.5)
        result = self.analyze()
        self.assertEqual(result['status'], 'blocked_terrain')
        self.assertTrue(result['missing_elsewhere'])

    def test_mixed_vertical_datums_are_rejected(self):
        self.raster('NMPT', np.zeros((8, 80)), 0.5, height='PL-KRON86-NH')
        detail = self.store('NMPT')
        self.assertEqual(len(detail.records), 0)
        self.assertIn('PL-KRON86-NH', detail.errors[0]['reason'])
        self.assertEqual(self.analyze()['status'], 'unknown_required_data')

    def test_eye_inside_roof_is_uncertain_and_ground_is_nmt(self):
        values = np.zeros((8, 80))
        values[:, 2] = 10
        self.raster('NMPT', values, 0.5)
        result = self.analyze()
        self.assertEqual(result['status'], 'uncertain_geometry')
        self.assertAlmostEqual(result['eye_z_m'], 1.7)

    def test_no_ground_at_endpoint_is_unknown_even_with_dsm(self):
        self.raster('NMT', np.full((4, 40), -9999), 1)
        self.assertEqual(self.analyze()['status'], 'unknown_required_data')

    def test_outside_radius_does_not_require_dem(self):
        self.config['radius'] = 10
        self.assertEqual(self.analyze()['status'], 'outside_analysis')

    def test_window_cache_bound_and_finer_valid_overlap(self):
        coarse = np.full((4, 40), 3)
        self.raster('NMPT', coarse, 1, name='coarse.tif')
        store = self.store('NMPT')
        values, _ = store.sample(np.array([1.25, 10.25]), np.array([2.25, 2.25]))
        np.testing.assert_array_equal(values, [0, 0])
        self.assertLessEqual(len(store.blocks), 32)

    def test_ray_on_grid_edge_checks_both_adjacent_columns(self):
        self.raster('NMT', np.zeros((40, 4)), 1, origin=(0, 40))
        detail = np.zeros((80, 8))
        detail[50, 3] = 20  # Left of x=2; a floor(x/res) sampler alone would miss it.
        self.raster('NMPT', detail, 0.5, origin=(0, 40))
        self.receiver.update(x=2, y=1.25)
        self.turbine.update(x=2, y=39.25)
        self.assertEqual(self.analyze()['status'], 'blocked_detail')

    def test_block_cache_evicts_when_scanning_larger_local_raster(self):
        self.raster('NMPT', np.zeros((1800, 1800)), 0.5, origin=(0, 900))
        store = self.store('NMPT')
        x, y = np.meshgrid(np.arange(1, 1800, 256) * 0.5, 900 - np.arange(1, 1800, 256) * 0.5)
        values, _ = store.sample(x.ravel(), y.ravel())
        self.assertTrue(np.isfinite(values).all())
        self.assertEqual(len(store.blocks), 32)
        self.assertLessEqual(len(store.datasets), 8)

    def test_curvature_can_hide_distant_target_on_flat_models(self):
        self.raster('NMT', np.zeros((1, 200)), 100, origin=(0, 100))
        self.raster('NMPT', np.zeros((1, 200)), 100, origin=(0, 100))
        self.receiver.update(x=0.5, y=50)
        self.turbine.update(x=19999.5, y=50, hub=1.7)
        self.config['eye'] = 1.7
        self.assertEqual(self.analyze()['status'], 'visible_modeled')
        self.config['curvature'] = True
        self.assertEqual(self.analyze()['status'], 'blocked_terrain')

    def point_layer(self, point, name):
        from qgis.core import QgsPointXY
        layer = QgsVectorLayer('Point?crs=EPSG:2180', name, 'memory')
        feature = QgsFeature()
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(point['x'], point['y'])))
        layer.dataProvider().addFeatures([feature])
        return layer

    def engine(self, **kwargs):
        from nmt_nmpt_downloader.visibility import VisibilityEngine
        turbines = self.point_layer(self.turbine, 'turbiny')
        receivers = self.point_layer(self.receiver, 'obserwatorzy')
        return VisibilityEngine(QgsVectorLayerFeatureSource(turbines), turbines.crs(),
                                QgsVectorLayerFeatureSource(receivers), receivers.crs(), CONTEXT,
                                dict(self.config, **kwargs))

    def test_task_engine_writes_gpkg_csv_json_md_and_polygon_point(self):
        from nmt_nmpt_downloader.visibility import read_points
        from nmt_nmpt_downloader.visibility_dialog import add_results
        polygon = layer_for([(0, 0, 3, 3)])
        points, issues = read_points(QgsVectorLayerFeatureSource(polygon), polygon.crs(), CONTEXT,
                                     'receivers', self.config, self.event)
        self.assertEqual(len(points), 1)
        self.assertTrue(points[0]['representative'])
        self.assertFalse(issues)
        result = self.engine().run()
        self.assertEqual(result['state'], 'completed', result)
        self.assertEqual(result['counts'], {'visible_modeled': 1})
        folder = Path(result['report_dir'])
        self.assertTrue(all((folder / p).is_file() for p in ['widocznosc.gpkg', 'wyniki.csv', 'report.json', 'report.md', 'events.jsonl']))
        self.assertEqual(json.loads((folder / 'report.json').read_text())['counts'], result['counts'])
        lines = QgsVectorLayer(result['gpkg'] + '|layername=linie_widzenia', 'test', 'ogr')
        self.assertTrue(lines.isValid())
        self.assertEqual(lines.featureCount(), 1)
        self.assertEqual(next(lines.getFeatures())['status'], 'visible_modeled')
        add_results(result)
        add_results(result)
        self.assertEqual(len(QgsProject.instance().mapLayers()), 3)

    def test_cancel_retains_report_without_faking_complete_results(self):
        engine = self.engine()
        engine.cancel_event.set()
        result = engine.run()
        self.assertEqual(result['state'], 'canceled')
        self.assertFalse(result['results'])
        self.assertTrue((Path(result['report_dir']) / 'report.json').is_file())

    def test_error_on_one_line_does_not_stop_other_pairs(self):
        from nmt_nmpt_downloader.visibility import VisibilityEngine, analyze_pair
        turbines = self.point_layer(self.turbine, 'turbiny')
        receivers = self.point_layer(self.receiver, 'obserwatorzy')
        feature = next(receivers.getFeatures())
        receivers.dataProvider().addFeatures([feature])
        engine = VisibilityEngine(QgsVectorLayerFeatureSource(turbines), turbines.crs(),
                                  QgsVectorLayerFeatureSource(receivers), receivers.crs(), CONTEXT, self.config)
        calls = []

        def fail_first(*args):
            calls.append(1)
            if len(calls) == 1:
                raise ValueError('kontrolowany błąd linii')
            return analyze_pair(*args)

        with patch('nmt_nmpt_downloader.visibility.analyze_pair', side_effect=fail_first):
            report = engine.run()
        self.assertEqual(report['state'], 'completed_with_gaps')
        self.assertEqual(report['counts'], {'unknown_required_data': 1, 'visible_modeled': 1})
        self.assertIn('kontrolowany błąd', report['results'][0]['reason'])

    def test_old_plugin_roundoff_is_normalized(self):
        path = self.root / 'NMPT' / 'test.tif'
        ds = gdal.Open(str(path), gdal.GA_Update)
        ds.SetGeoTransform((0.00000015, 0.500000000016, 0, 3.9999993, 0, -0.500000000016))
        ds.SetMetadataItem('REQUEST_SIGNATURE', 'old-plugin-request')
        ds.SetMetadataItem('NATIVE_RESOLUTION', '0.5')
        ds = None
        store = self.store('NMPT')
        self.assertEqual(store.records[0]['gt'], (0, 0.5, 0, 4, 0, -0.5))
        self.assertNotEqual(store.records[0]['source_gt'], store.records[0]['gt'])
        self.assertEqual(self.analyze()['status'], 'visible_modeled')

    def test_gui_async_nmpt_default_and_add_results(self):
        from qgis.PyQt.QtWidgets import QMainWindow
        from nmt_nmpt_downloader.visibility_dialog import VisibilityDialog
        turbines = self.point_layer(self.turbine, 'turbiny')
        receivers = self.point_layer(self.receiver, 'obserwatorzy')
        project = QgsProject.instance()
        project.addMapLayer(turbines)
        project.addMapLayer(receivers)
        window = QMainWindow()

        class Iface:
            def mainWindow(self): return window
            def activeLayer(self): return receivers

        dialog = VisibilityDialog(Iface())
        try:
            self.assertTrue(dialog.use_nmpt.isChecked())
            dialog.turbines.setLayer(turbines)
            dialog.receivers.setLayer(receivers)
            dialog.detail_mode.setCurrentIndex(1)
            dialog.hub.setValue(20)
            dialog.diameter.setValue(0)
            dialog.auto_download.setChecked(False)
            dialog.nmt_folder.edit.setText(self.config['folders']['NMT'])
            dialog.nmpt_folder.edit.setText(self.config['folders']['NMPT'])
            dialog.report_folder.edit.setText(self.config['report_folder'])
            with patch('nmt_nmpt_downloader.visibility_dialog.QMessageBox.information'), patch('nmt_nmpt_downloader.visibility_dialog.QMessageBox.warning'):
                dialog.start()
                DownloaderTests.wait_until(self, lambda: dialog.task is None and dialog.last_report is not None)
            self.assertEqual(dialog.last_report['state'], 'completed')
            self.assertTrue(dialog.map_button.isEnabled())
            dialog.map_button.click()
            self.assertEqual(len(project.mapLayers()), 5)
        finally:
            dialog.deleteLater()


class AtlasTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.event = threading.Event()
        self.config = dict(radius=100, eye=1.7, hub=20, diameter=20, hub_field='', diameter_field='',
                           models=[dict(resource='NMT', radius=80, resolution=2, height='PL-EVRF2007-NH'),
                                   dict(resource='NMPT', radius=60, resolution=1, height='PL-EVRF2007-NH')],
                           source_settings={r: dict(resolution=0, height='PL-EVRF2007-NH', strict_resolution=False,
                                                    alternate_height=False) for r in ['NMT', 'NMPT']},
                           folders={r: str(self.root / r) for r in ['NMT', 'NMPT']},
                           report_folder=str(self.root / 'reports'), auto_download=False, curvature=False)
        for resource in ['NMT', 'NMPT']:
            VisibilityTests.raster(self, resource, np.full((201, 201), 100.0), 1, origin=(0, 201))
        self.layer = QgsVectorLayer('Point?crs=EPSG:2180', 'turbiny', 'memory')
        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromWkt('POINT (80.5 100.5)'))
        self.layer.dataProvider().addFeatures([feat])

    def tearDown(self):
        QgsProject.instance().clear()
        self.tmp.cleanup()

    def engine(self, contexts=None):
        from nmt_nmpt_downloader.atlas import AtlasEngine
        return AtlasEngine(QgsVectorLayerFeatureSource(self.layer), self.layer.crs(), CONTEXT,
                           self.config, contexts)

    def test_circle_without_observers_independent_model_ranges_and_steps(self):
        report = self.engine().run()
        self.assertEqual(report['state'], 'completed', report.get('fatal_error'))
        self.assertEqual(len(report['products']), 2)
        for product in report['products']:
            ds = gdal.Open(product['paths']['count'])
            data = ds.ReadAsArray()
            self.assertTrue((data == 65535).any(), 'Corners outside a circle must remain NoData')
            self.assertEqual(int(data[data != 65535].max()), 1)
            self.assertEqual(ds.GetGeoTransform()[1], product['resolution'])
            self.assertLess(abs(product['summary']['area_km2'] - np.pi * product['radius']**2 / 1e6), 0.002)
            ds = None
        self.assertTrue(Path(report['gpkg']).is_file())
        self.assertEqual(report['context_summary'], [])
        self.assertTrue((Path(report['report_dir']) / 'events.jsonl').is_file())

    def test_overlapping_circles_count_multiple_turbines(self):
        feature = QgsFeature()
        feature.setGeometry(QgsGeometry.fromWkt('POINT (120.5 100.5)'))
        self.layer.dataProvider().addFeatures([feature])
        report = self.engine().run()
        self.assertEqual(report['state'], 'completed', report.get('fatal_error'))
        data = gdal.Open(report['products'][1]['paths']['count']).ReadAsArray()
        self.assertEqual(int(data[data != 65535].max()), 2)

    def test_all_missing_surface_preserves_nmt_and_marks_nmpt_unknown(self):
        VisibilityTests.raster(self, 'NMPT', np.full((201, 201), -9999), 1, origin=(0, 201))
        report = self.engine().run()
        self.assertEqual(report['state'], 'completed_with_gaps', report.get('fatal_error'))
        self.assertEqual(report['products'][0]['state'], 'completed')
        self.assertGreater(report['products'][1]['summary']['unknown_cells'], 0)

    def test_preflight_rejects_oversized_grid_before_network(self):
        self.config['models'][0].update(radius=20000, resolution=0.5)
        self.config['auto_download'] = True
        with patch('nmt_nmpt_downloader.atlas.AtlasEngine.download') as download:
            report = self.engine().run()
            download.assert_not_called()
        self.assertEqual(report['state'], 'failed')
        self.assertIn('krok', report['fatal_error'])

    def test_cancel_preserves_diagnostic_report(self):
        engine = self.engine()
        engine.cancel_event.set()
        report = engine.run()
        self.assertEqual(report['state'], 'canceled')
        self.assertTrue((Path(report['report_dir']) / 'report.json').is_file())

    def test_error_for_one_circle_does_not_stop_next_model(self):
        from nmt_nmpt_downloader.atlas import circular_viewshed
        calls = []

        def fail_first(*args):
            calls.append(1)
            if len(calls) == 1:
                raise ValueError('kontrolowany błąd koła')
            return circular_viewshed(*args)

        with patch('nmt_nmpt_downloader.atlas.circular_viewshed', side_effect=fail_first):
            report = self.engine().run()
        self.assertEqual(report['state'], 'completed_with_gaps', report.get('fatal_error'))
        self.assertEqual(len(report['products']), 2)
        self.assertEqual(report['products'][1]['state'], 'completed')

    def test_coarse_cell_keeps_small_source_nodata_hole_unknown(self):
        self.config['models'][1]['resolution'] = 2
        values = np.full((201, 201), 100.0)
        values[100, 111] = -9999
        VisibilityTests.raster(self, 'NMPT', values, 1, origin=(0, 201))
        report = self.engine().run()
        ds = gdal.Open(report['products'][1]['paths']['quality'])
        gt = ds.GetGeoTransform()
        value = ds.ReadAsArray(int((111.5 - gt[0]) / gt[1]), int((100.5 - gt[3]) / gt[5]), 1, 1)[0, 0]
        self.assertEqual(value, 3)
        ds = None

    def test_below_sea_level_does_not_trigger_gdal_zero_height_clamp(self):
        for resource in ['NMT', 'NMPT']:
            VisibilityTests.raster(self, resource, np.full((201, 201), -10.0), 1, origin=(0, 201))
        report = self.engine().run()
        self.assertEqual(report['state'], 'completed', report.get('fatal_error'))
        self.assertEqual(report['products'][1]['summary']['visible_cells'], report['products'][1]['summary']['cells'])

    def test_unified_gui_background_task_exports_atlas_without_context_layers(self):
        from qgis.PyQt.QtWidgets import QMainWindow
        from qgis.gui import QgsMapCanvas
        from nmt_nmpt_downloader.workspace_dialog import WorkspaceDialog
        window, canvas = QMainWindow(), QgsMapCanvas()
        QgsProject.instance().addMapLayer(self.layer)

        class Iface:
            def mainWindow(self): return window
            def activeLayer(inner): return self.layer
            def mapCanvas(self): return canvas

        dialog = WorkspaceDialog(Iface())
        try:
            for resource, panel in dialog.panels.items():
                panel.analysis_radius.setValue(50)
                panel.step.setCurrentText('2')
                panel.folder.edit.setText(self.config['folders'][resource])
            dialog.report_folder.edit.setText(self.config['report_folder'])
            dialog.auto_download.setChecked(False)
            with patch('nmt_nmpt_downloader.workspace_dialog.QMessageBox.information'), patch('nmt_nmpt_downloader.workspace_dialog.QMessageBox.warning'):
                dialog.start()
                DownloaderTests.wait_until(self, lambda: dialog.task is None and dialog.last_report is not None, 15000)
            self.assertEqual(dialog.last_report['state'], 'completed', dialog.last_report.get('fatal_error'))
            self.assertNotIn('presentation_error', dialog.last_report)
            self.assertTrue(Path(dialog.last_report['presentation']['pdf']).is_file())
            self.assertIn('NMPT/count', dialog.atlas_layers)
        finally:
            dialog.deleteLater()
            canvas.deleteLater()

    def test_nmpt_wall_casts_shadow_and_nmt_remains_visible(self):
        values = np.full((201, 201), 100.0)
        values[:, 110:113] = 180
        VisibilityTests.raster(self, 'NMPT', values, 1, origin=(0, 201))
        report = self.engine().run()
        self.assertEqual(report['state'], 'completed', report.get('fatal_error'))
        for product in report['products']:
            ds = gdal.Open(product['paths']['count'])
            gt = ds.GetGeoTransform()
            col, row = int((130.5 - gt[0]) / gt[1]), int((100.5 - gt[3]) / gt[5])
            self.assertEqual(int(ds.GetRasterBand(1).ReadAsArray(col, row, 1, 1)[0, 0]), 1 if product['resource'] == 'NMT' else 0)
            ds = None

    def test_missing_strip_propagates_uncertainty_instead_of_false_visibility(self):
        values = np.full((201, 201), 100.0)
        values[:, 110:113] = -9999
        VisibilityTests.raster(self, 'NMPT', values, 1, origin=(0, 201))
        report = self.engine().run()
        self.assertEqual(report['state'], 'completed_with_gaps', report.get('fatal_error'))
        product = report['products'][1]
        quality = gdal.Open(product['paths']['quality'])
        gt = quality.GetGeoTransform()

        def pixel(x):
            return quality.ReadAsArray(int((x - gt[0]) / gt[1]), int((100.5 - gt[3]) / gt[5]), 1, 1)[0, 0]
        self.assertEqual(pixel(130.5), 2)
        self.assertEqual(pixel(111.5), 3)
        self.assertEqual(pixel(50.5), 1)
        quality = None

    def test_roof_is_not_a_ground_level_observation_position(self):
        values = np.full((201, 201), 100.0)
        values[95:105, 110:120] = 115
        VisibilityTests.raster(self, 'NMPT', values, 1, origin=(0, 201))
        report = self.engine().run()
        product = report['products'][1]
        quality = gdal.Open(product['paths']['quality'])
        gt = quality.GetGeoTransform()
        value = quality.ReadAsArray(int((115.5 - gt[0]) / gt[1]), int((100.5 - gt[3]) / gt[5]), 1, 1)[0, 0]
        self.assertEqual(value, 4)
        quality = None

    def test_three_height_maps_are_not_just_one_binary_answer(self):
        values = np.full((201, 201), 100.0)
        values[:, 110] = 112
        VisibilityTests.raster(self, 'NMPT', values, 1, origin=(0, 201))
        report = self.engine().run()
        product = report['products'][1]
        count = gdal.Open(product['paths']['count']).ReadAsArray()
        hub = gdal.Open(product['paths']['hub']).ReadAsArray()
        self.assertTrue(((count == 1) & (hub == 0)).any())

    def test_optional_roads_buildings_and_observers_produce_context_layers(self):
        road = QgsVectorLayer('LineString?crs=EPSG:2180', 'drogi', 'memory')
        feature = QgsFeature()
        feature.setGeometry(QgsGeometry.fromWkt('LINESTRING (40 100, 140 100)'))
        road.dataProvider().addFeatures([feature])
        building = layer_for([(60, 110, 70, 120)])
        contexts = {'drogi': (QgsVectorLayerFeatureSource(road), road.crs()),
                    'zabudowa': (QgsVectorLayerFeatureSource(building), building.crs()),
                    'obserwatorzy': (QgsVectorLayerFeatureSource(self.layer), self.layer.crs())}
        report = self.engine(contexts).run()
        self.assertEqual(report['state'], 'completed', report.get('fatal_error'))
        self.assertEqual(len(report['context_summary']), 6)
        from osgeo import ogr
        dataset = ogr.Open(report['gpkg'])
        self.assertGreaterEqual(dataset.GetLayerByName('drogi_NMPT').GetFeatureCount(), 2)
        self.assertEqual(dataset.GetLayerByName('zabudowa_NMPT').GetFeatureCount(), 1)
        self.assertEqual(dataset.GetLayerByName('obserwatorzy_NMPT').GetFeatureCount(), 1)
        dataset = None

    def test_atlas_layout_pdf_png_html_and_project_layers(self):
        from nmt_nmpt_downloader.atlas_presentation import add_atlas, export_atlas
        report = self.engine().run()
        self.assertEqual(report['state'], 'completed', report.get('fatal_error'))
        layers = add_atlas(report)
        self.assertIn('NMPT/count', layers)
        presentation = export_atlas(report, layers)
        self.assertEqual(presentation['pdf_status'], 0, presentation)
        self.assertEqual(presentation['image_status'], 0, presentation)
        self.assertEqual(len(presentation['png']), 2)
        self.assertTrue(Path(presentation['html']).is_file())
        self.assertGreater(Path(presentation['pdf']).stat().st_size, 10000)

    def test_unified_ui_observers_empty_and_one_menu_action(self):
        from qgis.PyQt.QtWidgets import QMainWindow
        from qgis.gui import QgsMapCanvas
        from nmt_nmpt_downloader.plugin import TerrainPlugin
        window = QMainWindow()
        canvas = QgsMapCanvas()
        QgsProject.instance().addMapLayer(self.layer)
        actions = []

        class Iface:
            def mainWindow(self): return window
            def activeLayer(inner): return self.layer
            def mapCanvas(self): return canvas
            def addPluginToMenu(self, menu, action): actions.append(action)
            def addToolBarIcon(self, *args): pass
            def removePluginMenu(self, *args): pass
            def removeToolBarIcon(self, *args): pass
        plugin = TerrainPlugin(Iface())
        try:
            plugin.initGui()
            plugin.open()
            self.assertEqual(len(actions), 1)
            view = plugin.dialog
            self.assertTrue(all(c.currentLayer() is None for c in view.context_layers.values()))
            for resource, panel in view.panels.items():
                panel.analysis_radius.setValue(50)
                panel.step.setCurrentText('2')
                panel.folder.edit.setText(self.config['folders'][resource])
            view.report_folder.edit.setText(self.config['report_folder'])
            layer, options, contexts = view.options()
            self.assertEqual(contexts, {})
            self.assertEqual(len(options['models']), 2)
            self.assertNotIn('receivers_ids', options)
            plugin.open_visibility()
            self.assertIs(view, plugin.dialog)
            self.assertIsNone(plugin.visibility_dialog)
        finally:
            plugin.unload()
            plugin.dialog.deleteLater()
            canvas.deleteLater()


if __name__ == '__main__':
    unittest.main()
