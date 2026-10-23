"""QGIS UI for NMPT-first turbine-to-receiver sight line analysis."""
from pathlib import Path

from qgis.PyQt.QtCore import QSettings, QUrl, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)
from qgis.core import (
    QgsApplication, QgsCategorizedSymbolRenderer, QgsCoordinateTransformContext,
    QgsFieldProxyModel, QgsLineSymbol, QgsMapLayerProxyModel, QgsProject,
    QgsRendererCategory, QgsTask, QgsVectorLayer, QgsVectorLayerFeatureSource, QgsWkbTypes,
)
from qgis.gui import QgsFieldComboBox, QgsMapLayerComboBox

from .catalog import HEIGHTS
from .plugin import FolderChooser, duration
from .visibility import LABELS, MAX_PAIRS, VisibilityEngine


class VisibilityTask(QgsTask):
    stats = pyqtSignal(object)
    message = pyqtSignal(str)
    completed = pyqtSignal(object)

    def __init__(self, turbines, turbine_crs, receivers, receiver_crs, context, options):
        super().__init__('Widoczność turbin — NMPT', QgsTask.CanCancel)
        self.engine = VisibilityEngine(turbines, turbine_crs, receivers, receiver_crs, context,
                                       options, self.stats.emit, self.message.emit)
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


def metric(value, minimum, maximum):
    widget = QDoubleSpinBox()
    widget.setRange(minimum, maximum)
    widget.setDecimals(2)
    widget.setSuffix(' m')
    widget.setValue(value)
    return widget


def add_results(report):
    """Run only on the GUI thread after the worker has closed its GeoPackage."""
    path = report.get('gpkg')
    if not path or not Path(path).is_file():
        raise ValueError('Brak pliku wynikowego GeoPackage')
    project = QgsProject.instance()
    sources = {layer.source() for layer in project.mapLayers().values()}
    group = None
    colors = {'blocked_terrain': '#935b28', 'blocked_detail': '#d43832',
              'visible_modeled': '#168447', 'potential_visible_partial_detail': '#de9d18',
              'visible_terrain_only': '#5388b2', 'unknown_required_data': '#8154b5',
              'uncertain_geometry': '#cf589b', 'outside_analysis': '#969696'}
    for name, title in [('linie_widzenia', 'Widoczność — linie NMPT'), ('turbiny', 'Widoczność — turbiny'),
                        ('obserwatorzy', 'Widoczność — obserwatorzy')]:
        source = str(path) + '|layername=' + name
        if source in sources:
            continue
        layer = QgsVectorLayer(source, title, 'ogr')
        if not layer.isValid():
            raise ValueError('Nie można otworzyć warstwy: ' + name)
        if name == 'linie_widzenia':
            categories = []
            for status, label in LABELS.items():
                symbol = QgsLineSymbol.createSimple(dict(line_color=colors[status], line_width='0.6',
                                                         line_style='dash' if status == 'outside_analysis' else 'solid'))
                categories.append(QgsRendererCategory(status, symbol, label))
            layer.setRenderer(QgsCategorizedSymbolRenderer('status', categories))
        if group is None:
            group = project.layerTreeRoot().addGroup(Path(path).parent.name)
        project.addMapLayer(layer, False)
        group.addLayer(layer)


class VisibilityDialog(QDialog):
    def __init__(self, iface, coverage_manager=None):
        super().__init__(iface.mainWindow())
        self.iface, self.coverage_manager = iface, coverage_manager
        self.settings = QSettings()
        self.task, self.last_report = None, None
        self.setWindowTitle('NMT i NMTP ściągacz — widoczność turbin z NMPT')
        self.resize(950, 900)
        layout = QVBoxLayout(self)
        self.inputs = QGroupBox('Miejsca obserwacji, turbiny i model NMPT')
        form = QFormLayout(self.inputs)
        self.turbines = QgsMapLayerComboBox()
        self.turbines.setFilters(QgsMapLayerProxyModel.PointLayer)
        form.addRow('Warstwa turbin (punkty):', self.turbines)
        self.selected_turbines = QCheckBox('Tylko zaznaczone turbiny')
        form.addRow(self.selected_turbines)
        self.hub = metric(120, 0.01, 2000)
        form.addRow('Wysokość piasty nad gruntem:', self.hub)
        self.hub_field = QgsFieldComboBox()
        self.hub_field.setFilters(QgsFieldProxyModel.Numeric)
        self.hub_field.setAllowEmptyFieldName(True)
        self.hub_field.setToolTip('Puste pole oznacza stałą wartość wpisaną powyżej')
        form.addRow('Albo pole wysokości piasty [m]:', self.hub_field)
        self.diameter = metric(160, 0, 2000)
        form.addRow('Średnica wirnika:', self.diameter)
        self.diameter_field = QgsFieldComboBox()
        self.diameter_field.setFilters(QgsFieldProxyModel.Numeric)
        self.diameter_field.setAllowEmptyFieldName(True)
        self.diameter_field.setToolTip('Puste pole oznacza stałą wartość wpisaną powyżej')
        form.addRow('Albo pole średnicy wirnika [m]:', self.diameter_field)
        self.turbines.layerChanged.connect(self.set_turbine_fields)
        self.set_turbine_fields(self.turbines.currentLayer())
        self.target = QComboBox()
        self.target.addItem('Najwyższy punkt zasięgu łopaty (piasta + ½ średnicy)', 'tip')
        self.target.addItem('Piasta', 'hub')
        form.addRow('Sprawdzany punkt turbiny:', self.target)
        self.receivers = QgsMapLayerComboBox()
        self.receivers.setFilters(QgsMapLayerProxyModel.PointLayer | QgsMapLayerProxyModel.PolygonLayer)
        current = iface.activeLayer()
        if current is not None and current.type() == current.VectorLayer and current.geometryType() in (QgsWkbTypes.PointGeometry, QgsWkbTypes.PolygonGeometry):
            self.receivers.setLayer(current)
        form.addRow('Obserwatorzy / zabudowa / działki:', self.receivers)
        self.selected_receivers = QCheckBox('Tylko zaznaczeni odbiorcy / poligony')
        form.addRow(self.selected_receivers)
        self.eye = metric(1.7, 0.1, 2000)
        form.addRow('Oko nad gruntem NMT:', self.eye)
        self.radius = metric(float(self.settings.value('nmt_nmpt/visibility/radius', 20000)), 1, 200000)
        form.addRow('Maksymalna odległość od turbiny:', self.radius)
        self.use_nmpt = QCheckBox('Uwzględnij NMPT — dachy, drzewa i inne pokrycie (zalecane)')
        self.use_nmpt.setChecked(True)
        form.addRow(self.use_nmpt)
        self.detail_mode = QComboBox()
        self.detail_mode.addItem('NMPT lokalnie — mniejszy transfer, wynik może być tylko potencjalny', 'local')
        self.detail_mode.addItem('NMPT na całej linii — sprawdzenie pokrycia całej trasy', 'full')
        form.addRow('Zakres szczegółowego NMPT:', self.detail_mode)
        self.detail_centers = QComboBox()
        self.detail_centers.addItem('Obserwatorzy i turbiny', 'both')
        self.detail_centers.addItem('Tylko obserwatorzy', 'receivers')
        self.detail_centers.addItem('Tylko turbiny', 'turbines')
        form.addRow('NMPT wokół:', self.detail_centers)
        self.detail_radius = QComboBox()
        self.detail_radius.setEditable(True)
        self.detail_radius.addItems(['1000', '650', '1500'])
        form.addRow('Lokalny promień NMPT [m] (możesz wpisać):', self.detail_radius)
        self.detail_mode.currentIndexChanged.connect(self.update_detail)
        self.use_nmpt.toggled.connect(self.update_detail)
        self.nmpt_folder = FolderChooser(self.settings.value('nmt_nmpt/nmpt_folder', ''))
        form.addRow('Folder kafli NMPT:', self.nmpt_folder)
        self.nmt_folder = FolderChooser(self.settings.value('nmt_nmpt/nmt_folder', ''))
        form.addRow('Folder NMT — pomocniczy poziom gruntu:', self.nmt_folder)
        self.report_folder = FolderChooser(self.settings.value('nmt_nmpt/report_folder', ''))
        form.addRow('Folder wyników i raportów:', self.report_folder)
        self.height = QComboBox()
        self.height.addItems(HEIGHTS)
        form.addRow('Wspólny układ wysokościowy NMT i NMPT:', self.height)
        self.auto_download = QCheckBox('Automatycznie pobierz / sprawdź potrzebne kafle, używaj zgodnych plików z dysku')
        self.auto_download.setChecked(True)
        self.auto_download.setToolTip('Najlepsza dostępna rozdzielczość źródłowa. Pobieranie tylko wzdłuż wybranych linii, bez drugiego układu wysokościowego. Odznacz, aby pracować wyłącznie na folderach lokalnych.')
        form.addRow(self.auto_download)
        self.workers = QSpinBox()
        self.workers.setRange(1, 4)
        self.workers.setValue(2)
        form.addRow('Pobierania równoległe:', self.workers)
        self.curvature = QCheckBox('Krzywizna Ziemi i standardowa refrakcja optyczna (k = 1/7)')
        self.curvature.setChecked(True)
        form.addRow(self.curvature)
        hint = QLabel('Dla poligonu sprawdzany jest jeden punkt wewnętrzny. Dla budynku najlepiej wskaż własny punkt na zewnątrz, '
                      'aby oko nie znalazło się pod dachem w NMPT. Widoczność końca łopaty nie oznacza widoczności całego wirnika.\n'
                      'NMPT jest modelem 2,5D; ten moduł liczy linie widzenia, bez pełnej sceny 3D. '
                      'Transfer obejmuje pełne kafle przecinające korytarze linii (bufor 2 m NMPT / 5 m NMT). Nie pobiera całych dysków 20 km.')
        hint.setWordWrap(True)
        form.addRow(hint)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.inputs)
        layout.addWidget(scroll, 3)
        self.stage = QLabel('Gotowe. NMPT jest włączone; wybierz turbiny oraz miejsca obserwacji.')
        self.stage.setWordWrap(True)
        layout.addWidget(self.stage)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.statistics = QLabel('')
        self.statistics.setWordWrap(True)
        layout.addWidget(self.statistics)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        layout.addWidget(self.log, 1)
        buttons = QHBoxLayout()
        self.start_button = QPushButton('Analizuj widoczność z NMPT')
        self.cancel_button = QPushButton('Anuluj')
        self.map_button = QPushButton('Pokaż wyniki na mapie')
        self.report_button = QPushButton('Otwórz folder raportu')
        hide = QPushButton('Ukryj')
        for button in (self.start_button, self.cancel_button, self.map_button, self.report_button, hide):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.cancel_button.setEnabled(False)
        self.map_button.setEnabled(False)
        self.report_button.setEnabled(False)
        self.start_button.clicked.connect(self.start)
        self.cancel_button.clicked.connect(self.cancel)
        self.map_button.clicked.connect(self.show_results)
        self.report_button.clicked.connect(self.open_report)
        hide.clicked.connect(self.hide)
        self.update_detail()

    def set_turbine_fields(self, layer):
        for combo in (self.hub_field, self.diameter_field):
            combo.setLayer(layer)
            combo.setField('')

    def update_detail(self, *args):
        enabled = self.use_nmpt.isChecked()
        local = enabled and self.detail_mode.currentData() == 'local'
        self.detail_mode.setEnabled(enabled)
        self.detail_centers.setEnabled(local)
        self.detail_radius.setEnabled(local)

    def options(self):
        turbines, receivers = self.turbines.currentLayer(), self.receivers.currentLayer()
        for name, layer, selected in [('turbin', turbines, self.selected_turbines), ('odbiorców', receivers, self.selected_receivers)]:
            if layer is None or not layer.isValid() or not layer.crs().isValid():
                raise ValueError(f'Wybierz poprawną warstwę {name} z rozpoznanym CRS')
            if not (layer.selectedFeatureCount() if selected.isChecked() else layer.featureCount()):
                raise ValueError(f'Warstwa {name} / zaznaczenie jest puste')
        nt = turbines.selectedFeatureCount() if self.selected_turbines.isChecked() else turbines.featureCount()
        nr = receivers.selectedFeatureCount() if self.selected_receivers.isChecked() else receivers.featureCount()
        if nt * nr > MAX_PAIRS:
            raise ValueError(f'Wybrano {nt * nr} par; limit zadania to {MAX_PAIRS}. Wybierz część obiektów przez zaznaczenie.')
        local = self.use_nmpt.isChecked() and self.detail_mode.currentData() == 'local'
        detail_radius = float(self.detail_radius.currentText().strip().replace(',', '.')) if local else 1000
        if not 0 < detail_radius <= 200000:
            raise ValueError('Promień NMPT musi być większy od 0 i nie większy niż 200000 m')
        folders = {}
        for resource, chooser in [('NMT', self.nmt_folder), ('NMPT', self.nmpt_folder), ('reports', self.report_folder)]:
            if not chooser.value() and (resource != 'NMPT' or self.use_nmpt.isChecked()):
                raise ValueError('Wskaż folder: ' + resource)
            if chooser.value():
                folders[resource] = str(Path(chooser.value()).expanduser().resolve())
        if folders.get('NMPT') == folders['NMT']:
            raise ValueError('Użyj oddzielnych folderów NMT i NMPT')
        folders.setdefault('NMPT', str(Path(folders['reports']) / 'nieuzywany_NMPT'))
        options = dict(radius=self.radius.value(), eye=self.eye.value(), hub=self.hub.value(), diameter=self.diameter.value(),
                       hub_field=self.hub_field.currentField(), diameter_field=self.diameter_field.currentField(),
                       target=self.target.currentData(), use_nmpt=self.use_nmpt.isChecked(),
                       detail_mode=self.detail_mode.currentData(), detail_centers=self.detail_centers.currentData(),
                       detail_radius=detail_radius, height=self.height.currentText(), curvature=self.curvature.isChecked(),
                       refraction=1 / 7, tolerance=0.25, auto_download=self.auto_download.isChecked(),
                       workers=self.workers.value(), pixels=1024,
                       folders={r: folders[r] for r in ('NMT', 'NMPT')}, report_folder=folders['reports'],
                       turbines_ids=turbines.selectedFeatureIds() if self.selected_turbines.isChecked() else None,
                       receivers_ids=receivers.selectedFeatureIds() if self.selected_receivers.isChecked() else None,
                       turbine_layer=turbines.name(), receiver_layer=receivers.name())
        return turbines, receivers, options

    def start(self):
        if self.task:
            return
        try:
            turbines, receivers, options = self.options()
            self.task = VisibilityTask(QgsVectorLayerFeatureSource(turbines), turbines.crs(),
                                       QgsVectorLayerFeatureSource(receivers), receivers.crs(),
                                       QgsCoordinateTransformContext(QgsProject.instance().transformContext()), options)
        except Exception as exc:
            QMessageBox.warning(self, 'Widoczność — ustawienia', str(exc))
            return
        for resource in ('NMT', 'NMPT'):
            if resource == 'NMT' or options['use_nmpt']:
                self.settings.setValue('nmt_nmpt/' + resource.lower() + '_folder', options['folders'][resource])
        self.settings.setValue('nmt_nmpt/report_folder', options['report_folder'])
        self.settings.setValue('nmt_nmpt/visibility/radius', options['radius'])
        self.inputs.setEnabled(False)
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.map_button.setEnabled(False)
        self.report_button.setEnabled(False)
        self.last_report = None
        self.log.clear()
        self.progress.setRange(0, 0)
        self.task.stats.connect(self.update_stats)
        self.task.message.connect(self.log.appendPlainText)
        self.task.completed.connect(self.finished)
        if self.coverage_manager:
            for resource in ('NMT', 'NMPT'):
                if resource == 'NMT' or options['use_nmpt']:
                    try:
                        self.coverage_manager.ensure(options['folders'][resource], resource)
                    except Exception as exc:
                        self.log.appendPlainText('Indeks folderu: ' + str(exc))
        QgsApplication.taskManager().addTask(self.task)

    def update_stats(self, stats):
        self.stage.setText(stats['stage'] + f' | {stats["done"]}/{stats["total"]} | czas {duration(stats["elapsed"])}')
        if stats['total']:
            self.progress.setRange(0, 10000)
            fraction = stats.get('fraction_done', stats['done'] / stats['total'])
            self.progress.setValue(int(10000 * fraction))
            if self.task:
                self.task.setProgress(100 * fraction)
        else:
            self.progress.setRange(0, 0)
        if stats.get('kind') == 'download':
            active = '; '.join(f'{r["file"]}: {r["phase"]}' for r in stats['active']) or '—'
            self.statistics.setText(f'{stats["resource"]} | pobrano {stats["bytes"] / 1e6:.1f} MB (łącznie {stats["all_bytes"] / 1e6:.1f} MB) | '
                                    f'pozostało ≈ {stats["remaining_estimate"] / 1e6:.1f} MB | '
                                    f'{stats["speed"] / 1e6:.2f} MB/s | ETA etapu ≈ {duration(stats["eta"])}\n{active}')
        else:
            counts = '; '.join(f'{LABELS[k]}: {v}' for k, v in stats['counts'].items())
            self.statistics.setText(f'ETA analizy ≈ {duration(stats["eta"])} | {counts}')

    def cancel(self):
        if self.task:
            self.task.cancel()
            self.cancel_button.setEnabled(False)
            self.stage.setText('Anulowanie… aktywne połączenie może czekać do 90 s; gotowe wyniki zostaną zachowane')

    def finished(self, report):
        self.task = None
        self.last_report = report
        self.inputs.setEnabled(True)
        self.update_detail()
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.map_button.setEnabled(bool(report.get('gpkg')))
        self.report_button.setEnabled(bool(report.get('report_dir')))
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if report['state'].startswith('completed') else 0)
        counts = '\n'.join(f'{LABELS[k]}: {v}' for k, v in report.get('counts', {}).items())
        text = {'completed': 'Analiza wykonana', 'completed_with_gaps': 'Analiza zakończona — sprawdź braki / niejednoznaczne punkty',
                'canceled': 'Analiza anulowana', 'failed': 'Błąd analizy'}[report['state']]
        self.stage.setText(text)
        text += '\n' + counts
        if report.get('fatal_error'):
            text += '\n' + report['fatal_error']
        if report.get('report_dir'):
            text += '\nRaport: ' + report['report_dir']
        if self.coverage_manager:
            self.coverage_manager.refresh_all()
        self.log.appendPlainText(text)
        if report['state'] == 'completed':
            QMessageBox.information(self, 'Widoczność NMPT', text)
        else:
            QMessageBox.warning(self, 'Widoczność NMPT', text)

    def show_results(self):
        try:
            add_results(self.last_report or {})
        except Exception as exc:
            QMessageBox.warning(self, 'Widoczność NMPT', str(exc))

    def open_report(self):
        if self.last_report and self.last_report.get('report_dir'):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.last_report['report_dir']))

    def closeEvent(self, event):
        self.hide()
        event.ignore()
