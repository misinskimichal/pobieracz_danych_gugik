"""One shared workflow: data, independent circular models and optional project context."""
from pathlib import Path
import json
import time
import threading
import math

from qgis.PyQt.QtCore import QSettings, QTimer, QUrl, Qt, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QGroupBox,
    QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea,
    QSpinBox, QTableWidget, QVBoxLayout, QWidget,
)
from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsCoordinateTransformContext, QgsFieldProxyModel,
                       QgsMapLayerProxyModel, QgsProject, QgsTask, QgsVectorLayer, QgsVectorLayerFeatureSource)
from qgis.gui import QgsFieldComboBox, QgsMapLayerComboBox

from .atlas import AtlasEngine, MAX_LOCAL_CELLS
from .core import PLUGIN_NAME, VERSION
from .plugin import CatalogTask, DownloadDialog, DownloadTask, FolderChooser, ResourceControls, duration


class AtlasTask(QgsTask):
    stats = pyqtSignal(object)
    message = pyqtSignal(str)
    completed = pyqtSignal(object)

    def __init__(self, source, crs, context, options, contexts):
        super().__init__('Atlas widoczności NMT / NMPT', QgsTask.CanCancel)
        self.engine = AtlasEngine(source, crs, context, options, contexts, self.stats.emit, self.message.emit)
        self.result = None

    def run(self):
        try:
            self.result = self.engine.run()
            return self.result['state'] != 'failed'
        except Exception as exc:
            self.result = dict(state='failed', fatal_error=str(exc))
            return False

    def cancel(self):
        self.engine.cancel_event.set()
        super().cancel()

    def finished(self, success):
        self.completed.emit(self.result or dict(state='canceled' if self.isCanceled() else 'failed'))


class SceneRefreshTask(QgsTask):
    message = pyqtSignal(str)
    completed = pyqtSignal(object)

    def __init__(self, report, options, context, scene_contexts):
        super().__init__('Odświeżenie sceny 3D z zapisanych modeli', QgsTask.CanCancel)
        self.report, self.options, self.context, self.scene_contexts = report, options, context, scene_contexts
        self.event, self.result = threading.Event(), None

    def run(self):
        from .scene_refresh import refresh_scenes
        try:
            self.result = refresh_scenes(self.report, self.options, self.event, self.context, self.scene_contexts, self.message.emit)
            return True
        except Exception as exc:
            self.result = dict(error=str(exc), canceled=self.event.is_set())
            return False

    def cancel(self):
        self.event.set()
        super().cancel()

    def finished(self, success):
        self.completed.emit(self.result or dict(canceled=True))


def metric(value, minimum, maximum):
    result = QDoubleSpinBox()
    result.setRange(minimum, maximum)
    result.setDecimals(1)
    result.setValue(value)
    result.setSuffix(' m')
    return result


class ModelPanel(ResourceControls):
    def __init__(self, resource, settings):
        super().__init__(resource, settings)
        form = self.layout()
        self.enabled = QCheckBox('Utwórz mapę ' + resource)
        self.enabled.setChecked(True)
        self.analysis_radius = metric(float(settings.value(f'nmt_nmpt/atlas/{resource}/radius', 20000 if resource == 'NMT' else 1000)), 1, 200000)
        self.step = QComboBox()
        self.step.setEditable(True)
        self.step.addItems(['10', '5', '20', '1', '2', '50', '100'] if resource == 'NMT' else ['1', '0.5', '2', '5', '10'])
        self.step.setCurrentText(str(settings.value(f'nmt_nmpt/atlas/{resource}/step', '10' if resource == 'NMT' else '1')))
        form.insertRow(0, self.enabled)
        form.insertRow(1, 'Promień koła od turbin:', self.analysis_radius)
        form.insertRow(2, 'Krok mapy widoczności [m]:', self.step)
        self.explanation = QLabel('Mapa terenu. NMT ustala też poziom gruntu dla NMPT.' if resource == 'NMT' else 'Drzewa i dachy — dokładna mapa pokrycia')
        self.explanation.setWordWrap(True)
        form.insertRow(3, self.explanation)

    def advanced(self, show):
        for widget in (self.resolution, self.strict, self.height, self.alternate):
            widget.setVisible(show)
            label = self.layout().labelForField(widget)
            if label:
                label.setVisible(show)

    def model(self):
        step = float(self.step.currentText().replace(',', '.').strip())
        if not 0.5 <= step <= 1000:
            raise ValueError(self.resource + ': krok mapy musi być od 0,5 do 1000 m')
        if step > self.analysis_radius.value():
            raise ValueError(self.resource + ': krok mapy nie może być większy od promienia koła')
        side = 2 * self.analysis_radius.value() / step + 2
        if side ** 2 > MAX_LOCAL_CELLS:
            raise ValueError(f'{self.resource}: za dużo komórek. Zwiększ krok mapy lub zmniejsz promień (limit {MAX_LOCAL_CELLS / 1e6:g} mln na turbinę).')
        return dict(resource=self.resource, radius=self.analysis_radius.value(), resolution=step, height=self.height.currentText())


class WorkspaceDialog(QDialog):
    def __init__(self, iface, coverage_manager=None):
        super().__init__(iface.mainWindow())
        self.iface, self.coverage_manager = iface, coverage_manager
        self.settings = QSettings()
        self.task = self.catalog_task = self.last_report = None
        self.export_job = None
        self.report_dir = None
        self.atlas_layers = {}
        self.running_atlas = True
        self.scene_dirty, self.open_after_scene_refresh, self.loading_scene_controls = False, False, False
        self.scene_only, self.scene_observer, self.point_tool, self.previous_map_tool = False, None, None, None
        self.setWindowTitle(PLUGIN_NAME + ' · Atlas widoczności ' + VERSION)
        self.resize(1130, 940)
        self.setStyleSheet('QGroupBox{border:1px solid #cddce0;border-radius:7px;margin-top:10px;padding:12px 8px 6px}QGroupBox::title{subcontrol-origin:margin;left:12px;padding:0 5px}QPushButton#primary{background:#164b5d;color:white;padding:10px 20px;border:0;border-radius:5px;font-weight:bold}')
        layout = QVBoxLayout(self)
        header = QLabel('<div style="background:#153747;color:white;padding:14px"><span style="color:#87e0d2;font-size:11px">NMT + NMPT · KRAJOBRAZ I EKSPOZYCJA</span><br><b style="font-size:22px">Atlas widoczności turbin</b><br>Całe koło analizy. Obserwatorzy, drogi i zabudowa są opcjonalne.</div>')
        header.setWordWrap(True)
        layout.addWidget(header)
        self.inputs = QWidget()
        form = QFormLayout(self.inputs)
        self.mode = QComboBox()
        self.mode.addItems(['Pobierz potrzebne dane i utwórz atlas widoczności', 'Tylko pobierz NMT / NMPT dla bufora warstwy'])
        form.addRow('Tryb pracy:', self.mode)
        self.layer = QgsMapLayerComboBox()
        self.layer.setFilters(QgsMapLayerProxyModel.PointLayer)
        current = iface.activeLayer()
        if current is not None:
            self.layer.setLayer(current)
        self.layer_label = QLabel('Warstwa turbin (punkty):')
        form.addRow(self.layer_label, self.layer)
        self.selected = QCheckBox('Tylko zaznaczone obiekty warstwy wejściowej')
        form.addRow(self.selected)
        self.turbine_box = QGroupBox('Wysokość turbiny i poziom obserwacji w otoczeniu')
        heights = QFormLayout(self.turbine_box)
        self.hub = metric(120, 0.1, 2000)
        self.hub_field = QgsFieldComboBox()
        self.hub_field.setFilters(QgsFieldProxyModel.Numeric)
        self.hub_field.setAllowEmptyFieldName(True)
        heights.addRow('Piasta nad gruntem:', self.pair(self.hub, self.hub_field))
        self.diameter = metric(160, 0, 2000)
        self.diameter_field = QgsFieldComboBox()
        self.diameter_field.setFilters(QgsFieldProxyModel.Numeric)
        self.diameter_field.setAllowEmptyFieldName(True)
        heights.addRow('Średnica wirnika:', self.pair(self.diameter, self.diameter_field))
        self.eye = metric(1.7, 0.1, 2000)
        heights.addRow('Oko w otoczeniu ponad gruntem NMT:', self.eye)
        heights.addRow(QLabel('Puste pole atrybutów po prawej = stała wartość z lewej. Mapa pokazuje widoczność turbiny z otoczenia.'))
        form.addRow(self.turbine_box)
        self.layer.layerChanged.connect(self.set_fields)
        self.set_fields(self.layer.currentLayer())
        self.download_radius = metric(float(self.settings.value('nmt_nmpt/radius', 20000)), 0, 200000)
        form.addRow('Bufor pobierania wokół geometrii:', self.download_radius)
        self.panels = {resource: ModelPanel(resource, self.settings) for resource in ('NMT', 'NMPT')}
        models = QWidget()
        models_layout = QHBoxLayout(models)
        models_layout.setContentsMargins(0, 0, 0, 0)
        for panel in self.panels.values():
            models_layout.addWidget(panel)
        form.addRow(models)
        self.advanced = QCheckBox('Pokaż ustawienia źródeł: rozdzielczość danych i układy wysokościowe')
        self.advanced.toggled.connect(self.show_advanced)
        form.addRow(self.advanced)
        self.catalog_button = QPushButton('Sprawdź dostępne dane źródłowe GUGiK')
        self.catalog_button.clicked.connect(self.refresh_catalog)
        self.catalog_label = QLabel('Krok mapy jest niezależny od piksela danych źródłowych. NMPT o drobnym pikselu pobieraj w potrzebnym zasięgu.')
        self.catalog_label.setWordWrap(True)
        form.addRow(self.catalog_button)
        form.addRow(self.catalog_label)
        self.context_box = QGroupBox('Ważne miejsca z projektu — opcjonalne')
        context_form = QFormLayout(self.context_box)
        self.context_layers = {}
        for role, title, filters in [('drogi', 'Drogi:', QgsMapLayerProxyModel.LineLayer),
                                     ('zabudowa', 'Zabudowa / działki:', QgsMapLayerProxyModel.PolygonLayer),
                                     ('obserwatorzy', 'Obserwatorzy:', QgsMapLayerProxyModel.PointLayer | QgsMapLayerProxyModel.PolygonLayer)]:
            combo = QgsMapLayerComboBox()
            combo.setFilters(filters)
            combo.setAllowEmptyLayer(True)
            combo.setLayer(None)
            self.context_layers[role] = combo
            context_form.addRow(title, combo)
        note = QLabel('Bez tych warstw powstaną pełne mapy kół. Po ich wskazaniu atlas dodatkowo pokoloruje odcinki dróg i obrysy zabudowy według ekspozycji.')
        note.setWordWrap(True)
        context_form.addRow(note)
        form.addRow(self.context_box)
        self.detail_box = QGroupBox('Promienie, przekrój i widok 3D — bez wymaganej warstwy obserwatorów')
        detail_form = QFormLayout(self.detail_box)
        self.rays = QCheckBox('Zapisz zielone / czerwone promienie widoczności (dla każdej turbiny)')
        self.rays.setChecked(True)
        self.ray_spacing = QDoubleSpinBox()
        self.ray_spacing.setRange(1, 90)
        self.ray_spacing.setValue(10)
        self.ray_spacing.setSuffix('°')
        self.details = QCheckBox('Utwórz przekrój wysokościowy i obracaną scenę 3D')
        self.details.setChecked(True)
        self.view_turbine = QSpinBox()
        self.view_turbine.setRange(1, 1000)
        self.view_azimuth = QDoubleSpinBox()
        self.view_azimuth.setRange(0, 359.9)
        self.view_azimuth.setValue(225)
        self.view_azimuth.setSuffix('°')
        detail_form.addRow(self.rays)
        detail_form.addRow('Odstęp promieni (nie zmienia kroku mapy):', self.ray_spacing)
        detail_form.addRow(self.details)
        detail_form.addRow('Numer turbiny w analizowanym zestawie (od 1):', self.view_turbine)
        detail_form.addRow('Kierunek od turbiny do obserwatora: 0° N, 90° E:', self.view_azimuth)
        self.scene_quality = QComboBox()
        for label, count in [('Lekka · do 129 × 129', 129), ('Średnia · do 257 × 257', 257),
                             ('Dokładna · do 513 × 513', 513), ('Bardzo dokładna · do 1025 × 1025', 1025)]:
            self.scene_quality.addItem(label, count)
        self.scene_quality.setCurrentIndex(2)
        self.scene_radius = metric(0, 0, 200000)
        self.scene_radius.setSpecialValueText('Cały promień analizy')
        detail_form.addRow('Gęstość siatki 3D (bez zmiany analizy):', self.scene_quality)
        detail_form.addRow('Mniejszy promień samej sceny 3D (0 = cały):', self.scene_radius)
        self.scene_start_eye = QCheckBox('Otwórz scenę z poziomu oczu (miejsce można zmieniać na mapce w przeglądarce)')
        self.scene_start_eye.setChecked(True)
        detail_form.addRow(self.scene_start_eye)
        point_row = QWidget()
        point_layout = QHBoxLayout(point_row)
        point_layout.setContentsMargins(0, 0, 0, 0)
        self.pick_point_button = QPushButton('Wskaż miejsce patrzenia w QGIS')
        self.clear_point_button = QPushButton('Wyczyść punkt')
        self.pick_point_button.clicked.connect(self.pick_scene_point)
        self.clear_point_button.clicked.connect(self.clear_scene_point)
        point_layout.addWidget(self.pick_point_button)
        point_layout.addWidget(self.clear_point_button)
        detail_form.addRow(point_row)
        self.scene_point_label = QLabel('Punkt nie jest wymagany — w scenie klikniesz własne miejsce na mapce. Wysokość początkowa = oko nad gruntem NMT.')
        self.scene_point_label.setWordWrap(True)
        detail_form.addRow(self.scene_point_label)
        self.scene_layers = {}
        for role, title, filters in [('lasy', 'Lasy / zadrzewienia (opcjonalnie BDOT):', QgsMapLayerProxyModel.PolygonLayer),
                                     ('drzewa', 'Drzewa — punkty (opcjonalnie BDOT):', QgsMapLayerProxyModel.PointLayer)]:
            combo = QgsMapLayerComboBox()
            combo.setFilters(filters)
            combo.setAllowEmptyLayer(True)
            combo.setLayer(None)
            self.scene_layers[role] = combo
            detail_form.addRow(title, combo)
        self.scene_texture = QCheckBox('Nałóż ortofotomapę na model 3D')
        self.scene_texture.setChecked(True)
        detail_form.addRow(self.scene_texture)
        self.texture_mode = QComboBox()
        self.texture_mode.addItem('Geoportal · ortofotomapa online', 'geoportal')
        self.texture_mode.addItem('Wybrana warstwa rastrowa QGIS', 'layer')
        self.texture_mode.addItem('Widoczne warstwy projektu · zaawansowane', 'visible')
        self.texture_layer = QgsMapLayerComboBox()
        self.texture_layer.setFilters(QgsMapLayerProxyModel.RasterLayer)
        self.texture_layer.setAllowEmptyLayer(True)
        from .scene_texture import ortho_candidate
        candidate = ortho_candidate(QgsProject.instance())
        self.texture_layer.setLayer(candidate)
        if candidate:
            self.texture_mode.setCurrentIndex(1)
        self.texture_mode.currentIndexChanged.connect(lambda: self.texture_layer.setEnabled(self.texture_mode.currentData() == 'layer'))
        self.texture_layer.setEnabled(candidate is not None)
        detail_form.addRow('Źródło ortofotomapy:', self.texture_mode)
        detail_form.addRow('Warstwa zdjęcia (bez NMT/NMPT nad nim):', self.texture_layer)
        self.refresh_scene_button = QPushButton('Odśwież samą scenę 3D / ortofotomapę · bez przeliczania widoczności')
        self.refresh_scene_button.setEnabled(False)
        self.refresh_scene_button.clicked.connect(self.refresh_scene)
        detail_form.addRow(self.refresh_scene_button)
        self.texture_state_label = QLabel('Wybierz zdjęcie. Po zmianie źródła przycisk Scena 3D przygotuje aktualny widok.')
        self.texture_state_label.setWordWrap(True)
        self.texture_preview_button = QPushButton('Pokaż wyeksportowane zdjęcie PNG')
        self.texture_preview_button.setEnabled(False)
        self.texture_preview_button.clicked.connect(self.preview_texture)
        detail_form.addRow(self.texture_state_label)
        detail_form.addRow(self.texture_preview_button)
        note = QLabel('Ortofotomapa Geoportal/WMS/WMTS wymaga sieci. Brak lub szare tło jest raportowane. Odświeżenie sceny nie zmienia map widoczności. W widoku z oczu wysokość liczona jest nad NMT; dachy i korony NMPT mogą zasłaniać widok.')
        note.setWordWrap(True)
        detail_form.addRow(note)
        form.addRow(self.detail_box)
        self.report_folder = FolderChooser(self.settings.value('nmt_nmpt/report_folder', ''))
        form.addRow('Folder atlasów i raportów:', self.report_folder)
        self.auto_download = QCheckBox('Automatycznie pobierz brakujące kafle; używaj zgodnych plików z folderów')
        self.auto_download.setChecked(True)
        form.addRow(self.auto_download)
        self.workers = QSpinBox()
        self.workers.setRange(1, 4)
        self.workers.setValue(2)
        form.addRow('Pobierania równoległe:', self.workers)
        self.curvature = QCheckBox('Uwzględnij krzywiznę Ziemi i refrakcję optyczną')
        self.curvature.setChecked(True)
        form.addRow(self.curvature)
        self.show_after = QCheckBox('Po zakończeniu pokaż atlas w projekcie')
        self.show_after.setChecked(True)
        self.export_after = QCheckBox('Przygotuj mapy PDF / PNG oraz przeglądarkowy atlas HTML')
        self.export_after.setChecked(True)
        form.addRow(self.show_after)
        form.addRow(self.export_after)
        self.estimate = QLabel('')
        self.estimate.setWordWrap(True)
        form.addRow(self.estimate)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.inputs)
        layout.addWidget(scroll, 4)
        self.stage = QLabel('Gotowe. Wybierz turbiny; pozostałe warstwy możesz zostawić puste.')
        self.stage.setWordWrap(True)
        layout.addWidget(self.stage)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.stats_label = QLabel('')
        self.stats_label.setWordWrap(True)
        layout.addWidget(self.stats_label)
        self.activity_label = QLabel('')
        layout.addWidget(self.activity_label)
        self.clock = QTimer(self)
        self.clock.setInterval(500)
        self.clock.timeout.connect(self.heartbeat)
        self.active = QTableWidget(0, 4)
        self.active.setHorizontalHeaderLabels(['Zasób', 'Kafel', 'Bieżące zadanie', 'MB'])
        self.active.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.active.horizontalHeader().setStretchLastSection(True)
        self.active.setMaximumHeight(95)
        layout.addWidget(self.active)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        layout.addWidget(self.log, 1)
        buttons = QHBoxLayout()
        self.start_button = QPushButton('Utwórz atlas widoczności')
        self.start_button.setObjectName('primary')
        self.cancel_button = QPushButton('Anuluj')
        self.map_button = QPushButton('Pokaż wynik w QGIS')
        self.report_button = QPushButton('Otwórz atlas / raport')
        self.ray_button = QPushButton('Wysokości + promienie')
        self.profile_button = QPushButton('Przekrój 2D')
        self.scene_button = QPushButton('Scena 3D')
        self.rerun_button = QPushButton('Przelicz ponownie · lokalne modele')
        self.load_button = QPushButton('Wczytaj report.json')
        hide = QPushButton('Ukryj')
        for button in [self.start_button, self.cancel_button, self.map_button, self.report_button, hide]:
            buttons.addWidget(button)
        layout.addLayout(buttons)
        detail_buttons = QHBoxLayout()
        for button in [self.ray_button, self.profile_button, self.scene_button, self.rerun_button]:
            detail_buttons.addWidget(button)
            button.setEnabled(False)
        layout.addLayout(detail_buttons)
        detail_buttons.addWidget(self.load_button)
        self.cancel_button.setEnabled(False)
        self.map_button.setEnabled(False)
        self.report_button.setEnabled(False)
        self.start_button.clicked.connect(self.start)
        self.cancel_button.clicked.connect(self.cancel)
        self.map_button.clicked.connect(self.show_result)
        self.report_button.clicked.connect(self.open_report)
        self.ray_button.clicked.connect(self.show_rays)
        self.profile_button.clicked.connect(lambda: self.open_detail('profile'))
        self.scene_button.clicked.connect(lambda: self.open_detail('scene'))
        self.rerun_button.clicked.connect(self.rerun)
        self.load_button.clicked.connect(self.load_report)
        hide.clicked.connect(self.hide)
        self.mode.currentIndexChanged.connect(self.mode_changed)
        for panel in self.panels.values():
            panel.analysis_radius.valueChanged.connect(self.update_estimate)
            panel.step.currentTextChanged.connect(self.update_estimate)
            panel.enabled.toggled.connect(self.update_estimate)
        self.show_advanced(False)
        self.mode_changed()
        self.texture_layer.layerChanged.connect(self.texture_layer_selected)
        self.texture_mode.currentIndexChanged.connect(self.texture_mode_selected)
        for widget, signal in [(self.scene_texture, 'toggled'), (self.scene_start_eye, 'toggled'),
                               (self.scene_quality, 'currentIndexChanged'), (self.scene_radius, 'valueChanged'),
                               (self.view_turbine, 'valueChanged'), (self.view_azimuth, 'valueChanged'), (self.eye, 'valueChanged')]:
            getattr(widget, signal).connect(self.mark_scene_dirty)
        for combo in self.scene_layers.values():
            combo.layerChanged.connect(self.mark_scene_dirty)

    def mark_scene_dirty(self, *args):
        if self.loading_scene_controls:
            return
        self.scene_dirty = True
        if self.last_report:
            self.texture_state_label.setText('Zmieniono ustawienia. Scena 3D najpierw odświeży prezentację; mapy widoczności pozostaną bez zmian.')

    def texture_layer_selected(self, layer):
        if self.loading_scene_controls or layer is None:
            return
        self.texture_mode.setCurrentIndex(self.texture_mode.findData('layer'))
        self.scene_texture.setChecked(True)
        self.mark_scene_dirty()

    def texture_mode_selected(self, *args):
        if self.loading_scene_controls:
            return
        self.scene_texture.setChecked(True)
        self.mark_scene_dirty()

    def preferred_detail(self):
        items = self.last_report.get('details', []) if self.last_report else []
        return next((item for item in items if item['model'] == 'NMPT'), items[0] if items else None)

    def update_texture_state(self):
        detail = self.preferred_detail()
        if not detail:
            self.texture_preview_button.setEnabled(False)
            return
        path = Path(detail.get('texture') or (Path(self.report_dir) / ('tekstura_' + detail['model'] + '.png')))
        self.texture_preview_button.setEnabled(path.is_file())
        if self.last_report.get('scene_texture_error'):
            self.texture_state_label.setText('Eksport zdjęcia nie powiódł się: ' + self.last_report['scene_texture_error'])
            return
        try:
            text = Path(detail['scene']).read_text(encoding='utf-8')
            embedded = 'const textureData="data:image/' in text or 'const textureData= "data:image/' in text
        except OSError:
            embedded = False
        if embedded:
            info = detail.get('texture_info', {})
            self.texture_state_label.setText(f'Obraz jest dołączony do HTML. PNG: {info.get("width", "?")} × {info.get("height", "?")} px. Możesz sprawdzić go przyciskiem poniżej.')
        else:
            self.texture_state_label.setText('HTML nie zawiera ortofotomapy. Wybierz jej warstwę i kliknij Scena 3D — zdjęcie zostanie wyeksportowane.')

    def preview_texture(self):
        detail = self.preferred_detail()
        if detail:
            path = Path(detail.get('texture') or (Path(self.report_dir) / ('tekstura_' + detail['model'] + '.png')))
            if path.is_file():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    @staticmethod
    def pair(left, right):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(left)
        layout.addWidget(QLabel('lub pole [m]:'))
        layout.addWidget(right)
        return widget

    def set_fields(self, layer):
        for combo in (self.hub_field, self.diameter_field):
            combo.setLayer(layer)
            combo.setField('')

    def show_advanced(self, show):
        for panel in self.panels.values():
            panel.advanced(show)

    def mode_changed(self, *args):
        atlas = self.mode.currentIndex() == 0
        self.layer.setFilters(QgsMapLayerProxyModel.PointLayer if atlas else QgsMapLayerProxyModel.VectorLayer)
        self.layer_label.setText('Warstwa turbin (punkty):' if atlas else 'Warstwa do pobierania:')
        for widget in [self.turbine_box, self.context_box, self.detail_box, self.auto_download, self.curvature, self.show_after, self.export_after]:
            widget.setVisible(atlas)
        self.download_radius.setVisible(not atlas)
        self.inputs.layout().labelForField(self.download_radius).setVisible(not atlas)
        for panel in self.panels.values():
            panel.enabled.setText(('Utwórz mapę ' if atlas else 'Pobierz ') + panel.resource)
            for widget in [panel.analysis_radius, panel.step]:
                widget.setVisible(atlas)
                panel.layout().labelForField(widget).setVisible(atlas)
            panel.alternate.setEnabled(not atlas)
        self.start_button.setText('Utwórz atlas widoczności' if atlas else 'Pobierz dane')
        self.update_estimate()

    def update_estimate(self, *args):
        if self.mode.currentIndex() != 0:
            self.estimate.setText('Pobieranie obejmie bufor całej geometrii. Zgodne pliki na dysku będą pomijane.')
            return
        texts = []
        for resource, panel in self.panels.items():
            if not panel.enabled.isChecked():
                continue
            try:
                step = float(panel.step.currentText().replace(',', '.'))
                cells = (2 * panel.analysis_radius.value() / step) ** 2
                native = 1 if resource == 'NMT' else 0.5
                transfer = 22 * 3.1416 * (panel.analysis_radius.value() / native) ** 2 / 1e9
                texts.append(f'{resource}: {cells / 1e6:.2f} mln komórek / turbinę; transfer źródłowy orientacyjnie {transfer:.1f} GB / koło')
            except (ValueError, ZeroDivisionError):
                texts.append(resource + ': wpisz dodatni krok mapy')
        self.estimate.setText('\n'.join(texts) + '\nSzacunek transferu zakłada numeryczne ASCII; koła mogą się pokrywać, a pliki być już na dysku. Duży zasięg NMPT może oznaczać wiele GB.')

    def options(self):
        layer = self.layer.currentLayer()
        if layer is None or not layer.isValid() or not layer.crs().isValid():
            raise ValueError('Wybierz poprawną warstwę wejściową z CRS')
        ids = list(layer.selectedFeatureIds()) if self.selected.isChecked() else None
        if ids == [] or layer.featureCount() == 0:
            raise ValueError('Warstwa lub zaznaczenie jest puste')
        selected = [r for r, panel in self.panels.items() if panel.enabled.isChecked()]
        if not selected:
            raise ValueError('Włącz co najmniej NMT lub NMPT')
        atlas = self.mode.currentIndex() == 0
        required = set(selected)
        if atlas and 'NMPT' in required:
            required.add('NMT')
        folders = {}
        for resource, panel in self.panels.items():
            value = panel.folder.value()
            if resource in required and not value:
                raise ValueError('Wskaż folder ' + resource + (' (także poziom gruntu dla NMPT)' if resource == 'NMT' else ''))
            folders[resource] = str(Path(value).expanduser().resolve()) if value else ''
        if len(required) == 2 and folders['NMT'] == folders['NMPT']:
            raise ValueError('Użyj oddzielnych folderów NMT i NMPT')
        if not self.report_folder.value():
            raise ValueError('Wskaż folder atlasów / raportów')
        common = dict(folders=folders, report_folder=str(Path(self.report_folder.value()).expanduser().resolve()),
                      workers=self.workers.value(), pixels=1024, reuse=True)
        source_settings = {r: panel.options() for r, panel in self.panels.items()}
        if not atlas:
            return layer, dict(common, resources=selected, radius=self.download_radius.value(), feature_ids=ids,
                               resource_settings={r: source_settings[r] for r in selected}), {}
        models = [self.panels[r].model() for r in selected]
        contexts = {}
        for role, combo in dict(self.context_layers, **self.scene_layers).items():
            other = combo.currentLayer()
            if other is not None:
                if not other.crs().isValid():
                    raise ValueError('Brak CRS warstwy: ' + other.name())
                contexts[role] = (QgsVectorLayerFeatureSource(other), other.crs())
        opts = dict(common, models=models, source_settings=source_settings, turbines_ids=ids,
                    turbine_id_field=layer.customProperty('nmt_nmpt/turbine_id_field', ''),
                    context_layer_ids={key: combo.currentLayer().id() for key, combo in dict(self.context_layers, **self.scene_layers).items()
                                       if combo.currentLayer() is not None},
                    hub=self.hub.value(), diameter=self.diameter.value(), hub_field=self.hub_field.currentField(),
                    diameter_field=self.diameter_field.currentField(), eye=self.eye.value(),
                    auto_download=self.auto_download.isChecked(), curvature=self.curvature.isChecked(),
                    rays=self.rays.isChecked(), ray_spacing=self.ray_spacing.value(), details=self.details.isChecked(),
                    view_turbine=self.view_turbine.value(), view_azimuth=self.view_azimuth.value(),
                    scene_vertices=self.scene_quality.currentData(), scene_radius=self.scene_radius.value(),
                    scene_texture=self.scene_texture.isChecked())
        opts.update(self.view_options())
        return layer, opts, contexts

    def view_options(self):
        return dict(view_turbine=self.view_turbine.value(), view_azimuth=self.view_azimuth.value(),
                    scene_vertices=self.scene_quality.currentData(), scene_radius=self.scene_radius.value(),
                    scene_eye=self.eye.value(), scene_start_eye=self.scene_start_eye.isChecked(), scene_observer=self.scene_observer,
                    scene_texture=self.scene_texture.isChecked(), scene_texture_mode=self.texture_mode.currentData(),
                    scene_texture_layer_id=self.texture_layer.currentLayer().id() if self.texture_layer.currentLayer() else '')

    def update_scene_point_label(self):
        self.scene_point_label.setText('Miejsce patrzenia EPSG:2180: X={:.2f}, Y={:.2f}. Wysokość nad gruntem NMT.'.format(*self.scene_observer)
                                       if self.scene_observer else 'Punkt opcjonalny — w scenie klikniesz własne miejsce na mapce.')

    def clear_scene_point(self):
        self.scene_observer = None
        self.update_scene_point_label()
        self.mark_scene_dirty()

    def pick_scene_point(self):
        if self.task or self.export_job or self.point_tool:
            return
        from .scene_point_tool import ScenePointTool
        canvas = self.iface.mapCanvas()
        self.previous_map_tool = canvas.mapTool()
        self.point_tool = ScenePointTool(canvas)
        self.point_tool.canvasClicked.connect(self.scene_point_picked)
        self.point_tool.canceled.connect(self.stop_scene_picker)
        self.hide()
        canvas.setMapTool(self.point_tool)
        self.iface.mainWindow().statusBar().showMessage('Kliknij miejsce patrzenia. Escape anuluje wybór.')

    def stop_scene_picker(self, show=True):
        if self.point_tool:
            tool = self.point_tool
            canvas = self.iface.mapCanvas()
            if self.previous_map_tool:
                canvas.setMapTool(self.previous_map_tool)
            else:
                canvas.unsetMapTool(self.point_tool)
            self.point_tool = None
            self.previous_map_tool = None
            tool.deleteLater()
            self.iface.mainWindow().statusBar().clearMessage()
        if show:
            self.show()
            self.raise_()

    def scene_point_picked(self, point, button):
        if button == Qt.LeftButton:
            try:
                canvas = self.iface.mapCanvas()
                transform = QgsCoordinateTransform(canvas.mapSettings().destinationCrs(), QgsCoordinateReferenceSystem('EPSG:2180'),
                                                   QgsProject.instance().transformContext())
                projected = transform.transform(point)
                if not all(math.isfinite(v) for v in (projected.x(), projected.y())):
                    raise ValueError('Nieprawidłowe współrzędne')
                self.scene_observer = [projected.x(), projected.y()]
                self.scene_start_eye.setChecked(True)
                self.update_scene_point_label()
                self.mark_scene_dirty()
            except Exception as exc:
                QMessageBox.warning(self, PLUGIN_NAME, 'Nie można wskazać miejsca. Sprawdź CRS mapy. ' + str(exc))
        self.stop_scene_picker()

    def start(self, local_only=False, previous_report=None):
        if self.task or self.export_job:
            return
        self.scene_only = False
        self.open_after_scene_refresh = False
        try:
            layer, options, contexts = self.options()
            self.running_atlas = self.mode.currentIndex() == 0
            context = QgsCoordinateTransformContext(QgsProject.instance().transformContext())
            source = QgsVectorLayerFeatureSource(layer)
            if local_only:
                from .visibility import read_points
                points, issues = read_points(source, layer.crs(), context, 'turbines', options, threading.Event())
                positions = sorted((str(t['id']), round(t['x'], 3), round(t['y'], 3)) for t in points)
                original = sorted((str(t['id']), round(t['x'], 3), round(t['y'], 3)) for t in previous_report['turbines'])
                if positions != original:
                    raise ValueError('Zmieniono zestaw lub położenie turbin. Dla nowego obszaru użyj przycisku Utwórz atlas widoczności.')
                options.update(auto_download=False, recalculate_from=previous_report['report_dir'])
            self.task = AtlasTask(source, layer.crs(), context, options, contexts) if self.running_atlas else DownloadTask(source, layer.crs(), context, options)
        except Exception as exc:
            QMessageBox.warning(self, PLUGIN_NAME, str(exc))
            return
        for resource, panel in self.panels.items():
            self.settings.setValue('nmt_nmpt/' + resource.lower() + '_folder', panel.folder.value())
            self.settings.setValue(f'nmt_nmpt/atlas/{resource}/radius', panel.analysis_radius.value())
            self.settings.setValue(f'nmt_nmpt/atlas/{resource}/step', panel.step.currentText())
            for key, value in panel.options().items():
                self.settings.setValue(f'nmt_nmpt/{resource}/{key}', value)
        self.settings.setValue('nmt_nmpt/report_folder', options['report_folder'])
        self.inputs.setEnabled(False)
        self.load_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.map_button.setEnabled(False)
        self.report_button.setEnabled(False)
        self.last_report = None
        for button in [self.ray_button, self.profile_button, self.scene_button, self.rerun_button]:
            button.setEnabled(False)
        self.atlas_layers = {}
        self.log.clear()
        if local_only:
            self.log.appendPlainText('Ponowne obliczenia: wyłącznie lokalne NMT/NMPT. Poprzedni wynik zostaje w osobnym folderze.')
        self.progress.setRange(0, 0)
        self.clock_started = time.monotonic()
        self.clock.start()
        self.task.stats.connect(self.update_stats)
        self.task.message.connect(self.log.appendPlainText)
        self.task.completed.connect(self.finished)
        if self.coverage_manager:
            for resource, folder in options['folders'].items():
                if folder:
                    try:
                        self.coverage_manager.ensure(folder, resource)
                    except Exception as exc:
                        self.log.appendPlainText('Indeks folderu: ' + str(exc))
        QgsApplication.taskManager().addTask(self.task)

    def refresh_scene(self):
        if self.task or self.export_job or not self.last_report:
            return
        self.scene_only = True
        contexts = {role: (QgsVectorLayerFeatureSource(combo.currentLayer()), combo.currentLayer().crs())
                    for role, combo in self.scene_layers.items() if combo.currentLayer() is not None}
        self.task = SceneRefreshTask(self.last_report, self.view_options(),
                                     QgsCoordinateTransformContext(QgsProject.instance().transformContext()), contexts)
        self.task.message.connect(self.stage.setText)
        self.task.message.connect(self.log.appendPlainText)
        self.task.completed.connect(self.scene_refreshed)
        self.inputs.setEnabled(False)
        self.load_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.rerun_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setRange(0, 0)
        self.clock_started = time.monotonic()
        self.clock.start()
        QgsApplication.taskManager().addTask(self.task)

    def scene_refreshed(self, result):
        self.task = None
        if result.get('error') or result.get('canceled'):
            self.last_report['presentation_error'] = result.get('error', 'Anulowano odświeżenie sceny')
            self.complete(self.last_report)
            return
        self.last_report, self.report_dir = result, result['report_dir']
        if self.scene_texture.isChecked():
            from .scene_texture import SceneTextures
            self.export_job = SceneTextures(result, self)
            self.export_job.status.connect(self.stage.setText)
            self.export_job.status.connect(self.log.appendPlainText)
            self.export_job.completed.connect(self.textures_finished)
            self.export_job.start()
        else:
            self.finish_scene_view()

    def finish_scene_view(self):
        from .atlas_presentation import make_html
        presentation = self.last_report.setdefault('presentation', dict(png=[]))
        presentation.setdefault('png', [])
        make_html(self.last_report, presentation)
        self.complete(self.last_report)

    def update_stats(self, stats):
        if stats.get('kind') == 'download' or 'bytes' in stats:
            DownloadDialog.update_stats(self, stats)
            if stats.get('all_bytes') is not None:
                self.stats_label.setText(self.stats_label.text() + f'\nŁączny transfer zadania: {stats["all_bytes"] / 1e6:.1f} MB')
            return
        self.active.setRowCount(0)
        self.stage.setText(stats['stage'] + (f' · operacja {stats["operation_percent"]}%' if 'operation_percent' in stats else ''))
        self.stats_label.setText(f'Czas: {duration(stats["elapsed"])} | Turbiny etapu: {stats["done"]}/{stats["total"]} | '
                                 f'ETA modelu ≈ {duration(stats.get("eta"))} | Łączny transfer: {stats.get("transfer_bytes", 0) / 1e6:.1f} MB')
        if stats['total']:
            self.progress.setRange(0, 10000)
            fraction = stats.get('fraction_done', stats['done'] / stats['total'])
            self.progress.setValue(int(fraction * 10000))
        else:
            self.progress.setRange(0, 0)

    def finished(self, report):
        self.task = None
        self.last_report = report
        self.report_dir = report.get('report_dir')
        self.cancel_button.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if report['state'].startswith('completed') else 0)
        self.report_button.setEnabled(bool(self.report_dir))
        self.map_button.setEnabled(bool(report.get('products') or report.get('tiles')))
        if self.coverage_manager:
            self.coverage_manager.refresh_all()
        if self.running_atlas and report['state'].startswith('completed') and (self.show_after.isChecked() or self.export_after.isChecked() or self.scene_texture.isChecked()):
            self.stage.setText('Prezentacja atlasu — legendy, mapy PDF / PNG i raport HTML…')
            QgsApplication.processEvents()
            try:
                from .atlas_presentation import add_atlas
                self.atlas_layers = add_atlas(report, self.iface if self.show_after.isChecked() else None,
                                              show=self.show_after.isChecked())
                if report.get('options', {}).get('scene_texture') and report.get('details'):
                    from .scene_texture import SceneTextures
                    self.progress.setRange(0, 0)
                    self.cancel_button.setEnabled(True)
                    self.export_job = SceneTextures(report, self)
                    self.export_job.status.connect(self.stage.setText)
                    self.export_job.status.connect(self.log.appendPlainText)
                    self.export_job.completed.connect(self.textures_finished)
                    self.export_job.start()
                    return
                if self.export_after.isChecked():
                    self.launch_export()
                    return
            except Exception as exc:
                self.log.appendPlainText('Wyniki obliczono; problem prezentacji: ' + str(exc))
                report['presentation_error'] = str(exc)
        self.complete(report)

    def launch_export(self):
        from .atlas_presentation import AsyncAtlasExport
        self.progress.setRange(0, 0)
        self.cancel_button.setEnabled(True)
        self.export_job = AsyncAtlasExport(self.last_report, self.atlas_layers, self)
        self.export_job.status.connect(self.stage.setText)
        self.export_job.status.connect(self.log.appendPlainText)
        self.export_job.completed.connect(self.presentation_finished)
        self.export_job.start()

    def textures_finished(self, result):
        self.export_job = None
        if result.get('canceled'):
            self.last_report['presentation_error'] = 'Anulowano przygotowanie prezentacji; wyniki analizy zostały zachowane.'
            self.complete(self.last_report)
        else:
            if result.get('error'):
                self.last_report['scene_texture_error'] = result['error']
                self.log.appendPlainText('Tekstura 3D: ' + result['error'])
            if self.scene_only:
                self.finish_scene_view()
            elif self.export_after.isChecked():
                self.launch_export()
            else:
                self.complete(self.last_report)

    def presentation_finished(self, result):
        self.export_job = None
        if result.get('canceled'):
            self.last_report['presentation_error'] = 'Eksport anulowany; obliczone rastry, promienie i podglądy zostały zachowane.'
        elif result.get('error'):
            self.last_report['presentation_error'] = result['error']
        elif not result.get('pdf') or not result.get('png'):
            self.last_report['presentation_error'] = 'Nie udało się zapisać wszystkich map PDF / PNG.'
        from .core import atomic_json
        if self.report_dir:
            atomic_json(Path(self.report_dir) / 'report.json', self.last_report)
        self.complete(self.last_report)

    def complete(self, report):
        auto_open = self.open_after_scene_refresh and self.scene_only
        self.open_after_scene_refresh = False
        if self.report_dir:
            from .core import atomic_json
            try:
                atomic_json(Path(self.report_dir) / 'report.json', report)
            except (OSError, ValueError, TypeError) as exc:
                self.log.appendPlainText('Nie można zapisać końcowej diagnostyki: ' + str(exc))
        self.clock.stop()
        self.cancel_button.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if report['state'].startswith('completed') else 0)
        self.ray_button.setEnabled(bool(report.get('rays_gpkg')))
        self.profile_button.setEnabled(bool(report.get('details')))
        self.scene_button.setEnabled(bool(report.get('details')))
        self.rerun_button.setEnabled(bool(report.get('turbines') and report.get('products')))
        self.refresh_scene_button.setEnabled(bool(report.get('turbines') and report.get('products')))
        text = {'completed': 'Gotowe — atlas wykonany' if self.running_atlas else 'Pobieranie wykonane',
                'completed_with_gaps': 'Zakończono — sprawdź oznaczone braki danych',
                'canceled': 'Anulowano; ukończone wyniki zachowano', 'failed': 'Zadanie nie powiodło się'}[report['state']]
        if report.get('fatal_error'):
            text += '\n' + report['fatal_error']
        if report.get('presentation_error'):
            text += '\nProblem prezentacji: ' + report['presentation_error']
        if report.get('scene_texture_error'):
            text += '\nOrtofotomapa: ' + report['scene_texture_error']
        if self.scene_only:
            text = ('Nie ukończono odświeżenia sceny.' if report.get('presentation_error') else
                    'Odświeżono scenę 3D; mapy widoczności pozostają z poprzednich obliczeń.') + (
                '\nOrtofotomapa: ' + report['scene_texture_error'] if report.get('scene_texture_error') else '') + (
                '\n' + report['presentation_error'] if report.get('presentation_error') else '')
        self.stage.setText(text)
        self.log.appendPlainText(text)
        self.inputs.setEnabled(True)
        self.load_button.setEnabled(True)
        self.start_button.setEnabled(True)
        self.scene_dirty = bool(report.get('presentation_error'))
        self.update_texture_state()
        if report['state'] == 'completed' and not report.get('presentation_error') and not report.get('scene_texture_error'):
            if not auto_open:
                QMessageBox.information(self, PLUGIN_NAME, text)
        else:
            QMessageBox.warning(self, PLUGIN_NAME, text)
        if auto_open and not report.get('presentation_error') and not report.get('scene_texture_error'):
            detail = self.preferred_detail()
            if detail:
                QDesktopServices.openUrl(QUrl.fromLocalFile(detail['scene']))

    def cancel(self):
        if self.export_job:
            self.export_job.cancel()
            self.cancel_button.setEnabled(False)
        if self.task:
            self.task.cancel()
            self.cancel_button.setEnabled(False)
            self.stage.setText('Anulowanie… zachowuję ukończone pliki; aktywne połączenie może czekać do 90 s')

    def heartbeat(self):
        self.activity_label.setText('Łączny czas: ' + duration(time.monotonic() - self.clock_started) +
                                    (' · renderowanie map w tle' if self.export_job else ' · zadanie aktywne'))

    def show_rays(self):
        self.show_result()
        if not self.last_report:
            return
        root = QgsProject.instance().layerTreeRoot()
        for key, layer in self.atlas_layers.items():
            node = root.findLayer(layer.id())
            if node and '/' in key:
                node.setItemVisibilityChecked(key.endswith(('/rays', '/elevation', '/circles')))
        self.iface.mapCanvas().refresh()

    def open_detail(self, kind):
        if self.task or self.export_job:
            return
        if kind == 'scene' and self.last_report:
            generated_version = self.last_report.get('scene_version', self.last_report.get('version'))
            detail = self.preferred_detail()
            missing_texture = self.scene_texture.isChecked() and detail and not detail.get('texture') and not self.last_report.get('scene_texture_error')
            if self.scene_dirty or generated_version != VERSION or missing_texture:
                self.open_after_scene_refresh = True
                self.refresh_scene()
                return
        if self.last_report and self.last_report.get('details'):
            items = self.last_report['details']
            preferred = next((item for item in items if item['model'] == 'NMPT'), items[0])
            QDesktopServices.openUrl(QUrl.fromLocalFile(preferred[kind]))

    def rerun(self):
        if not self.task and not self.export_job and self.last_report and self.last_report.get('turbines'):
            self.mode.setCurrentIndex(0)
            self.start(local_only=True, previous_report=self.last_report)

    def load_report(self, filename=None):
        if self.task or self.export_job:
            return
        if not isinstance(filename, (str, Path)):
            filename, _ = QFileDialog.getOpenFileName(self, 'Wczytaj ustawienia atlasu z report.json',
                                                      self.report_dir or '', 'Raport JSON (*.json)')
        if not filename:
            return
        try:
            self.loading_scene_controls = True
            path = Path(filename)
            report = json.loads(path.read_text(encoding='utf-8'))
            if not report.get('products') or not report.get('turbines') or not report.get('options', {}).get('models'):
                raise ValueError('To nie jest raport atlasu widoczności')
            local = path.parent / 'atlas.gpkg'
            source = local if local.is_file() else Path(report['gpkg'])
            layer = QgsVectorLayer(str(source) + '|layername=turbiny', 'Turbiny z atlasu · ' + path.parent.name, 'ogr')
            if not layer.isValid():
                raise ValueError('Brak atlas.gpkg z geometrią i wysokościami turbin. Zachowaj cały folder atlasu.')
            layer.setCustomProperty('nmt_nmpt/turbine_id_field', 'source_id')
            QgsProject.instance().addMapLayer(layer)
            self.mode.setCurrentIndex(0)
            self.layer.setLayer(layer)
            self.selected.setChecked(False)
            self.hub_field.setField('piasta_m')
            self.diameter_field.setField('srednica_m')
            opts = report['options']
            view = report.get('scene_view_options') or opts
            for resource, panel in self.panels.items():
                model = next((s for s in opts['models'] if s['resource'] == resource), None)
                panel.enabled.setChecked(model is not None)
                panel.folder.edit.setText(opts['folders'].get(resource, ''))
                settings = opts.get('source_settings', {}).get(resource, {})
                panel.select_resolution(float(settings.get('resolution', 0)))
                panel.strict.setChecked(bool(settings.get('strict_resolution', False)))
                panel.height.setCurrentText((model or settings).get('height', 'PL-EVRF2007-NH'))
                if model:
                    panel.analysis_radius.setValue(model['radius'])
                    panel.step.setCurrentText(str(model['resolution']))
            for key, widget in [('eye', self.eye), ('hub', self.hub), ('diameter', self.diameter),
                                ('view_turbine', self.view_turbine), ('view_azimuth', self.view_azimuth),
                                ('scene_radius', self.scene_radius), ('ray_spacing', self.ray_spacing)]:
                values = view if key in ('view_turbine', 'view_azimuth', 'scene_radius') else opts
                if key in values:
                    widget.setValue(values[key])
            self.eye.setValue(view.get('scene_eye', opts.get('eye', 1.7)))
            self.scene_quality.setCurrentIndex(max(0, self.scene_quality.findData(view.get('scene_vertices', 513))))
            self.scene_observer = view.get('scene_observer')
            self.scene_start_eye.setChecked(bool(view.get('scene_start_eye', True)))
            self.texture_mode.setCurrentIndex(max(0, self.texture_mode.findData(view.get('scene_texture_mode', 'geoportal'))))
            chosen_texture = QgsProject.instance().mapLayer(view.get('scene_texture_layer_id', ''))
            if chosen_texture:
                self.texture_layer.setLayer(chosen_texture)
            self.update_scene_point_label()
            for key, checkbox in [('curvature', self.curvature), ('rays', self.rays), ('details', self.details),
                                  ('scene_texture', self.scene_texture)]:
                checkbox.setChecked(bool((view if key == 'scene_texture' else opts).get(key, key != 'scene_texture')))
            for key, combo in dict(self.context_layers, **self.scene_layers).items():
                combo.setLayer(QgsProject.instance().mapLayer(opts.get('context_layer_ids', {}).get(key, '')))
            self.auto_download.setChecked(False)
            self.report_folder.edit.setText(str(path.parent.parent))
            report['report_dir'] = str(path.parent)
            report['gpkg'] = str(source)
            for key, name in [('links_gpkg', 'raport.gpkg'), ('rays_gpkg', 'promienie.gpkg')]:
                if (path.parent / name).is_file():
                    report[key] = str(path.parent / name)
            for product in report['products']:
                for key, old_path in product['paths'].items():
                    local = path.parent / product['resource'] / Path(old_path).name
                    if local.is_file():
                        product['paths'][key] = str(local)
            for detail in report.get('details', []):
                for key in ['profile', 'scene', 'fallback_scene', 'texture']:
                    if detail.get(key) and (path.parent / Path(detail[key]).name).is_file():
                        detail[key] = str(path.parent / Path(detail[key]).name)
            if (path.parent / 'atlas.html').is_file():
                report.setdefault('presentation', {})['html'] = str(path.parent / 'atlas.html')
            self.last_report, self.report_dir, self.running_atlas = report, str(path.parent), True
            self.atlas_layers = {}
            self.rerun_button.setEnabled(True)
            self.refresh_scene_button.setEnabled(True)
            self.report_button.setEnabled(True)
            self.map_button.setEnabled(True)
            self.ray_button.setEnabled(bool(report.get('rays_gpkg')))
            self.profile_button.setEnabled(bool(report.get('details')))
            self.scene_button.setEnabled(bool(report.get('details')))
            self.scene_dirty = False
            self.update_texture_state()
            self.stage.setText('Wczytano poprzedni zestaw. Zmień parametry i kliknij Przelicz ponownie. Pola piasta_m / srednica_m zachowują wysokości; puste pola oznaczają stałe wartości.')
        except Exception as exc:
            QMessageBox.warning(self, PLUGIN_NAME, 'Nie można odtworzyć atlasu: ' + str(exc))
        finally:
            self.loading_scene_controls = False

    def show_result(self):
        try:
            if self.last_report and self.last_report.get('products'):
                from .atlas_presentation import add_atlas
                self.atlas_layers = add_atlas(self.last_report, self.iface)
            elif self.coverage_manager and self.last_report:
                self.coverage_manager.show_results(self.last_report)
        except Exception as exc:
            QMessageBox.warning(self, PLUGIN_NAME, str(exc))

    def open_report(self):
        if self.last_report:
            target = self.last_report.get('presentation', {}).get('html') or self.report_dir
            if target:
                QDesktopServices.openUrl(QUrl.fromLocalFile(target))

    def refresh_catalog(self):
        self.catalog_button.setEnabled(False)
        self.catalog_task = CatalogTask()
        self.catalog_task.completed.connect(self.catalog_finished)
        QgsApplication.taskManager().addTask(self.catalog_task)

    def catalog_finished(self, result):
        self.catalog_task = None
        self.catalog_button.setEnabled(True)
        for panel in self.panels.values():
            panel.update_catalog(result['variants'])
        self.catalog_label.setText('\n'.join(f'{r}: ' + ', '.join(f'{v["resolution"]:g} m / {v["height"]}' for v in result['variants'] if v['resource'] == r) for r in self.panels))

    def closeEvent(self, event):
        self.hide()
        event.ignore()
