"""One shared workflow: data, independent circular models and optional project context."""
from pathlib import Path

from qgis.PyQt.QtCore import QSettings, QUrl, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea,
    QSpinBox, QTableWidget, QVBoxLayout, QWidget,
)
from qgis.core import (QgsApplication, QgsCoordinateTransformContext, QgsFieldProxyModel,
                       QgsMapLayerProxyModel, QgsProject, QgsTask, QgsVectorLayerFeatureSource)
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
        self.report_dir = None
        self.atlas_layers = {}
        self.running_atlas = True
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
        hide = QPushButton('Ukryj')
        for button in [self.start_button, self.cancel_button, self.map_button, self.report_button, hide]:
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.cancel_button.setEnabled(False)
        self.map_button.setEnabled(False)
        self.report_button.setEnabled(False)
        self.start_button.clicked.connect(self.start)
        self.cancel_button.clicked.connect(self.cancel)
        self.map_button.clicked.connect(self.show_result)
        self.report_button.clicked.connect(self.open_report)
        hide.clicked.connect(self.hide)
        self.mode.currentIndexChanged.connect(self.mode_changed)
        for panel in self.panels.values():
            panel.analysis_radius.valueChanged.connect(self.update_estimate)
            panel.step.currentTextChanged.connect(self.update_estimate)
            panel.enabled.toggled.connect(self.update_estimate)
        self.show_advanced(False)
        self.mode_changed()

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
        for widget in [self.turbine_box, self.context_box, self.auto_download, self.curvature, self.show_after, self.export_after]:
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
        for role, combo in self.context_layers.items():
            other = combo.currentLayer()
            if other is not None:
                if not other.crs().isValid():
                    raise ValueError('Brak CRS warstwy: ' + other.name())
                contexts[role] = (QgsVectorLayerFeatureSource(other), other.crs())
        opts = dict(common, models=models, source_settings=source_settings, turbines_ids=ids,
                    hub=self.hub.value(), diameter=self.diameter.value(), hub_field=self.hub_field.currentField(),
                    diameter_field=self.diameter_field.currentField(), eye=self.eye.value(),
                    auto_download=self.auto_download.isChecked(), curvature=self.curvature.isChecked())
        return layer, opts, contexts

    def start(self):
        if self.task:
            return
        try:
            layer, options, contexts = self.options()
            self.running_atlas = self.mode.currentIndex() == 0
            context = QgsCoordinateTransformContext(QgsProject.instance().transformContext())
            source = QgsVectorLayerFeatureSource(layer)
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
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.map_button.setEnabled(False)
        self.report_button.setEnabled(False)
        self.last_report = None
        self.atlas_layers = {}
        self.log.clear()
        self.progress.setRange(0, 0)
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

    def update_stats(self, stats):
        if stats.get('kind') == 'download' or 'bytes' in stats:
            DownloadDialog.update_stats(self, stats)
            if stats.get('all_bytes') is not None:
                self.stats_label.setText(self.stats_label.text() + f'\nŁączny transfer zadania: {stats["all_bytes"] / 1e6:.1f} MB')
            return
        self.active.setRowCount(0)
        self.stage.setText(stats['stage'])
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
        if self.running_atlas and report['state'].startswith('completed') and (self.show_after.isChecked() or self.export_after.isChecked()):
            self.stage.setText('Prezentacja atlasu — legendy, mapy PDF / PNG i raport HTML…')
            QgsApplication.processEvents()
            try:
                from .atlas_presentation import add_atlas, export_atlas
                self.atlas_layers = add_atlas(report, self.iface if self.show_after.isChecked() else None,
                                              show=self.show_after.isChecked())
                if self.export_after.isChecked():
                    presentation = export_atlas(report, self.atlas_layers)
                    if not presentation.get('pdf') or not presentation.get('png'):
                        self.log.appendPlainText('Sprawdź eksport map: ' + str(presentation))
            except Exception as exc:
                self.log.appendPlainText('Wyniki obliczono; problem prezentacji: ' + str(exc))
                report['presentation_error'] = str(exc)
        text = {'completed': 'Gotowe — atlas wykonany' if self.running_atlas else 'Pobieranie wykonane',
                'completed_with_gaps': 'Zakończono — sprawdź oznaczone braki danych',
                'canceled': 'Anulowano; ukończone wyniki zachowano', 'failed': 'Zadanie nie powiodło się'}[report['state']]
        if report.get('fatal_error'):
            text += '\n' + report['fatal_error']
        if report.get('presentation_error'):
            text += '\nProblem prezentacji: ' + report['presentation_error']
        self.stage.setText(text)
        self.log.appendPlainText(text)
        self.inputs.setEnabled(True)
        self.start_button.setEnabled(True)
        if report['state'] == 'completed' and not report.get('presentation_error'):
            QMessageBox.information(self, PLUGIN_NAME, text)
        else:
            QMessageBox.warning(self, PLUGIN_NAME, text)

    def cancel(self):
        if self.task:
            self.task.cancel()
            self.cancel_button.setEnabled(False)
            self.stage.setText('Anulowanie… zachowuję ukończone pliki; aktywne połączenie może czekać do 90 s')

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
