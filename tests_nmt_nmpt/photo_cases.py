"""Photograph cases run in test_downloader's existing standalone QGIS application."""
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import numpy as np
from osgeo import ogr
from PIL import Image
from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPointXY, QgsProject
from qgis.PyQt.QtCore import QPoint, Qt
from qgis.PyQt.QtWidgets import QMainWindow
from qgis.gui import QgsMapCanvas, QgsMapToolPan

from nmt_nmpt_downloader.atlas import Grid, NODATA, srs2180, write_array
from nmt_nmpt_downloader.core import Canceled, atomic_json
from nmt_nmpt_downloader.photo_core import PhotoRaster, decode_photo, inspect_photo, photo_config, prepare_photo
from nmt_nmpt_downloader.photo_panel import bearing_on_grid, camera_adjustment, streetview_url


class PhotoTests(unittest.TestCase):
    def test_panel_click_selects_only_the_armed_field_and_checks_geometry_for_every_selector(self):
        from qgis.core import QgsLayerTreeModel, QgsRasterLayer, QgsVectorLayer
        from qgis.gui import QgsLayerTreeView, QgsMapLayerComboBox
        from qgis.PyQt.QtTest import QTest
        from nmt_nmpt_downloader.workspace_dialog import WorkspaceDialog
        window, tree = QMainWindow(), QgsLayerTreeView()
        tree_model = QgsLayerTreeModel(QgsProject.instance().layerTreeRoot(), tree)
        tree.setModel(tree_model)
        window.setCentralWidget(tree)
        layers = [QgsVectorLayer(kind + '?crs=EPSG:2180', kind, 'memory') for kind in ('Point', 'LineString', 'Polygon')]
        layers.append(QgsRasterLayer(str(self.root/'NMPT'/'elevation.tif'), 'Zdjęcie kontrolne'))
        QgsProject.instance().addMapLayers(layers)

        class Iface:
            def mainWindow(self): return window
            def activeLayer(self): return layers[0]
            def layerTreeView(self): return tree

        view = WorkspaceDialog(Iface())
        try:
            window.show()
            view.show()
            QgsApplication.processEvents()
            picker = view.layer_panel_picker
            self.assertEqual(set(picker.buttons), set(view.findChildren(QgsMapLayerComboBox)))
            self.assertEqual(len(picker.buttons), 8)
            self.assertTrue(view.detail_box.isCollapsed())
            self.assertTrue(view.visual_body.isHidden())
            self.assertFalse(view.details.isChecked())
            self.assertFalse(view.export_after.isChecked())
            view.detail_box.setCollapsed(False)
            view.context_box.setCollapsed(False)
            self.assertFalse(view.visual_body.isHidden())
            before = {combo: combo.currentLayer() for combo in picker.buttons}
            picker.begin(view.context_layers['drogi'])
            self.assertFalse(picker.choose(layers[0]))
            self.assertEqual(before, {combo: combo.currentLayer() for combo in picker.buttons})
            picker.finish()
            # A real layer-tree click, including a layer which is already active.
            for combo in picker.buttons:
                candidate = next(combo.layer(i) for i in range(combo.count()) if combo.layer(i) is not None)
                before = {other: other.currentLayer() for other in picker.buttons if other is not combo}
                picker.buttons[combo].click()
                self.assertFalse(view.isVisible())
                node = QgsProject.instance().layerTreeRoot().findLayer(candidate.id())
                index = tree.node2index(node)
                tree.scrollTo(index)
                QgsApplication.processEvents()
                QTest.mouseClick(tree.viewport(), Qt.LeftButton, pos=tree.visualRect(index).center())
                self.assertIsNone(picker.target)
                self.assertIs(combo.currentLayer(), candidate)
                self.assertEqual(before, {other: other.currentLayer() for other in before})
            previous = view.layer.currentLayer()
            picker.begin(view.layer)
            picker.notice.reject()
            self.assertIs(view.layer.currentLayer(), previous)
            self.assertTrue(view.isVisible())
        finally:
            view.layer_panel_picker.finish(restore=False)
            view.deleteLater()
            window.hide()

    def test_modal_visual_settings_release_the_layer_tree_during_picking(self):
        from qgis.PyQt.QtCore import QTimer
        from qgis.PyQt.QtWidgets import QApplication
        from qgis.core import QgsLayerTreeModel, QgsVectorLayer
        from qgis.gui import QgsLayerTreeView
        from nmt_nmpt_downloader.workspace_dialog import WorkspaceDialog
        window, tree = QMainWindow(), QgsLayerTreeView()
        tree_model = QgsLayerTreeModel(QgsProject.instance().layerTreeRoot(), tree)
        tree.setModel(tree_model)
        window.setCentralWidget(tree)
        points = QgsVectorLayer('Point?crs=EPSG:2180', 'drzewa', 'memory')
        QgsProject.instance().addMapLayer(points)

        class Iface:
            def mainWindow(self): return window
            def activeLayer(self): return points
            def layerTreeView(self): return tree

        view = WorkspaceDialog(Iface())
        results = []

        def pick():
            try:
                view.layer_panel_picker.begin(view.scene_layers['drzewa'])
                results.append(QApplication.activeModalWidget() is None)
                results.append(view.layer_panel_picker.choose(points))
            finally:
                view.visual_settings.accept()
        try:
            QTimer.singleShot(0, pick)
            view.visual_settings.exec()
            self.assertEqual(results, [True, True])
            self.assertIs(view.scene_layers['drzewa'].currentLayer(), points)
        finally:
            view.layer_panel_picker.finish(restore=False)
            view.deleteLater()

    def test_result_name_records_source_and_exact_warsaw_time_without_replacing_missing_history(self):
        from nmt_nmpt_downloader.analysis_identity import initialize_identity, result_title
        report = dict(options=dict(turbine_layer_name='Park <Północ>'), started_at='2026-10-26T08:07:06+00:00')
        initialize_identity(report)
        title = result_title(report)
        self.assertEqual(title, 'Widoczność · Park <Północ> · 2026-10-26 09:07:06 CET')
        created = report['created_at']
        initialize_identity(report)
        self.assertEqual(report['created_at'], created)
        self.assertIn('14:07:06 CEST', result_title(dict(report, created_at='2026-06-20T12:07:06+00:00')))
        self.assertIn('data niezapisana', result_title({}))

    def test_street_reference_positions_the_imported_image_and_selects_the_photo_output(self):
        from nmt_nmpt_downloader.workspace_dialog import WorkspaceDialog
        from nmt_nmpt_downloader.street_reference import street_reference
        window = QMainWindow()

        class Iface:
            def mainWindow(self): return window
            def activeLayer(self): return None

        view = WorkspaceDialog(Iface())
        try:
            view.last_report = self.report
            view.photos.attach_report(self.report)
            view.photos.street_key.setText('session-only-secret')
            reference = street_reference('https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=52.23,21.01&pano=EXACT&heading=123&pitch=2&fov=75')
            view.photos.add_street_record(reference, str(self.image))
            photo = view.photos.current()
            self.assertEqual(view.visual_source.currentData(), 'photo')
            self.assertEqual(photo['fov'], 75)
            self.assertTrue(115 < photo['heading'] < 130)
            self.assertIn('pano=EXACT', streetview_url(photo, QgsProject.instance().transformContext()))
            self.assertNotIn('session-only-secret', (self.root/'report.json').read_text())
        finally:
            view.deleteLater()

    def test_named_building_and_forest_layers_are_selected_but_parcels_are_not(self):
        from nmt_nmpt_downloader.workspace_dialog import WorkspaceDialog
        from qgis.core import QgsVectorLayer
        forest = QgsVectorLayer('Polygon?crs=EPSG:2180', 'OT_PTLZ_A', 'memory')
        building = QgsVectorLayer('Polygon?crs=EPSG:2180', 'OT_BUBD_A', 'memory')
        parcels = QgsVectorLayer('Polygon?crs=EPSG:2180', 'działki', 'memory')
        QgsProject.instance().addMapLayers([forest, building, parcels])
        window = QMainWindow()

        class Iface:
            def mainWindow(self): return window
            def activeLayer(self): return None

        view = WorkspaceDialog(Iface())
        try:
            self.assertIs(view.scene_layers['lasy'].currentLayer(), forest)
            self.assertIs(view.scene_layers['budynki_3d'].currentLayer(), building)
            self.assertTrue(view.texture_layer.isEnabled())
        finally:
            view.deleteLater()

    def test_street_link_identifies_an_exact_panorama_and_rejects_a_map_link(self):
        from nmt_nmpt_downloader.street_reference import street_reference
        reference = street_reference('https://www.google.com/maps/@52.23,21.01,3a,75y,123.5h,88t/data=!3m7!1e1!3m5!1sEXACT_panorama-123!2e0')
        self.assertEqual(reference['pano'], 'EXACT_panorama-123')
        self.assertEqual(reference['heading'], 123.5)
        self.assertEqual(reference['pitch'], 2)
        self.assertIn('pano=EXACT_panorama-123', reference['url'])
        for invalid in ['https://www.google.com/maps/@52.23,21.01,12z', 'https://maps.app.goo.gl/short', 'https://example.org/maps/@52.23,21.01,3a,75y']:
            with self.assertRaises(ValueError):
                street_reference(invalid)

    def test_street_api_fetches_the_selected_frame_and_never_returns_the_key(self):
        from nmt_nmpt_downloader.street_reference import fetch_street_frame, street_reference
        reference = street_reference('https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=52.23,21.01&pano=EXACT&heading=123&pitch=2&fov=75')
        calls = []
        metadata = dict(status='OK', pano_id='EXACT', location=dict(lat=52.231, lng=21.011), date='2024-06', copyright='Google')
        image = self.image.read_bytes()

        class Response:
            status_code = 200
            def __init__(self, data): self.content = data
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def iter_content(self, count): return iter([self.content])

        class Session:
            def get(self, url, **kwargs):
                calls.append((url, kwargs['params']))
                return Response(json.dumps(metadata).encode() if url.endswith('/metadata') else image)

        destination = self.root/'street.jpg'
        result = fetch_street_frame(reference, 'private-test-key', destination, self.event, Session())
        self.assertEqual(destination.read_bytes(), image)
        self.assertEqual(calls[1][1]['pano'], 'EXACT')
        self.assertEqual(calls[1][1]['heading'], 123)
        self.assertNotIn('private-test-key', json.dumps(result))
        self.assertIn('EXACT', result['url'])
        self.assertEqual(result['lat'], 52.231)

    def test_one_visual_action_routes_the_selected_photo_and_model_without_duplicate_main_buttons(self):
        from nmt_nmpt_downloader.workspace_dialog import WorkspaceDialog
        window = QMainWindow()

        class Iface:
            def mainWindow(self): return window
            def activeLayer(self): return None

        record = prepare_photo(self.report, self.config, self.event)
        self.report['photo_imports'] = [record]
        view = WorkspaceDialog(Iface())
        try:
            view.last_report = self.report
            view.photos.attach_report(self.report, restore=True)
            view.visual_source.setCurrentIndex(view.visual_source.findData('photo'))
            with patch('nmt_nmpt_downloader.photo_panel.QDesktopServices.openUrl') as browser:
                view.open_visualization()
                self.assertTrue(browser.call_args.args[0].toLocalFile().endswith('/fotomontaz.html'))
            with patch.object(view, 'open_detail') as model:
                view.visual_source.setCurrentIndex(view.visual_source.findData('model'))
                view.open_visualization()
                model.assert_called_once_with('scene')
            self.assertTrue(view.photos.isHidden())
            self.assertFalse(view.visual_settings.isVisible())
            self.assertTrue(view.photos.prepare_button.parentWidget().isHidden())
            self.assertTrue(view.refresh_scene_button.isHidden())
            view.visual_source.setCurrentIndex(view.visual_source.findData('photo'))
            view.photos.save_records()
            stored = json.loads((self.root/'report.json').read_text())
            self.assertEqual(stored['scene_view_options']['scene_visual_source'], 'photo')
        finally:
            view.deleteLater()

    def test_saved_buildings_and_forest_are_retained_without_original_project_layers(self):
        from nmt_nmpt_downloader.atlas_details import write_details
        from nmt_nmpt_downloader.scene_refresh import refresh_scenes
        from qgis.core import QgsFeature, QgsGeometry, QgsVectorLayer, QgsVectorLayerFeatureSource, QgsCoordinateTransformContext
        turbine = dict(id='A', x=500250, y=500250, hub=100, diameter=120)
        model = self.report['products'][0]
        model['radius'] = 200
        self.report['turbines'] = [turbine]
        forest = QgsVectorLayer('Polygon?crs=EPSG:2180', 'PTLZ', 'memory')
        building = QgsVectorLayer('Polygon?crs=EPSG:2180', 'BUBD', 'memory')
        for layer, wkt in [(forest, 'POLYGON((500100 500115,500180 500115,500180 500125,500100 500125,500100 500115))'),
                           (building, 'POLYGON((500290 500115,500310 500115,500310 500125,500290 500125,500290 500115))')]:
            feature = QgsFeature()
            feature.setGeometry(QgsGeometry.fromWkt(wkt))
            layer.dataProvider().addFeatures([feature])
        context = QgsCoordinateTransformContext()
        options = dict(eye=1.7, curvature=False, scene_vertices=257)
        detail = write_details(self.root, model, self.grid, turbine, self.ground, np.ones(self.ground.shape, bool),
                               self.cover, np.ones(self.cover.shape, bool), 100, options, self.event,
                               {r:(QgsVectorLayerFeatureSource(l), l.crs()) for r,l in [('lasy', forest), ('budynki_3d', building)]}, context)
        self.report['details'] = [detail]
        old_path = Path(detail['scene'])
        old_text = old_path.read_text()
        old_payload = re.search(r'const scene=(.*?);\n', old_text).group(1)
        legacy = json.loads(old_payload)
        legacy.pop('building_mask', None)
        old_path.write_text(old_text.replace(old_payload, json.dumps(legacy)))
        before = hashlib.sha256((self.root/'NMPT'/'count.tif').read_bytes()).hexdigest()
        result = refresh_scenes(self.report, dict(view_turbine=1, scene_vertices=257), self.event, context, {})
        payload = json.loads(re.search(r'const scene=(.*?);\n', Path(result['details'][0]['scene']).read_text()).group(1))
        self.assertTrue(result['details'][0]['context_reused'])
        self.assertTrue(payload['trees'])
        self.assertTrue(payload['buildings'])
        self.assertTrue(any(any(row) for row in payload['building_mask']))
        self.assertTrue(any(any(row) for row in payload['forest']))
        self.assertEqual(before, hashlib.sha256((self.root/'NMPT'/'count.tif').read_bytes()).hexdigest())
        partial = refresh_scenes(result, dict(view_turbine=1, scene_vertices=257), self.event, context,
                                 {'lasy':(QgsVectorLayerFeatureSource(forest), forest.crs())})
        partial_payload = json.loads(re.search(r'const scene=(.*?);\n', Path(partial['details'][0]['scene']).read_text()).group(1))
        self.assertTrue(partial_payload['buildings'])
        cleared = refresh_scenes(partial, dict(view_turbine=1, scene_vertices=257, scene_reuse_objects=False), self.event, context, {})
        cleared_payload = json.loads(re.search(r'const scene=(.*?);\n', Path(cleared['details'][0]['scene']).read_text()).group(1))
        self.assertFalse(cleared_payload['buildings'])
        self.assertFalse(cleared_payload['trees'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.event = threading.Event()
        self.grid = Grid(500000, 500500, 1, 500, 500)
        self.ground = np.full((500, 500), 100, np.float32)
        self.cover = self.ground.copy()
        self.cover[375:385, :] = 130  # A transverse foreground obstruction.
        model = self.root / 'NMPT'
        model.mkdir()
        for name, array in [('terrain', self.ground), ('elevation', self.cover), ('count', self.ground)]:
            ds = write_array(model / (name + '.tif'), self.grid, array)
            ds = None
        self.image = self.root / 'telefon.jpg'
        Image.new('RGB', (600, 400), (80, 140, 170)).save(self.image)
        self.config = photo_config(dict(id='test_photo', name='Droga', image_path=str(self.image), x=500250.5, y=500030.5, heading=0, fov=65))
        self.report = dict(state='completed', report_dir=str(self.root), gpkg=str(self.root / 'atlas.gpkg'), details=[],
                           options=dict(models=[dict(resource='NMPT', radius=500, resolution=1, height='PL-EVRF2007-NH')],
                                        folders={}, eye=1.7, hub=100, diameter=120, curvature=False),
                           products=[dict(resource='NMPT', radius=500, resolution=1, height='PL-EVRF2007-NH',
                                          paths=dict(count=str(model / 'count.tif'), elevation=str(model / 'elevation.tif')),
                                          turbines=[dict(id='A', ground_z_m=100)])],
                           turbines=[dict(id='A', x=500250.5, y=500400.5, hub=100, diameter=120),
                                     dict(id='B', x=500340.5, y=500420.5, hub=80, diameter=90)])
        ds = ogr.GetDriverByName('GPKG').CreateDataSource(self.report['gpkg'])
        layer = ds.CreateLayer('turbiny', srs2180(), ogr.wkbPoint)
        for name, kind in [('source_id', ogr.OFTString), ('piasta_m', ogr.OFTReal), ('srednica_m', ogr.OFTReal)]:
            layer.CreateField(ogr.FieldDefn(name, kind))
        for t in self.report['turbines']:
            f = ogr.Feature(layer.GetLayerDefn())
            for name, value in [('source_id', t['id']), ('piasta_m', t['hub']), ('srednica_m', t['diameter'])]:
                f.SetField(name, value)
            point = ogr.Geometry(ogr.wkbPoint)
            point.AddPoint_2D(t['x'], t['y'])
            f.SetGeometry(point)
            layer.CreateFeature(f)
        ds, layer = None, None
        atomic_json(self.root / 'report.json', self.report)

    def tearDown(self):
        QgsProject.instance().clear()
        self.temp.cleanup()

    @staticmethod
    def payload(path):
        source = Path(path).read_text(encoding='utf-8')
        return json.loads(re.search(r'const photoScene=(.*?);</script>', source).group(1))

    def test_original_is_preserved_and_html_is_self_contained_without_changing_analysis(self):
        paths = list((self.root / 'NMPT').glob('*.tif'))
        before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
        with patch('nmt_nmpt_downloader.atlas.AtlasEngine.run') as atlas, patch('nmt_nmpt_downloader.engine.Engine.run') as downloads:
            record = prepare_photo(self.report, self.config, self.event)
        atlas.assert_not_called()
        downloads.assert_not_called()
        self.assertEqual(before, [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths])
        self.assertEqual(self.image.read_bytes(), (self.root / record['image_path']).read_bytes())
        payload = self.payload(self.root / record['html'])
        self.assertEqual(payload['camera']['z'], 101.7)
        self.assertEqual(len(payload['targets']), 2)
        self.assertTrue(payload['image'].startswith('data:image/jpeg;base64,'))
        self.assertNotIn(str(self.root), (self.root / record['html']).read_text())
        horizon = payload['targets'][0]['horizon']
        center = len(horizon['angles']) // 2
        expected = math.atan2(130 - 101.7, 84.5)
        self.assertAlmostEqual(horizon['angles'][center], expected, delta=.015)
        self.assertFalse(any(horizon['unknown']))
        self.assertLessEqual(horizon['samples_per_ray'], 8192)

    def test_exif_orientation_and_equivalent_focal_length(self):
        from nmt_nmpt_downloader.photo_core import exif_camera
        image = Image.new('RGB', (80, 40), 'red')
        exif = Image.Exif()
        exif[274] = 6
        exif[41989] = 26
        image.save(self.image, exif=exif)
        info = decode_photo(self.image, self.root / 'rotated.jpg')
        self.assertEqual((info['width'], info['height']), (40, 80))
        estimate = exif_camera(self.image, 40, 80)
        self.assertTrue(10 < estimate['fov'] < 60, estimate)
        self.assertIn('EXIF', estimate['fov_source'])
        self.assertEqual(inspect_photo(self.image)['width'], 80)

    def test_missing_surface_is_unknown_and_an_occupied_camera_disables_automatic_mask(self):
        cover = self.cover.copy()
        cover[250:260, 200:300] = NODATA
        cover[469, 250] = 125
        ds = write_array(self.root / 'NMPT' / 'elevation.tif', self.grid, cover)
        ds.FlushCache()
        ds = None
        record = prepare_photo(self.report, self.config, self.event)
        payload = self.payload(self.root / record['html'])
        self.assertTrue(payload['occupied'])
        self.assertTrue(any(payload['targets'][0]['horizon']['unknown']))
        self.assertTrue(any('Niepełne' in warning or 'niepełne' in warning for warning in record['warnings']))
        self.assertTrue(any('wyłączono' in warning for warning in record['warnings']))

    def test_outside_camera_corrupt_image_and_cancellation_keep_previous_html(self):
        record = prepare_photo(self.report, self.config, self.event)
        path = self.root / record['html']
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Brak NMT'):
            prepare_photo(self.report, dict(record, x=600000), self.event)
        self.event.set()
        with self.assertRaises(Canceled):
            prepare_photo(self.report, record, self.event)
        self.assertEqual(path.read_bytes(), before)
        bad = self.root / 'bad.jpg'
        bad.write_text('not an image')
        with self.assertRaises(ValueError):
            inspect_photo(bad)
        with self.assertRaises(ValueError):
            photo_config(dict(self.config, heading=float('nan')))
        with self.assertRaises(ValueError):
            photo_config(dict(self.config, id='../elsewhere'))

    def test_raster_nodata_and_outside_are_not_zero_and_cache_is_bounded(self):
        self.ground[20, 20] = NODATA
        ds = write_array(self.root / 'check.tif', self.grid, self.ground)
        ds.FlushCache()
        ds = None
        raster = PhotoRaster(self.root / 'check.tif')
        try:
            output = raster.sample([500020.5, 500030.5, 700000], [500479.5] * 3)
            self.assertTrue(np.isnan(output[0]))
            self.assertEqual(output[1], 100)
            self.assertTrue(np.isnan(output[2]))
            self.assertLessEqual(len(raster.cache), 64)
        finally:
            raster.close()

    def test_grid_direction_is_independent_of_project_crs_and_google_uses_true_heading(self):
        source = QgsCoordinateReferenceSystem('EPSG:3857')
        context = QgsProject.instance().transformContext()
        transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:2180'), source, context)
        start, end = QgsPointXY(500250.5, 500030.5), QgsPointXY(500350.5, 500030.5)
        x, y, direction = bearing_on_grid(transform.transform(start), transform.transform(end), source, context)
        self.assertAlmostEqual(x, start.x(), places=4)
        self.assertAlmostEqual(y, start.y(), places=4)
        self.assertAlmostEqual(direction, 90, places=5)
        params = parse_qs(urlparse(streetview_url(dict(self.config, heading=90), context)).query)
        self.assertEqual(params['map_action'], ['pano'])
        self.assertNotIn('key', params)
        self.assertTrue(85 < float(params['heading'][0]) < 95)
        lat, lon = map(float, params['viewpoint'][0].split(','))
        self.assertTrue(45 < lat < 60 and 10 < lon < 30)

    def test_adjustment_round_trip_and_rejection_of_another_photo_or_bad_mask(self):
        record = prepare_photo(self.report, self.config, self.event)
        data = dict(photo_id=record['id'], source_sha256=record['source_sha256'], heading=12, fov=55, pitch=-2, roll=1,
                    yaw=90, phase=25, opacity=.8, mask_strokes=[dict(mode='hide', radius=.02, points=[[.2, .3], [.4, .5]])])
        adjusted = camera_adjustment(record, data)
        self.assertEqual(adjusted['mask_strokes'], data['mask_strokes'])
        self.assertEqual(adjusted['fov'], 55)
        self.assertFalse(adjusted['fov_pending'])
        with self.assertRaises(ValueError):
            camera_adjustment(record, dict(data, photo_id='another'))
        with self.assertRaises(ValueError):
            camera_adjustment(record, dict(data, source_sha256='changed'))
        with self.assertRaises(ValueError):
            camera_adjustment(record, dict(data, mask_strokes=[dict(mode='hide', radius=.1, points=[[float('nan'), .4]])]))

    def test_explicit_model_keeps_its_own_height_datum(self):
        nmt = self.root / 'NMT'
        nmt.mkdir()
        for name in ['terrain', 'count']:
            ds = write_array(nmt / (name + '.tif'), self.grid, self.ground + 100)
            ds.FlushCache()
            ds = None
        self.report['products'].append(dict(resource='NMT', radius=500, resolution=1, height='PL-KRON86-NH', paths=dict(count=str(nmt / 'count.tif'))))
        record = prepare_photo(self.report, dict(self.config, resource='NMT'), self.event)
        payload = self.payload(self.root / record['html'])
        self.assertEqual(payload['camera']['z'], 201.7)
        self.assertEqual(payload['targets'][0]['ground'], 200)
        self.assertEqual(record['height_datum'], 'PL-KRON86-NH')

    def test_qgis_drag_file_import_async_prepare_report_reload_and_persistent_layers(self):
        from nmt_nmpt_downloader.workspace_dialog import WorkspaceDialog
        window, canvas = QMainWindow(), QgsMapCanvas()
        canvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:3857'))
        pan = QgsMapToolPan(canvas)
        canvas.setMapTool(pan)

        class Iface:
            def mainWindow(self): return window
            def activeLayer(self): return None
            def mapCanvas(self): return canvas

        class MapEvent:
            def __init__(self, point, pos): self.point, self.position = point, pos
            def button(self): return Qt.LeftButton
            def mapPoint(self): return self.point
            def pos(self): return self.position

        view = WorkspaceDialog(Iface())
        try:
            with patch('nmt_nmpt_downloader.workspace_dialog.QMessageBox.warning') as warning, \
                    patch('nmt_nmpt_downloader.photo_panel.QDesktopServices.openUrl') as browser, \
                    patch('nmt_nmpt_downloader.photo_panel.QFileDialog.getOpenFileName', return_value=(str(self.image), '')):
                view.load_report(self.root / 'report.json')
                self.assertFalse(warning.called, warning.call_args)
                transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:2180'), canvas.mapSettings().destinationCrs(), QgsProject.instance().transformContext())
                a, b = transform.transform(QgsPointXY(500250.5, 500030.5)), transform.transform(QgsPointXY(500250.5, 500100.5))
                view.photos.pick()
                self.assertIs(canvas.mapTool(), view.photos.tool)
                tool = view.photos.tool
                tool.canvasPressEvent(MapEvent(a, QPoint(100, 200)))
                tool.canvasMoveEvent(MapEvent(b, QPoint(100, 100)))
                tool.canvasReleaseEvent(MapEvent(b, QPoint(100, 100)))
                self.assertIs(canvas.mapTool(), pan)
                self.assertEqual(len(view.photos.records), 1)
                self.assertAlmostEqual(view.photos.records[0]['heading'], 0, places=5)
                self.assertEqual(view.photos.layers['punkty'].featureCount(), 1)
                self.assertEqual(view.photos.layers['kierunki'].featureCount(), 1)
                with patch('nmt_nmpt_downloader.atlas.AtlasEngine.run') as analysis, patch('nmt_nmpt_downloader.engine.Engine.run') as downloads:
                    view.photos.prepare()
                    end = time.monotonic() + 15
                    while view.task is not None and time.monotonic() < end:
                        QgsApplication.processEvents()
                        time.sleep(.01)
                    self.assertIsNone(view.task)
                    analysis.assert_not_called()
                    downloads.assert_not_called()
                self.assertFalse(warning.called, warning.call_args)
                browser.assert_called_once()
                photo = view.photos.records[0]
                self.assertTrue((self.root / photo['html']).is_file())
                stored = json.loads((self.root / 'report.json').read_text())
                self.assertEqual(stored['photo_imports'][0]['source_sha256'], photo['source_sha256'])
                self.assertEqual(view.photos.layers['punkty'].providerType(), 'ogr')
                action = view.photos.layers['punkty'].actions().actions()[0]
                self.assertIn('Feature', action.actionScopes())
                self.assertIn('fotomontaz.html', (self.root / 'atlas.html').read_text())
                project_file = self.root / 'photos.qgz'
                self.assertTrue(QgsProject.instance().write(str(project_file)))
                QgsProject.instance().clear()
                self.assertTrue(QgsProject.instance().read(str(project_file)))
                view.load_report(self.root / 'report.json')
                self.assertFalse(warning.called, warning.call_args)
                self.assertEqual(len(view.photos.records), 1)
                self.assertEqual(view.photos.current()['id'], photo['id'])
                self.assertEqual(view.photos.layers['punkty'].featureCount(), 1)
                adjustment = self.root / 'dopasowanie.json'
                atomic_json(adjustment, dict(photo_id=photo['id'], heading=5, pitch=-1, roll=2, fov=50))
                view.photos.import_adjustment(adjustment)
                self.assertEqual(view.photos.controls['fov'].value(), 50)
                view.photos.pick(replace=True)
                view.photos.stop_picker()
                self.assertIs(canvas.mapTool(), pan)
                self.assertEqual(len(view.photos.records), 1)
        finally:
            view.photos.stop_picker(show=False)
            view.deleteLater()
            canvas.deleteLater()

    def test_pending_camera_and_direction_are_visible_then_saved_as_persistent_layers(self):
        from nmt_nmpt_downloader.workspace_dialog import WorkspaceDialog
        window = QMainWindow()

        class Iface:
            def mainWindow(self): return window
            def activeLayer(self): return None

        view = WorkspaceDialog(Iface())
        try:
            view.photos.records = [self.config]
            view.photos.refresh_list()
            view.photos.save_records()
            pending = list(view.photos.pending_layers.values())
            self.assertEqual(len(pending), 2)
            self.assertTrue(all(QgsProject.instance().mapLayer(i).featureCount() == 1 for i in pending))
            view.photos.attach_report(self.report)
            view.photos.sync_layers()
            self.assertFalse(view.photos.pending_layers)
            self.assertTrue(all(QgsProject.instance().mapLayer(i) is None for i in pending))
            self.assertEqual(view.photos.layers['punkty'].providerType(), 'ogr')
            view.photos.controls['heading'].setValue(90)
            line = next(view.photos.layers['kierunki'].getFeatures()).geometry().asPolyline()
            self.assertAlmostEqual(line[-1].x() - line[0].x(), 80)
            self.assertAlmostEqual(line[-1].y() - line[0].y(), 0)
            view.photos.remove()
            self.assertFalse(json.loads((self.root / 'zdjecia_punkty.geojson').read_text())['features'])
        finally:
            view.deleteLater()

    def test_two_clicks_and_escape_cancel_restore_the_previous_map_tool(self):
        from qgis.PyQt.QtCore import QEvent
        from qgis.PyQt.QtGui import QKeyEvent
        from nmt_nmpt_downloader.workspace_dialog import WorkspaceDialog
        window, canvas = QMainWindow(), QgsMapCanvas()
        canvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:2180'))
        pan = QgsMapToolPan(canvas)
        canvas.setMapTool(pan)

        class Iface:
            def mainWindow(self): return window
            def activeLayer(self): return None
            def mapCanvas(self): return canvas

        class MapEvent:
            def __init__(self, point, pos): self.point, self.position = point, pos
            def button(self): return Qt.LeftButton
            def mapPoint(self): return self.point
            def pos(self): return self.position

        view = WorkspaceDialog(Iface())
        try:
            view.photos.pick()
            view.photos.tool.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
            self.assertIs(canvas.mapTool(), pan)
            self.assertIsNone(view.photos.tool)
            with patch('nmt_nmpt_downloader.photo_panel.QFileDialog.getOpenFileName', return_value=('', '')):
                view.photos.pick()
                tool = view.photos.tool
                a = MapEvent(QgsPointXY(500250, 500030), QPoint(100, 200))
                b = MapEvent(QgsPointXY(500250, 500100), QPoint(100, 100))
                tool.canvasPressEvent(a)
                tool.canvasReleaseEvent(a)
                self.assertIs(view.photos.tool, tool)
                tool.canvasPressEvent(b)
                tool.canvasReleaseEvent(b)
                self.assertIsNone(view.photos.tool)
                self.assertIs(canvas.mapTool(), pan)
                self.assertFalse(view.photos.records)
        finally:
            view.photos.stop_picker(show=False)
            view.deleteLater()
            canvas.deleteLater()

    def test_new_atlas_preserves_the_previous_photo_source_instead_of_rebasing_it_to_a_missing_file(self):
        from nmt_nmpt_downloader.workspace_dialog import WorkspaceDialog
        window = QMainWindow()

        class Iface:
            def mainWindow(self): return window
            def activeLayer(self): return None

        record = prepare_photo(self.report, self.config, self.event)
        self.report['photo_imports'] = [record]
        view = WorkspaceDialog(Iface())
        try:
            view.photos.attach_report(self.report, restore=True)
            new_report = copy.deepcopy(self.report)
            new_root = self.root / 'nowy_atlas'
            new_root.mkdir()
            new_report['report_dir'] = str(new_root)
            exported = view.photos.configs(absolute=True)[0]
            self.assertTrue(Path(exported['image_path']).is_file())
            self.assertNotIn('html', exported)
            view.photos.attach_report(new_report)
            carried = view.photos.current()
            self.assertTrue(Path(carried['image_path']).is_file())
            self.assertNotIn('html', carried)
            self.assertTrue(carried['dirty'])
            new_photo = prepare_photo(new_report, carried, self.event)
            self.assertEqual((new_root / new_photo['image_path']).read_bytes(), self.image.read_bytes())
            self.assertTrue((self.root / record['html']).is_file())
        finally:
            view.deleteLater()
