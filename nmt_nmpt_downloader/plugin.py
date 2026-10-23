"""Polish QGIS dialog; all network and spatial work runs in QgsTask."""
from pathlib import Path
import json
import re

from qgis.PyQt.QtCore import QSettings, Qt, QUrl, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices, QIcon
try:
    from qgis.PyQt.QtGui import QAction
except ImportError:
    from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QScrollArea, QVBoxLayout, QWidget,
)
from qgis.core import (
    QgsApplication, QgsCoordinateTransformContext, QgsMapLayerProxyModel,
    QgsProject, QgsTask, QgsVectorLayerFeatureSource,
)
from qgis.gui import QgsMapLayerComboBox

from .engine import Engine
from .core import PLUGIN_NAME, STATUS_LABELS
from .catalog import HEIGHTS
from .coverage import CoverageManager


def duration(seconds):
    if seconds is None:
        return '—'
    seconds = max(0, int(seconds))
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f'{hours:d}:{minutes:02d}:{seconds:02d}'


class DownloadTask(QgsTask):
    stats = pyqtSignal(object)
    message = pyqtSignal(str)
    completed = pyqtSignal(object)

    def __init__(self, source, crs, context, options):
        super().__init__(PLUGIN_NAME, QgsTask.CanCancel)
        self.engine = Engine(source, crs, context, options, self.stats.emit, self.message.emit)
        self.result = None

    def run(self):
        self.result = self.engine.run()
        return self.result['state'] != 'failed'

    def cancel(self):
        self.engine.cancel_event.set()
        super().cancel()

    def finished(self, success):
        self.completed.emit(self.result or {'state': 'failed', 'fatal_error': 'Zadanie nie zostało uruchomione'})


class FolderChooser(QWidget):
    def __init__(self, value=''):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit(value)
        button = QPushButton('Wybierz…')
        button.clicked.connect(self.choose)
        layout.addWidget(self.edit)
        layout.addWidget(button)

    def choose(self):
        directory = QFileDialog.getExistingDirectory(self, 'Folder docelowy', self.edit.text())
        if directory:
            self.edit.setText(directory)

    def value(self):
        return self.edit.text().strip()


class CatalogTask(QgsTask):
    completed = pyqtSignal(object)

    def __init__(self):
        super().__init__('Sprawdzanie wariantów NMT / NMPT', QgsTask.CanCancel)
        self.engine = Engine(None, None, None, {'resources': ['NMT', 'NMPT']})
        self.result = None

    def run(self):
        try:
            variants, descriptions, errors = self.engine.discover()
            self.result = dict(variants=[v.as_dict() for v in variants], errors=errors)
            return True
        except Exception as exc:
            self.result = dict(variants=[], errors=[dict(error=str(exc))])
            return False

    def cancel(self):
        self.engine.cancel_event.set()
        super().cancel()

    def finished(self, success):
        self.completed.emit(self.result or dict(variants=[], errors=[]))


class ResourceControls(QGroupBox):
    def __init__(self, resource, settings):
        super().__init__(resource)
        self.resource = resource
        form = QFormLayout(self)
        self.folder = FolderChooser(settings.value(f'nmt_nmpt/{resource.lower()}_folder', ''))
        form.addRow('Folder:', self.folder)
        self.resolution = QComboBox()
        self.resolution.setEditable(True)
        self.resolution.addItem('Źródłowa — najlepsza dostępna', 0.0)
        for value in ([1.0, 5.0] if resource == 'NMT' else [0.5, 1.0]):
            self.resolution.addItem(f'{value:g} m (sprawdź dostępność)', value)
        preferred = float(settings.value(f'nmt_nmpt/{resource}/resolution', 1 if resource == 'NMT' else 0.5))
        self.select_resolution(preferred)
        form.addRow('Preferowany piksel:', self.resolution)
        self.strict = QCheckBox('Tylko wybrana rozdzielczość')
        self.strict.setChecked(settings.value(f'nmt_nmpt/{resource}/strict_resolution', False, type=bool))
        self.strict.setToolTip('Po zaznaczeniu brak dokładnie takiej rozdzielczości oznacza brak pobrania. Bez zaznaczenia wtyczka próbuje najbliższej dostępnej.')
        form.addRow(self.strict)
        self.height = QComboBox()
        self.height.addItems(HEIGHTS)
        self.height.setCurrentText(settings.value(f'nmt_nmpt/{resource}/height', HEIGHTS[0]))
        form.addRow('Układ wysokościowy:', self.height)
        self.alternate = QCheckBox('Przy brakach sprawdź też drugi układ')
        self.alternate.setChecked(settings.value(f'nmt_nmpt/{resource}/alternate_height', False, type=bool))
        self.alternate.setToolTip('Zamiennik zachowuje własny układ w nazwie i raporcie. Wtyczka nie przelicza wysokości ani nie łączy różnych układów.')
        form.addRow(self.alternate)

    def select_resolution(self, value):
        index = self.resolution.findData(value)
        if index < 0:
            self.resolution.addItem(f'{value:g} m (preferencja)', value)
            index = self.resolution.count() - 1
        self.resolution.setCurrentIndex(index)

    def chosen_resolution(self):
        text = self.resolution.currentText()
        if text.startswith('Źródłowa'):
            return 0.0
        match = re.match(r'\s*(\d+(?:[.,]\d+)?)', text)
        if not match or not 0.05 <= float(match.group(1).replace(',', '.')) <= 1000:
            raise ValueError(f'{self.resource}: wybierz dodatnią rozdzielczość w metrach')
        return float(match.group(1).replace(',', '.'))

    def options(self):
        return dict(resolution=self.chosen_resolution(), height=self.height.currentText(),
                    strict_resolution=self.strict.isChecked(), alternate_height=self.alternate.isChecked())

    def update_catalog(self, variants):
        try:
            preferred = self.chosen_resolution()
        except ValueError:
            preferred = 0.0
        values = sorted({v['resolution'] for v in variants if v['resource'] == self.resource})
        self.resolution.clear()
        self.resolution.addItem('Źródłowa — najlepsza dostępna', 0.0)
        for value in values:
            self.resolution.addItem(f'{value:g} m', value)
        self.select_resolution(preferred)


class DownloadDialog(QDialog):
    def __init__(self, iface, coverage_manager=None, open_visibility=None):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self.task = None
        self.report_dir = None
        self.settings = QSettings()
        self.coverage_manager = coverage_manager
        self.catalog_task = None
        self.last_report = None
        self.setWindowTitle(PLUGIN_NAME)
        self.resize(1000, 850)
        layout = QVBoxLayout(self)
        if open_visibility is not None:
            visibility_button = QPushButton('Nowe: analiza widoczności turbin z NMPT…')
            visibility_button.clicked.connect(open_visibility)
            layout.addWidget(visibility_button)
        self.inputs = QGroupBox('Obszar i dane')
        form = QFormLayout(self.inputs)
        self.layer = QgsMapLayerComboBox()
        self.layer.setFilters(QgsMapLayerProxyModel.VectorLayer)
        current = iface.activeLayer()
        if current is not None:
            self.layer.setLayer(current)
        form.addRow('Warstwa wejściowa:', self.layer)
        self.selected = QCheckBox('Tylko zaznaczone obiekty (w przeciwnym razie cała warstwa)')
        form.addRow('', self.selected)
        self.radius = QDoubleSpinBox()
        self.radius.setRange(0, 200000)
        self.radius.setDecimals(1)
        self.radius.setSuffix(' m')
        self.radius.setValue(float(self.settings.value('nmt_nmpt/radius', 20000)))
        form.addRow('Promień wokół geometrii:', self.radius)
        self.nmt = QCheckBox('NMT — teren')
        self.nmpt = QCheckBox('NMPT — teren i pokrycie')
        self.nmt.setChecked(False)
        self.nmpt.setChecked(True)
        kinds = QWidget()
        kinds_layout = QHBoxLayout(kinds)
        kinds_layout.setContentsMargins(0, 0, 0, 0)
        kinds_layout.addWidget(self.nmt)
        kinds_layout.addWidget(self.nmpt)
        form.addRow('Zasoby:', kinds)
        self.resource_controls = {r: ResourceControls(r, self.settings) for r in ('NMT', 'NMPT')}
        panels = QWidget()
        panel_layout = QHBoxLayout(panels)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        for panel in self.resource_controls.values():
            panel_layout.addWidget(panel)
        form.addRow(panels)
        self.nmt_folder = self.resource_controls['NMT'].folder
        self.nmpt_folder = self.resource_controls['NMPT'].folder
        self.report_folder = FolderChooser(self.settings.value('nmt_nmpt/report_folder', ''))
        form.addRow('Folder raportów:', self.report_folder)
        self.catalog_button = QPushButton('Sprawdź dostępne rozdzielczości i układy')
        self.catalog_button.clicked.connect(self.refresh_catalog)
        form.addRow(self.catalog_button)
        self.catalog_label = QLabel('Przed pobraniem dostępność jest sprawdzana ponownie. Możesz też wpisać preferowany piksel.\n'
                                    'Bez „Tylko wybrana” niedostępna rozdzielczość zostanie zastąpiona najbliższą źródłową.')
        self.catalog_label.setWordWrap(True)
        form.addRow(self.catalog_label)
        self.workers = QSpinBox()
        self.workers.setRange(1, 4)
        self.workers.setValue(2)
        form.addRow('Pobierania równoległe:', self.workers)
        self.pixels = QComboBox()
        for value in (1024, 512, 2048):
            self.pixels.addItem(f'{value} × {value} pikseli', value)
        form.addRow('Wielkość kafla:', self.pixels)
        self.reuse = QCheckBox('Pomijaj istniejące pliki po sprawdzeniu zgodności i odczytu rastra')
        self.reuse.setChecked(True)
        form.addRow('', self.reuse)
        hint = QLabel('Wynik: GeoTIFF Float32, EPSG:2180. Pełne kafle mogą wykraczać poza bufor.\n'
                      'Indeksy folderów aktualizują się automatycznie; dodanie rastrów jest osobną opcją.\n'
                      'Duży obszar przy 1 m może oznaczać wiele GB danych. Braki i błędy nie zatrzymują innych kafli.')
        hint.setWordWrap(True)
        form.addRow(hint)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.inputs)
        scroll.setMinimumHeight(360)
        layout.addWidget(scroll, 2)
        self.stage = QLabel('Gotowe do rozpoczęcia')
        layout.addWidget(self.stage)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.stats_label = QLabel('Pobrano: 0 MB | Pozostało: — | Prędkość: — | ETA: —')
        self.stats_label.setWordWrap(True)
        layout.addWidget(self.stats_label)
        self.active = QTableWidget(0, 4)
        self.active.setHorizontalHeaderLabels(['Zasób', 'Kafel', 'Etap', 'MB w bieżącej próbie'])
        self.active.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.active.horizontalHeader().setStretchLastSection(True)
        self.active.setMaximumHeight(135)
        layout.addWidget(self.active)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        layout.addWidget(self.log, 1)
        map_buttons = QHBoxLayout()
        self.index_button = QPushButton('Pokaż / odśwież indeksy folderów')
        self.index_button.clicked.connect(self.show_indexes)
        self.map_button = QPushButton('Pokaż pobrane rastry na mapie')
        self.map_button.setEnabled(False)
        self.map_button.clicked.connect(self.show_rasters)
        map_buttons.addWidget(self.index_button)
        map_buttons.addWidget(self.map_button)
        layout.addLayout(map_buttons)
        buttons = QHBoxLayout()
        self.start_button = QPushButton('Pobierz')
        self.start_button.clicked.connect(self.start)
        self.cancel_button = QPushButton('Anuluj')
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        self.report_button = QPushButton('Otwórz raporty')
        self.report_button.setEnabled(False)
        self.report_button.clicked.connect(self.open_reports)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch()
        buttons.addWidget(self.report_button)
        close = QPushButton('Ukryj')
        close.clicked.connect(self.hide)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.nmt.toggled.connect(self.resource_controls['NMT'].setEnabled)
        self.nmpt.toggled.connect(self.resource_controls['NMPT'].setEnabled)
        self.resource_controls['NMT'].setEnabled(self.nmt.isChecked())
        self.resource_controls['NMPT'].setEnabled(self.nmpt.isChecked())

    def refresh_catalog(self):
        self.catalog_button.setEnabled(False)
        self.catalog_label.setText('Sprawdzanie usług WCS…')
        self.catalog_task = CatalogTask()
        self.catalog_task.completed.connect(self.catalog_ready)
        QgsApplication.taskManager().addTask(self.catalog_task)

    def catalog_ready(self, result):
        self.catalog_task = None
        self.catalog_button.setEnabled(True)
        text = []
        for resource, panel in self.resource_controls.items():
            panel.update_catalog(result['variants'])
            variants = [v for v in result['variants'] if v['resource'] == resource]
            text.append(resource + ': ' + (', '.join(f'{v["resolution"]:g} m / {v["height"]}' for v in variants) or 'brak dostępnych wariantów'))
        self.catalog_label.setText('\n'.join(text))
        for error in result['errors']:
            self.log.appendPlainText('Katalog WCS: ' + error['error'])

    def show_indexes(self):
        if self.coverage_manager is None:
            return
        try:
            for resource, checkbox in [('NMT', self.nmt), ('NMPT', self.nmpt)]:
                if checkbox.isChecked():
                    folder = self.resource_controls[resource].folder.value()
                    if not folder:
                        raise ValueError('Wybierz folder ' + resource)
                    self.coverage_manager.ensure(folder, resource)
        except Exception as exc:
            QMessageBox.warning(self, 'Indeks kafli', str(exc))

    def show_rasters(self):
        if self.coverage_manager and self.last_report:
            self.coverage_manager.show_results(self.last_report)

    def options(self):
        layer = self.layer.currentLayer()
        if layer is None or not layer.isValid() or not layer.crs().isValid():
            raise ValueError('Wybierz poprawną warstwę wektorową z określonym układem współrzędnych.')
        resources = [r for r, box in [('NMT', self.nmt), ('NMPT', self.nmpt)] if box.isChecked()]
        if not resources:
            raise ValueError('Zaznacz NMT lub NMPT.')
        folders = {'NMT': self.nmt_folder.value(), 'NMPT': self.nmpt_folder.value()}
        for resource in resources:
            if not folders[resource]:
                raise ValueError('Wybierz folder dla ' + resource)
            folders[resource] = str(Path(folders[resource]).expanduser().resolve())
        if len(resources) == 2 and folders['NMT'] == folders['NMPT']:
            raise ValueError('Wybierz różne foldery dla NMT i NMPT.')
        selected = list(layer.selectedFeatureIds()) if self.selected.isChecked() else None
        if selected == []:
            raise ValueError('Brak zaznaczonych obiektów. Zaznacz obiekty albo wyłącz ograniczenie do zaznaczenia.')
        if layer.featureCount() == 0:
            raise ValueError('Warstwa jest pusta.')
        if not self.report_folder.value():
            raise ValueError('Wybierz folder raportów.')
        options = {'radius': self.radius.value(), 'resources': resources, 'folders': folders,
                   'report_folder': str(Path(self.report_folder.value()).expanduser().resolve()),
                   'feature_ids': selected, 'resource_settings': {r: self.resource_controls[r].options() for r in resources},
                   'workers': self.workers.value(),
                   'pixels': self.pixels.currentData(), 'reuse': self.reuse.isChecked(),
                   'layer_name': layer.name(), 'layer_crs': layer.crs().authid()}
        return layer, options

    def start(self):
        try:
            layer, options = self.options()
            source = QgsVectorLayerFeatureSource(layer)  # snapshot created in the main thread
            context = QgsCoordinateTransformContext(QgsProject.instance().transformContext())
            self.task = DownloadTask(source, layer.crs(), context, options)
            if self.coverage_manager:
                for resource in options['resources']:
                    self.coverage_manager.ensure(options['folders'][resource], resource)
        except Exception as exc:
            QMessageBox.warning(self, 'Nie można rozpocząć', str(exc))
            return
        for name, value in [('radius', options['radius']), ('nmt_folder', self.nmt_folder.value()),
                            ('nmpt_folder', self.nmpt_folder.value()), ('report_folder', self.report_folder.value())]:
            self.settings.setValue('nmt_nmpt/' + name, value)
        for resource, values in options['resource_settings'].items():
            for name, value in values.items():
                self.settings.setValue(f'nmt_nmpt/{resource}/{name}', value)
        self.report_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.inputs.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setRange(0, 0)
        self.log.clear()
        self.map_button.setEnabled(False)
        self.task.stats.connect(self.update_stats)
        self.task.message.connect(self.log.appendPlainText)
        self.task.completed.connect(self.finished)
        QgsApplication.taskManager().addTask(self.task)

    def cancel(self):
        if self.task:
            self.task.cancel()
            self.cancel_button.setEnabled(False)
            self.stage.setText('Anulowanie… oczekiwanie na zakończenie aktywnych połączeń (limit 90 s)')

    def update_stats(self, stats):
        counts = ', '.join(f'{STATUS_LABELS[k]}: {v}' for k, v in stats['counts'].items()) or '—'
        self.stage.setText(f'{stats["stage"]} | Kafle: {stats["done"]} / {stats["total"]} | '
                           f'Czas: {duration(stats["elapsed"])}')
        if stats['total']:
            self.progress.setRange(0, 10000)
            self.progress.setValue(int(10000 * stats['fraction_done']))
            if self.task:
                self.task.setProgress(100 * stats['fraction_done'])
        self.stats_label.setText(
            f'Pobrano przez sieć: {stats["bytes"] / 1e6:.1f} MB | '
            f'Pozostało ≈ {stats["remaining_estimate"] / 1e6:.1f} MB | '
            f'Prędkość średnia: {stats["speed"] / 1e6:.2f} MB/s | ETA ≈ {duration(stats["eta"])}\n'
            f'Stany kafli: {counts}. Rozmiar pozostały i ETA są szacunkowe; pobrane MB obejmują ponowienia.')
        self.active.setRowCount(len(stats['active']))
        for row, item in enumerate(stats['active']):
            for col, value in enumerate([item['resource'], item['file'], item['phase'],
                                         f'{item["bytes"] / 1e6:.2f}' + (f' / {item["expected"] / 1e6:.2f}' if item['expected'] else '')]):
                self.active.setItem(row, col, QTableWidgetItem(str(value)))
        self.active.resizeColumnsToContents()

    def finished(self, result):
        self.task = None
        self.last_report = result
        self.map_button.setEnabled(any(r.get('files') or (r.get('file') and r.get('status') in ('downloaded', 'reused', 'partial'))
                                       for r in result.get('tiles', [])))
        if self.coverage_manager:
            self.coverage_manager.refresh_all()
        self.inputs.setEnabled(True)
        self.nmt_folder.setEnabled(self.nmt.isChecked())
        self.nmpt_folder.setEnabled(self.nmpt.isChecked())
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if result['state'].startswith('completed') else 0)
        self.report_dir = result.get('report_dir')
        self.report_button.setEnabled(bool(self.report_dir))
        states = {'completed': 'Zadanie wykonane', 'completed_with_gaps': 'Zadanie wykonane — są braki lub błędy',
                  'failed': 'Zadanie nie powiodło się', 'canceled': 'Zadanie anulowane'}
        counts = ', '.join(f'{STATUS_LABELS[k]}: {v}' for k, v in result.get('counts', {}).items())
        text = states[result['state']] + '\n' + counts
        if result.get('fatal_error'):
            text += '\n' + result['fatal_error']
        if self.report_dir:
            text += '\nRaporty: ' + self.report_dir
        self.stage.setText(states[result['state']])
        self.log.appendPlainText(text)
        if result['state'] == 'completed':
            QMessageBox.information(self, PLUGIN_NAME, text)
        else:
            QMessageBox.warning(self, PLUGIN_NAME, text)

    def open_reports(self):
        if self.report_dir:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.report_dir))

    def closeEvent(self, event):
        # Closing the window never destroys a running task or silently cancels downloads.
        self.hide()
        event.ignore()


class TerrainPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.dialog = None
        self.action = None
        self.coverage_manager = None
        self.visibility_dialog = None
        self.visibility_action = None

    def initGui(self):
        self.coverage_manager = CoverageManager(self.iface)
        self.action = QAction(QIcon(str(Path(__file__).with_name('icon.svg'))),
                              PLUGIN_NAME, self.iface.mainWindow())
        self.action.triggered.connect(self.open)
        self.iface.addPluginToMenu(PLUGIN_NAME, self.action)
        self.iface.addToolBarIcon(self.action)
        self.visibility_action = QAction('Widoczność turbin — NMPT', self.iface.mainWindow())
        self.visibility_action.triggered.connect(self.open_visibility)
        self.iface.addPluginToMenu(PLUGIN_NAME, self.visibility_action)

    def open(self):
        if self.dialog is None:
            self.dialog = DownloadDialog(self.iface, self.coverage_manager, self.open_visibility)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def open_visibility(self):
        from .visibility_dialog import VisibilityDialog
        if self.visibility_dialog is None:
            self.visibility_dialog = VisibilityDialog(self.iface, self.coverage_manager)
        self.visibility_dialog.show()
        self.visibility_dialog.raise_()
        self.visibility_dialog.activateWindow()

    def unload(self):
        if self.visibility_dialog:
            if self.visibility_dialog.task:
                self.visibility_dialog.task.cancel()
            self.visibility_dialog.hide()
        if self.dialog:
            if self.dialog.catalog_task:
                self.dialog.catalog_task.cancel()
            if self.dialog.task:
                self.dialog.task.cancel()
            self.dialog.hide()
        if self.coverage_manager:
            self.coverage_manager.stop()
        if self.action:
            self.iface.removePluginMenu(PLUGIN_NAME, self.action)
            self.iface.removeToolBarIcon(self.action)
        if self.visibility_action:
            self.iface.removePluginMenu(PLUGIN_NAME, self.visibility_action)
