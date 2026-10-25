"""Phone photograph workflow in the shared QGIS form; the generated viewer is offline."""
import copy
import json
import math
from pathlib import Path
import threading
import time
import uuid
from urllib.parse import urlencode

from qgis.PyQt.QtCore import Qt, QUrl, QVariant, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices, QImageReader, QPixmap
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
                                 QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton,
                                 QVBoxLayout, QWidget)
from qgis.core import (QgsAction, QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsDistanceArea, QgsFeature, QgsField, QgsGeometry, QgsMarkerSymbol, QgsPointXY,
                       QgsProject, QgsProperty, QgsTask, QgsVectorLayer)

from .core import PLUGIN_NAME, atomic_json
from .photo_core import MAX_PHOTOS, inspect_photo, photo_config, prepare_photo, resolve_asset


class PhotoTask(QgsTask):
    message = pyqtSignal(str)
    completed = pyqtSignal(object)

    def __init__(self, report, config):
        super().__init__('Zdjęcie terenowe — fotomontaż turbin', QgsTask.CanCancel)
        self.report, self.config = copy.deepcopy(report), copy.deepcopy(config)
        self.event, self.result = threading.Event(), None

    def run(self):
        try:
            self.result = dict(photo=prepare_photo(self.report, self.config, self.event, self.message.emit, self.setProgress))
            return True
        except Exception as exc:
            self.result = dict(error=str(exc), canceled=self.event.is_set())
            return False

    def cancel(self):
        self.event.set()
        super().cancel()

    def finished(self, success):
        self.completed.emit(self.result or dict(error='Nie ukończono przygotowania zdjęcia'))


class StreetFrameTask(QgsTask):
    message = pyqtSignal(str)
    completed = pyqtSignal(object)

    def __init__(self, reference, key, destination):
        super().__init__('Wybrany kadr Street View · oficjalne API', QgsTask.CanCancel)
        self.reference, self.key, self.destination = reference, key, destination
        self.event, self.result = threading.Event(), None

    def run(self):
        from .street_reference import fetch_street_frame
        try:
            self.message.emit('Street View: sprawdzanie konkretnej panoramy i pobieranie kadru…')
            reference = fetch_street_frame(self.reference, self.key, self.destination, self.event)
            self.result = dict(reference=reference, filename=str(self.destination))
            return True
        except Exception as exc:
            self.result = dict(error=str(exc).replace(self.key, '[klucz]') if self.key else str(exc))
            return False
        finally:
            self.key = ''

    def cancel(self):
        self.event.set()
        super().cancel()

    def finished(self, success):
        self.completed.emit(self.result or dict(error='Anulowano pobieranie kadru'))


def bearing_on_grid(start, end, source_crs, context):
    transform = QgsCoordinateTransform(source_crs, QgsCoordinateReferenceSystem('EPSG:2180'), context)
    a, b = transform.transform(start), transform.transform(end)
    if not all(math.isfinite(v) for v in (a.x(), a.y(), b.x(), b.y())) or math.hypot(b.x() - a.x(), b.y() - a.y()) < .05:
        raise ValueError('Wskaż dwa różne miejsca: aparat i kierunek patrzenia')
    return a.x(), a.y(), math.degrees(math.atan2(b.x() - a.x(), b.y() - a.y())) % 360


def streetview_url(photo, context):
    """An explicit external link, not a Google image downloader. Convert grid to true bearing."""
    if photo.get('street_reference'):
        return photo['street_reference']['url']
    transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:2180'), QgsCoordinateReferenceSystem('EPSG:4326'), context)
    p = QgsPointXY(photo['x'], photo['y'])
    angle = math.radians(photo['heading'])
    a, b = transform.transform(p), transform.transform(QgsPointXY(p.x() + 100 * math.sin(angle), p.y() + 100 * math.cos(angle)))
    measure = QgsDistanceArea()
    measure.setSourceCrs(QgsCoordinateReferenceSystem('EPSG:4326'), context)
    measure.setEllipsoid('GRS80')
    heading = math.degrees(measure.bearing(a, b)) % 360
    return 'https://www.google.com/maps/@?' + urlencode(dict(api=1, map_action='pano', viewpoint=f'{a.y():.8f},{a.x():.8f}',
                                                             heading=f'{heading:.3f}', pitch=f'{photo["pitch"]:.2f}',
                                                             fov=f'{min(100, photo["fov"]):.2f}'))


def camera_adjustment(config, data):
    if data.get('photo_id') != config['id']:
        raise ValueError('Dopasowanie pochodzi z innego zdjęcia. Wybierz właściwe zdjęcie na liście.')
    if data.get('source_sha256') and data['source_sha256'] != config.get('source_sha256'):
        raise ValueError('Zmieniono plik zdjęcia. To dopasowanie dotyczy innego oryginału.')
    updated = copy.deepcopy(config)
    for key in ('heading', 'pitch', 'roll', 'fov'):
        updated[key] = data[key]
    for key, low, high in [('yaw', 0, 360), ('phase', 0, 360), ('opacity', 0, 1)]:
        value = float(data.get(key, 1 if key == 'opacity' else 0))
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError('Nieprawidłowe ustawienie: ' + key)
        updated[key] = value
    updated.update(mask_strokes=data.get('mask_strokes', []), fov_pending=False, fov_source='Dopasowanie użytkownika zapisane w JSON')
    return photo_config(updated)


class PhotoPanel(QGroupBox):
    def __init__(self, owner):
        super().__init__('Zdjęcie z telefonu · fotomontaż turbin', owner)
        self.owner, self.iface = owner, owner.iface
        self.records, self.report = [], None
        self.loading, self.tool, self.previous_tool, self.helper = False, None, None, None
        self.layers = {}
        self.pending_layers = {}
        form = QFormLayout(self)
        self.add_button = QPushButton('Dodaj zdjęcie na mapie · wskaż aparat i kierunek')
        self.add_button.clicked.connect(lambda: self.pick())
        form.addRow(self.add_button)
        self.street_import_button = QPushButton('Dodaj widok Street View z linku…')
        self.street_import_button.clicked.connect(self.import_street)
        form.addRow(self.street_import_button)
        note = QLabel('Przeciągnij od miejsca aparatu w kierunku kadru albo kliknij te dwa miejsca. Potem wybierz oryginalny JPG/PNG. Escape / prawy przycisk anuluje. Zwykłe zdjęcia perspektywiczne; panoramę telefonu i HEIC wyeksportuj lub zastąp zwykłym JPG.')
        note.setWordWrap(True)
        form.addRow(note)
        self.list = QComboBox()
        self.list.currentIndexChanged.connect(self.select)
        form.addRow('Zdjęcie:', self.list)
        self.name = QLineEdit()
        form.addRow('Nazwa ujęcia:', self.name)
        self.path = QLineEdit()
        self.path.setReadOnly(True)
        change = QPushButton('Zmień plik')
        change.clicked.connect(self.replace_file)
        form.addRow('Plik:', self.row(self.path, change))
        self.location = QLabel('Brak zdjęcia. Najpierw wskaż miejsce i kierunek na mapie.')
        self.location.setWordWrap(True)
        move = QPushButton('Popraw miejsce i kierunek na mapie')
        move.clicked.connect(lambda: self.pick(replace=True))
        form.addRow(self.location)
        form.addRow(move)
        self.preview = QLabel()
        self.preview.setMaximumHeight(180)
        form.addRow(self.preview)
        self.controls = {}
        for key, title, low, high, default, suffix in [
                ('heading', 'Kierunek w siatce mapy (0° N, 90° E):', 0, 359.99, 0, '°'),
                ('eye', 'Wysokość aparatu nad NMT:', .1, 1000, 1.7, ' m'),
                ('fov', 'Poziomy kąt widzenia — do dopasowania:', 10, 140, 65, '°'),
                ('pitch', 'Pochylenie (dodatnie = w górę):', -85, 85, 0, '°'),
                ('roll', 'Przechylenie zdjęcia:', -45, 45, 0, '°')]:
            spin = QDoubleSpinBox()
            spin.setDecimals(2)
            spin.setRange(low, high)
            spin.setValue(default)
            spin.setSuffix(suffix)
            self.controls[key] = spin
            form.addRow(title, spin)
            spin.valueChanged.connect(self.edited)
        self.model = QComboBox()
        self.model.addItems(['NMPT', 'NMT'])
        self.model.currentTextChanged.connect(self.edited)
        form.addRow('Model wysokości i zasłaniania:', self.model)
        self.name.textEdited.connect(self.edited)
        self.info = QLabel('Po obliczeniu lub wczytaniu atlasu przygotuj fotomontaż z zapisanych modeli. Nie wymaga ponownego pobierania ani liczenia widoczności. EXIF może podpowiedzieć kąt widzenia; kierunek bierze się z mapy.')
        self.info.setWordWrap(True)
        form.addRow(self.info)
        self.prepare_button = QPushButton('Przygotuj wizualizację na zdjęciu')
        self.prepare_button.clicked.connect(self.prepare)
        self.open_button = QPushButton('Otwórz fotomontaż')
        self.open_button.clicked.connect(self.open_photo)
        form.addRow(self.row(self.prepare_button, self.open_button))
        self.adjust_button = QPushButton('Wczytaj dopasowanie JSON zapisane w przeglądarce')
        self.adjust_button.clicked.connect(self.import_adjustment)
        form.addRow(self.adjust_button)
        self.street_button = QPushButton('Otwórz Street View w tym miejscu i kierunku · przeglądarka')
        self.street_button.clicked.connect(self.open_streetview)
        form.addRow(self.street_button)
        self.street_key = QLineEdit()
        self.street_key.setEchoMode(QLineEdit.Password)
        self.street_key.setPlaceholderText('Opcjonalny własny klucz Street View Static API · tylko bieżąca sesja')
        form.addRow('Klucz do pobrania kadru Google:', self.street_key)
        remove = QPushButton('Usuń zdjęcie z zestawu (zachowaj pliki)')
        remove.clicked.connect(self.remove)
        form.addRow(remove)
        self.update_buttons()

    @staticmethod
    def row(*widgets):
        result = QWidget()
        layout = QHBoxLayout(result)
        layout.setContentsMargins(0, 0, 0, 0)
        for widget in widgets:
            layout.addWidget(widget)
        return result

    def busy(self):
        return bool(self.owner.task or self.owner.export_job or self.owner.point_tool)

    def current(self):
        row = self.list.currentIndex()
        return self.records[row] if 0 <= row < len(self.records) else None

    def configs(self, absolute=False):
        records = [photo_config(p) for p in self.records]
        if absolute:
            root = self.report['report_dir'] if self.report else ''
            for photo in records:
                photo['image_path'] = str(resolve_asset(root, photo['image_path']).resolve())
                photo.pop('html', None)
                photo['dirty'] = True
        return records

    def edited(self, *args):
        item = self.current()
        if self.loading or item is None:
            return
        item.update(name=self.name.text(), resource=self.model.currentText(), **{k: w.value() for k, w in self.controls.items()})
        if self.sender() is self.controls['fov']:
            item.update(fov_pending=False, fov_source='Kąt widzenia ustawiony ręcznie w QGIS')
        item['dirty'] = True
        self.list.setItemText(self.list.currentIndex(), item['name'])
        self.location.setText(f'X={item["x"]:.2f}, Y={item["y"]:.2f} · EPSG:2180 · {item["heading"]:.2f}°')
        self.info.setText('Zmieniono ustawienia zdjęcia. Przygotuj wizualizację ponownie; rastry analizy pozostaną bez zmian.')
        self.save_records()
        self.update_buttons()

    def select(self, index):
        item = self.current()
        self.loading = True
        try:
            self.name.setText(item['name'] if item else '')
            root = self.report['report_dir'] if self.report else ''
            self.path.setText(str(resolve_asset(root, item['image_path'])) if item else '')
            self.path.setToolTip(self.path.text())
            self.preview.clear()
            self.preview.setMinimumHeight(0)
            if item:
                for key, widget in self.controls.items():
                    widget.setValue(item[key])
                self.model.setCurrentText(item['resource'])
                self.location.setText(f'X={item["x"]:.2f}, Y={item["y"]:.2f} · EPSG:2180 · {item["heading"]:.2f}°')
                self.info.setText('\n'.join(item.get('warnings', [])) or ('Przygotowano fotomontaż. Zmiany w przeglądarce zachowaj przez JSON.' if item.get('html') else 'Ujęcie dodane. Sprawdź wysokość aparatu i przygotuj wizualizację.'))
                source = resolve_asset(self.report['report_dir'] if self.report else '', item['image_path'])
                prepared = resolve_asset(self.report['report_dir'], item['html']).with_name('podglad.jpg') if self.report and item.get('html') else None
                if prepared and prepared.is_file() and not item.get('dirty'):
                    source = prepared
                if source.is_file():
                    reader = QImageReader(str(source))
                    reader.setAutoTransform(True)
                    size = reader.size()
                    limit = 24000000 if bytes(reader.format()).lower() in (b'jpeg', b'jpg') else 4000000
                    if 0 < size.width() * size.height() <= limit:
                        size.scale(420, 170, Qt.KeepAspectRatio)
                        reader.setScaledSize(size)
                        pixmap = QPixmap.fromImage(reader.read())
                        self.preview.setPixmap(pixmap)
                        self.preview.setMinimumHeight(min(170, pixmap.height()))
                    else:
                        self.preview.setText('Duże zdjęcie — podgląd powstanie w tle po przygotowaniu wizualizacji.')
            else:
                self.location.setText('Brak zdjęcia. Wskaż miejsce i kierunek na mapie.')
        finally:
            self.loading = False
        self.update_buttons()

    def update_buttons(self):
        current = self.current()
        ready = bool(current and self.report and any(p['resource'] == current['resource'] for p in self.report.get('products', [])))
        self.prepare_button.setEnabled(ready)
        self.open_button.setEnabled(bool(current and current.get('html') and not current.get('dirty')))
        self.street_button.setEnabled(bool(current))
        self.adjust_button.setEnabled(bool(current))
        from .visual_workflow import update_visual_workflow
        update_visual_workflow(self.owner)

    def attach_report(self, report, restore=False):
        rebased = not restore and self.report and self.report.get('report_dir') != report.get('report_dir')
        if rebased:
            # A new atlas has a new directory. Keep the actual source image, not an old relative path.
            self.records = self.configs(absolute=True)
        self.report = report
        available = {product['resource'] for product in report.get('products', [])}
        for i in range(self.model.count()):
            self.model.model().item(i).setEnabled(self.model.itemText(i) in available)
        if restore or not self.records:
            values = report.get('photo_imports', report.get('options', {}).get('photo_imports', []))
            if len(values) > MAX_PHOTOS:
                raise ValueError('Raport przekracza limit 24 zdjęć')
            self.records = [photo_config(p) for p in values]
            if len({photo['id'] for photo in self.records}) != len(self.records):
                raise ValueError('Raport zawiera powtórzone identyfikatory zdjęć')
            self.refresh_list()
        elif rebased:
            self.refresh_list(max(0, self.list.currentIndex()))
        self.update_buttons()
        if self.records:
            report['photo_imports'] = self.configs()

    def refresh_list(self, index=0):
        self.list.blockSignals(True)
        self.list.clear()
        self.list.addItems([p['name'] for p in self.records])
        self.list.setCurrentIndex(min(index, len(self.records) - 1))
        self.list.blockSignals(False)
        self.select(self.list.currentIndex())

    def pick(self, replace=False):
        if self.busy() or self.tool:
            return
        if replace and self.current() is None:
            return
        if not replace and len(self.records) >= MAX_PHOTOS:
            QMessageBox.warning(self, PLUGIN_NAME, 'Limit 24 zdjęć w jednym atlasie.')
            return
        from .photo_map_tool import PhotoDirectionTool
        canvas = self.iface.mapCanvas()
        self.replacing = replace
        self.previous_tool = canvas.mapTool()
        self.tool = PhotoDirectionTool(canvas)
        self.tool.picked.connect(self.picked)
        self.tool.canceled.connect(self.stop_picker)
        self.owner.hide()
        canvas.setMapTool(self.tool)
        self.helper = QDialog(self.iface.mainWindow(), Qt.Tool)
        self.helper.setWindowTitle('Zdjęcie — miejsce i kierunek')
        layout = QVBoxLayout(self.helper)
        label = QLabel('Przeciągnij od miejsca aparatu w kierunku zdjęcia\nalbo kliknij aparat, a następnie kierunek.\nEscape / prawy przycisk anuluje.')
        layout.addWidget(label)
        cancel = QPushButton('Anuluj i wróć')
        cancel.clicked.connect(self.stop_picker)
        layout.addWidget(cancel)
        self.helper.finished.connect(self.stop_picker)
        self.helper.show()
        self.iface.mainWindow().statusBar().showMessage('Zdjęcie: wskaż miejsce aparatu i kierunek patrzenia. Escape anuluje.')

    def stop_picker(self, *args, show=True):
        tool, self.tool = self.tool, None
        if tool:
            tool.done = True
            canvas = self.iface.mapCanvas()
            if canvas.mapTool() is tool:
                if self.previous_tool:
                    canvas.setMapTool(self.previous_tool)
                else:
                    canvas.unsetMapTool(tool)
            tool.cleanup()
            tool.deleteLater()
        self.previous_tool = None
        if self.helper:
            helper, self.helper = self.helper, None
            helper.blockSignals(True)
            helper.close()
            helper.deleteLater()
        if hasattr(self.iface, 'mapCanvas'):
            self.iface.mainWindow().statusBar().clearMessage()
        if show:
            self.owner.show()
            self.owner.raise_()

    def picked(self, start, end):
        try:
            x, y, heading = bearing_on_grid(start, end, self.iface.mapCanvas().mapSettings().destinationCrs(), QgsProject.instance().transformContext())
            replacing = self.replacing
            self.stop_picker()
            if replacing:
                self.current().update(x=x, y=y, heading=heading, dirty=True)
            else:
                path, _ = QFileDialog.getOpenFileName(self, 'Wybierz oryginalne zdjęcie z telefonu', '', 'Zdjęcia JPG / PNG (*.jpg *.jpeg *.JPG *.JPEG *.png *.PNG)')
                if not path:
                    return
                inspect_photo(path)
                self.records.append(photo_config(dict(name=Path(path).stem, x=x, y=y, heading=heading,
                                                      eye=self.owner.eye.value(), image_path=str(Path(path).resolve()),
                                                      resource='NMPT' if not self.report or any(p['resource'] == 'NMPT' for p in self.report.get('products', [])) else 'NMT',
                                                      fov_pending=True, dirty=True)))
            self.refresh_list(self.list.currentIndex() if replacing else len(self.records) - 1)
            if hasattr(self.owner, 'visual_source'):
                self.owner.visual_source.setCurrentIndex(self.owner.visual_source.findData('photo'))
            self.save_records()
        except Exception as exc:
            self.stop_picker()
            QMessageBox.warning(self, PLUGIN_NAME, str(exc))

    def replace_file(self):
        if self.current() is None or self.busy():
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Zmień zdjęcie', '', 'Zdjęcia (*.jpg *.jpeg *.png *.JPG *.JPEG *.PNG)')
        if path:
            try:
                inspect_photo(path)
                self.current().update(image_path=str(Path(path).resolve()), fov_pending=True, dirty=True, mask_strokes=[])
                self.current().pop('source_sha256', None)
                self.refresh_list(self.list.currentIndex())
                self.save_records()
            except Exception as exc:
                QMessageBox.warning(self, PLUGIN_NAME, str(exc))

    def remove(self):
        row = self.list.currentIndex()
        if row >= 0:
            self.records.pop(row)
            self.refresh_list(max(0, row - 1))
            self.save_records()

    def save_records(self):
        if not self.report:
            self.sync_pending_layers()
            return
        if self.report and not self.owner.task and not self.owner.export_job:
            self.report['photo_imports'] = self.configs()
            if hasattr(self.owner, 'visual_source'):
                self.report.setdefault('scene_view_options', {})['scene_visual_source'] = self.owner.visual_source.currentData()
            try:
                if self.report.get('products') and (self.report.get('presentation') or any(p.get('html') for p in self.records)):
                    from .atlas_presentation import make_html
                    presentation = self.report.setdefault('presentation', dict(png=[]))
                    presentation.setdefault('png', [])
                    make_html(self.report, presentation)
                atomic_json(Path(self.report['report_dir']) / 'report.json', self.report)
                self.sync_layers()
            except (OSError, RuntimeError, ValueError) as exc:
                self.owner.log.appendPlainText('Zdjęcia — zapis ustawień: ' + str(exc))

    def sync_pending_layers(self):
        """The camera is visible immediately, including before the first atlas exists."""
        project = QgsProject.instance()
        for role in ('punkty', 'kierunki'):
            layer = project.mapLayer(self.pending_layers.get(role, ''))
            if not self.records:
                if layer:
                    project.removeMapLayer(layer.id())
                continue
            if layer is None:
                geometry = 'Point' if role == 'punkty' else 'LineString'
                layer = QgsVectorLayer(geometry + '?crs=EPSG:2180', 'Zdjęcia terenowe · ' + role + ' (przed zapisem atlasu)', 'memory')
                layer.dataProvider().addAttributes([QgsField('nazwa', QVariant.String), QgsField('azymut', QVariant.Double)])
                layer.updateFields()
                project.addMapLayer(layer)
                self.pending_layers[role] = layer.id()
            provider = layer.dataProvider()
            provider.deleteFeatures([f.id() for f in layer.getFeatures()])
            features = []
            for photo in self.records:
                start = QgsPointXY(photo['x'], photo['y'])
                angle = math.radians(photo['heading'])
                end = QgsPointXY(start.x() + 80 * math.sin(angle), start.y() + 80 * math.cos(angle))
                feature = QgsFeature(layer.fields())
                feature.setAttributes([photo['name'], photo['heading']])
                feature.setGeometry(QgsGeometry.fromPointXY(start) if role == 'punkty' else QgsGeometry.fromPolylineXY([start, end]))
                features.append(feature)
            provider.addFeatures(features)
            layer.updateExtents()
            if role == 'punkty':
                symbol = QgsMarkerSymbol.createSimple(dict(name='triangle', color='#16bda5', outline_color='#ffffff', size='4'))
                symbol.setDataDefinedAngle(QgsProperty.fromField('azymut'))
                layer.renderer().setSymbol(symbol)
            layer.triggerRepaint()

    def sync_layers(self):
        if not self.report:
            self.sync_pending_layers()
            return
        for layer_id in self.pending_layers.values():
            if QgsProject.instance().mapLayer(layer_id):
                QgsProject.instance().removeMapLayer(layer_id)
        self.pending_layers = {}
        if not self.report or not self.records:
            if self.report:
                root = Path(self.report['report_dir']).resolve()
                files = {str(root / ('zdjecia_' + role + '.geojson')) for role in ('punkty', 'kierunki')}
                for layer in list(QgsProject.instance().mapLayers().values()):
                    if layer.customProperty('nmt_nmpt/photo_file', '') in files:
                        QgsProject.instance().removeMapLayer(layer.id())
                for filename in files:
                    if Path(filename).is_file():
                        atomic_json(filename, dict(type='FeatureCollection', crs=dict(type='name', properties=dict(name='EPSG:2180')), features=[]))
            self.layers = {}
            return
        root = Path(self.report['report_dir']).resolve()
        for role in ('punkty', 'kierunki'):
            filename = root / ('zdjecia_' + role + '.geojson')
            existing = [layer for layer in QgsProject.instance().mapLayers().values()
                        if layer.customProperty('nmt_nmpt/photo_file', '') == str(filename)]
            for layer in existing:
                layer.setDataSource('Point?crs=EPSG:2180' if role == 'punkty' else 'LineString?crs=EPSG:2180', layer.name(), 'memory')
            features = []
            for photo in self.records:
                angle = math.radians(photo['heading'])
                xy = [photo['x'], photo['y']]
                geometry = dict(type='Point', coordinates=xy) if role == 'punkty' else dict(type='LineString', coordinates=[xy, [xy[0] + 80 * math.sin(angle), xy[1] + 80 * math.cos(angle)]])
                target = resolve_asset(root, photo['html']).as_uri() if photo.get('html') else ''
                features.append(dict(type='Feature', geometry=geometry, properties=dict(id=photo['id'], nazwa=photo['name'], azymut=photo['heading'], oko_m=photo['eye'], plik=str(resolve_asset(root, photo['image_path'])), html=target)))
            atomic_json(filename, dict(type='FeatureCollection', crs=dict(type='name', properties=dict(name='EPSG:2180')), features=features))
            if not existing:
                layer = QgsVectorLayer(str(filename), 'Zdjęcia terenowe · ' + role, 'ogr')
                QgsProject.instance().addMapLayer(layer)
                existing = [layer]
            for layer in existing:
                layer.setDataSource(str(filename), layer.name(), 'ogr')
                layer.setCustomProperty('nmt_nmpt/photo_file', str(filename))
                if role == 'punkty':
                    symbol = QgsMarkerSymbol.createSimple(dict(name='triangle', color='#16bda5', outline_color='#ffffff', size='4'))
                    symbol.setDataDefinedAngle(QgsProperty.fromField('azymut'))
                    layer.renderer().setSymbol(symbol)
                    layer.actions().clearActions()
                    action = QgsAction(QgsAction.OpenUrl, 'Otwórz fotomontaż zdjęcia', '[% "html" %]')
                    action.setActionScopes({'Feature', 'Field'})
                    layer.actions().addAction(action)
                layer.triggerRepaint()
            self.layers[role] = existing[0]

    def prepare(self):
        if self.busy() or not self.current() or not self.report:
            return
        try:
            config = photo_config(self.current())
            task = PhotoTask(self.report, config)
            self.owner.task = task
            task.message.connect(self.owner.stage.setText)
            task.message.connect(self.owner.log.appendPlainText)
            task.completed.connect(self.prepared)
            task.progressChanged.connect(lambda value: self.owner.progress.setValue(round(value)))
            self.owner.inputs.setEnabled(False)
            self.owner.start_button.setEnabled(False)
            self.owner.load_button.setEnabled(False)
            self.owner.cancel_button.setEnabled(True)
            self.owner.progress.setRange(0, 100)
            self.owner.progress.setValue(0)
            self.owner.clock_started = time.monotonic()
            self.owner.clock.start()
            QgsApplication.taskManager().addTask(task)
        except Exception as exc:
            QMessageBox.warning(self, PLUGIN_NAME, str(exc))

    def prepared(self, result):
        self.owner.task = None
        self.owner.inputs.setEnabled(True)
        self.owner.start_button.setEnabled(True)
        self.owner.load_button.setEnabled(True)
        self.owner.cancel_button.setEnabled(False)
        self.owner.clock.stop()
        self.owner.progress.setRange(0, 100)
        if result.get('error'):
            self.owner.progress.setValue(0)
            self.owner.stage.setText('Zdjęcie: ' + ('anulowano; poprzednie pliki zachowano' if result.get('canceled') else result['error']))
            QMessageBox.warning(self, PLUGIN_NAME, self.owner.stage.text())
            return
        record = result['photo']
        record['dirty'] = False
        row = next((i for i, p in enumerate(self.records) if p['id'] == record['id']), None)
        if row is not None:
            self.records[row] = record
        self.refresh_list(row or 0)
        self.save_records()
        self.owner.progress.setValue(100)
        self.owner.stage.setText('Gotowe — fotomontaż zdjęcia przygotowany. Dopasuj kadr w przeglądarce i zapisz PNG lub JSON.')
        self.open_photo()

    def import_adjustment(self, filename=None):
        if not self.current() or self.busy():
            return
        if not isinstance(filename, (str, Path)):
            filename, _ = QFileDialog.getOpenFileName(self, 'Dopasowanie zapisane w fotomontażu', '', 'Dopasowanie JSON (*.json)')
        if not filename:
            return
        try:
            path = Path(filename)
            if path.stat().st_size > 12 * 1024 * 1024:
                raise ValueError('Plik dopasowania przekracza 12 MB')
            updated = camera_adjustment(self.current(), json.loads(path.read_text(encoding='utf-8')))
            updated['dirty'] = True
            self.records[self.list.currentIndex()] = updated
            self.refresh_list(self.list.currentIndex())
            self.save_records()
            self.info.setText('Wczytano kierunek, kąt widzenia i maskę. Przygotuj wizualizację, aby odtworzyć zapisane dopasowanie.')
        except Exception as exc:
            QMessageBox.warning(self, PLUGIN_NAME, str(exc))

    def open_photo(self):
        current = self.current()
        if current and current.get('html') and self.report:
            path = resolve_asset(self.report['report_dir'], current['html'])
            if path.is_file():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
            else:
                QMessageBox.warning(self, PLUGIN_NAME, 'Brak HTML. Przygotuj wizualizację ponownie.')

    def open_streetview(self):
        if self.current():
            QDesktopServices.openUrl(QUrl(streetview_url(self.current(), QgsProject.instance().transformContext())))

    def import_street(self):
        if self.busy() or len(self.records) >= MAX_PHOTOS:
            return
        from .street_reference import street_reference
        value, ok = QInputDialog.getText(self, 'Widok Street View', 'Wklej pełny adres wybranej panoramy z paska przeglądarki.\nLink ustawi aparat i kierunek. Bez klucza API wybierzesz plik JPG/PNG tego kadru.')
        if not ok or not value:
            return
        try:
            reference = street_reference(value)
            key = self.street_key.text().strip()
            if key:
                if not self.report:
                    raise ValueError('Najpierw wczytaj atlas, aby zapisać pobrany kadr w jego folderze')
                folder = Path(self.report['report_dir']) / 'zdjecia_terenowe'
                folder.mkdir(exist_ok=True)
                task = StreetFrameTask(reference, key, folder / ('import_' + uuid.uuid4().hex + '.jpg'))
                self.owner.task = task
                task.message.connect(self.owner.stage.setText)
                task.completed.connect(self.street_imported)
                self.owner.inputs.setEnabled(False)
                self.owner.start_button.setEnabled(False)
                self.owner.cancel_button.setEnabled(True)
                self.owner.progress.setRange(0, 0)
                self.owner.stats_label.setText('Street View Static API · kadr 640 × 480 px')
                self.owner.active.setRowCount(0)
                self.owner.clock_started = time.monotonic()
                self.owner.clock.start()
                QgsApplication.taskManager().addTask(task)
            else:
                filename, _ = QFileDialog.getOpenFileName(self, 'Wybierz plik wybranego kadru Street View (JPG/PNG)', '', 'Zdjęcia (*.jpg *.jpeg *.png *.JPG *.PNG)')
                if filename:
                    inspect_photo(filename)
                    self.add_street_record(reference, filename)
        except Exception as exc:
            QMessageBox.warning(self, PLUGIN_NAME, str(exc))

    def street_imported(self, result):
        self.owner.task = None
        self.owner.inputs.setEnabled(True)
        self.owner.start_button.setEnabled(True)
        self.owner.cancel_button.setEnabled(False)
        self.owner.clock.stop()
        self.owner.progress.setRange(0, 100)
        if result.get('error'):
            self.owner.progress.setValue(0)
            QMessageBox.warning(self, PLUGIN_NAME, result['error'])
            return
        self.owner.progress.setValue(100)
        try:
            self.add_street_record(result['reference'], result['filename'])
            self.owner.stage.setText('Dodano wybrany kadr Street View. Kliknij Utwórz fotomontaż, aby nałożyć turbiny.')
        except Exception as exc:
            QMessageBox.warning(self, PLUGIN_NAME, 'Nie można ustawić kadru: ' + str(exc))

    def add_street_record(self, reference, filename):
        context = QgsProject.instance().transformContext()
        measure = QgsDistanceArea()
        measure.setSourceCrs(QgsCoordinateReferenceSystem('EPSG:4326'), context)
        measure.setEllipsoid('GRS80')
        p = QgsPointXY(reference['lon'], reference['lat'])
        end = measure.computeSpheroidProject(p, 100, math.radians(reference['heading']))
        x, y, heading = bearing_on_grid(p, end, QgsCoordinateReferenceSystem('EPSG:4326'), context)
        self.records.append(photo_config(dict(name='Street View ' + (reference.get('date') or str(len(self.records) + 1)),
                                              image_path=str(Path(filename).resolve()), x=x, y=y, heading=heading,
                                              pitch=reference['pitch'], fov=reference['fov'], eye=2.5, fov_pending=False,
                                              street_reference=reference, fov_source='Kadr z linku Street View · sprawdź pole widzenia i wysokość kamery', dirty=True,
                                              resource='NMPT' if not self.report or any(p['resource'] == 'NMPT' for p in self.report.get('products', [])) else 'NMT')))
        self.refresh_list(len(self.records) - 1)
        if hasattr(self.owner, 'visual_source'):
            self.owner.visual_source.setCurrentIndex(self.owner.visual_source.findData('photo'))
        self.save_records()
