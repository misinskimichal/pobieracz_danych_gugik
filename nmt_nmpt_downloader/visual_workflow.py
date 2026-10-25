"""A short visual workflow, with existing expert controls moved to one settings dialog."""
from qgis.PyQt.QtWidgets import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget
from qgis.core import QgsProject, QgsWkbTypes
from .core import VERSION


def transfer_rows(source, destination, keep=()):
    """Reparent existing controls without copying values or creating competing controls."""
    retained = []
    while source.rowCount():
        row = source.takeRow(0)
        field = row.fieldItem.widget() if row.fieldItem else None
        label = row.labelItem.widget() if row.labelItem else None
        if field is None:
            continue
        if field in keep:
            retained.append((label, field))
        elif label:
            destination.addRow(label, field)
        else:
            destination.addRow(field)
    for label, field in retained:
        source.addRow(label, field) if label else source.addRow(field)


def install_visual_workflow(owner):
    dialog = QDialog(owner)
    dialog.setWindowTitle('Ustawienia zaawansowane · wizualizacja i wyniki')
    dialog.resize(900, 760)
    layout = QVBoxLayout(dialog)
    scroll, body = QScrollArea(), QWidget()
    scroll.setWidgetResizable(True)
    scroll.setWidget(body)
    expert = QFormLayout(body)
    layout.addWidget(scroll)
    close = QDialogButtonBox(QDialogButtonBox.Close)
    close.rejected.connect(dialog.reject)
    layout.addWidget(close)
    owner.visual_settings = dialog
    owner.reuse_context = QCheckBox('Zachowaj zapisane obiekty sceny, jeśli brakuje ich warstw w projekcie')
    owner.reuse_context.setChecked(True)
    owner.reuse_context.toggled.connect(owner.mark_scene_dirty)
    expert.addRow(owner.reuse_context)
    root_form = owner.inputs.layout()
    for widget in (owner.context_box, owner.auto_download, owner.curvature, owner.show_after, owner.export_after):
        position = root_form.getWidgetPosition(widget)[0]
        if position >= 0:
            row = root_form.takeRow(position)
            if row.labelItem and row.labelItem.widget():
                expert.addRow(row.labelItem.widget(), widget)
            else:
                expert.addRow(widget)
    owner.hidden_visual_actions = QWidget(owner)
    owner.hidden_visual_actions.hide()
    detail = owner.detail_box.layout()
    owner.detail_box.setTitle('Wizualizacja · wybierz obraz i otwórz wynik')
    transfer_rows(detail, expert)
    # These were different buttons for the same refresh operation.
    for button in (owner.refresh_scene_button, owner.prepare_points_button):
        index = expert.getWidgetPosition(button)[0]
        if index >= 0:
            expert.takeRow(index)
        button.setParent(owner.hidden_visual_actions)
        button.hide()
    owner.visual_source = QComboBox()
    owner.visual_source.addItem('Model 3D · NMT + NMPT + ortofotomapa', 'model')
    owner.visual_source.addItem('Fotomontaż · własne zdjęcie lub kadr Street View', 'photo')
    detail.addRow('Co chcesz obejrzeć?', owner.visual_source)
    owner.model_basic = QWidget()
    model_form = QFormLayout(owner.model_basic)
    for widget, label in [(owner.texture_layer, 'Ortofotomapa:'),
                          (owner.scene_layers['lasy'], 'Lasy / zadrzewienia:'),
                          (owner.scene_layers['budynki_3d'], 'Obrysy budynków:')]:
        position = expert.getWidgetPosition(widget)[0]
        if position >= 0:
            row = expert.takeRow(position)
            if row.labelItem and row.labelItem.widget():
                row.labelItem.widget().hide()
        model_form.addRow(label, widget)
    owner.texture_layer.setAllowEmptyLayer(True, 'Geoportal · automatycznie')
    owner.texture_layer.setEnabled(True)
    for widget in (owner.collect_points_button, owner.viewpoints, owner.remove_point_button):
        position = expert.getWidgetPosition(widget)[0]
        if position >= 0:
            row = expert.takeRow(position)
            if row.labelItem and row.labelItem.widget():
                row.labelItem.widget().hide()
        model_form.addRow(widget)
    owner.collect_points_button.setText('Wskaż miejsca patrzenia na mapie')
    owner.remove_point_button.setText('Usuń wybrane miejsce')
    owner.viewpoints.hideColumn(1)
    owner.viewpoints.hideColumn(2)
    detail.addRow(owner.model_basic)
    photo_form = owner.photos.layout()
    photo_keep = (owner.photos.add_button, owner.photos.street_import_button, owner.photos.list, owner.photos.location, owner.photos.preview, owner.photos.info)
    # The file row is a container with the read-only filename and Change file button.
    file_row = owner.photos.path.parentWidget()
    transfer_rows(photo_form, expert, keep=photo_keep + (file_row,))
    for button in (owner.photos.prepare_button, owner.photos.open_button):
        # Their common row is hidden; all output goes through the main action below.
        container = button.parentWidget()
        position = expert.getWidgetPosition(container)[0]
        if position >= 0:
            expert.takeRow(position)
        container.setParent(owner.hidden_visual_actions)
        container.hide()
    owner.photos.setTitle('Zdjęcie używane w fotomontażu')
    owner.photos.add_button.setText('Dodaj zdjęcie · wskaż miejsce i kierunek na mapie')
    detail.addRow(owner.photos)
    owner.visual_readiness = QLabel()
    owner.visual_readiness.setWordWrap(True)
    detail.addRow(owner.visual_readiness)
    settings = QPushButton('Ustawienia zaawansowane…')
    settings.clicked.connect(dialog.exec)
    detail.addRow(settings)
    detail.addRow(owner.scene_button)
    # Move less frequent result actions out of the persistent footer.
    extra = QGroupBox('Pozostałe wyniki')
    result_form = QFormLayout(extra)
    for button in (owner.ray_button, owner.profile_button, owner.rerun_button):
        result_form.addRow(button)
    expert.addRow(extra)
    owner.inputs.layout().insertRow(0, owner.load_button)
    owner.visual_source.currentIndexChanged.connect(owner.visual_source_changed)
    for combo in owner.scene_layers.values():
        combo.layerChanged.connect(owner.update_visual_controls)
    owner.photos.list.currentIndexChanged.connect(owner.update_visual_controls)
    owner.photos.info.setText('Wybierz zdjęcie. Ten obraz będzie tłem fotomontażu; dopasowanie kamery otworzysz przyciskiem poniżej.')
    update_visual_workflow(owner)


def update_visual_workflow(owner):
    if not hasattr(owner, 'visual_source'):
        return
    photo = owner.visual_source.currentData() == 'photo'
    owner.model_basic.setVisible(not photo)
    owner.viewpoints.setVisible(not photo and owner.viewpoints.rowCount() > 0)
    owner.remove_point_button.setVisible(not photo and owner.viewpoints.rowCount() > 0)
    owner.photos.setVisible(photo)
    record = owner.photos.current()
    if photo:
        dirty = not record or record.get('dirty') or not record.get('html') or record.get('prepared_version') != VERSION
        owner.scene_button.setText('Utwórz fotomontaż' if dirty else 'Otwórz fotomontaż')
    else:
        dirty = owner.scene_dirty or not owner.last_report or owner.last_report.get('scene_version') != VERSION
        owner.scene_button.setText('Utwórz model 3D' if dirty else 'Otwórz model 3D')
    owner.scene_button.setEnabled(bool(owner.last_report and owner.last_report.get('products')))
    if photo:
        owner.visual_readiness.setText('Wybrane zdjęcie będzie tłem fotomontażu. Kadr dopasujesz po otwarciu.' if record else 'Najpierw dodaj zdjęcie lub zaimportuj kadr i położenie z linku Street View.')
    else:
        names = []
        for role, label in [('lasy', 'Lasy'), ('drzewa', 'Drzewa'), ('budynki_3d', 'Budynki')]:
            layer = owner.scene_layers[role].currentLayer()
            names.append(label + ': ' + (layer.name() if layer else 'brak warstwy'))
        source = dict(layer='wybrana warstwa QGIS', geoportal='Geoportal', visible='widoczne warstwy projektu (ustawienie zaawansowane)')
        owner.visual_readiness.setText('Ortofotomapa: ' + source.get(owner.texture_mode.currentData(), 'brak źródła') +
                                       '\n' + ' · '.join(names) + '\nNMPT pokazuje powierzchnię dachów i koron. Wskaż obrysy powyżej, aby uzyskać osobne budynki i korony.')
        detail = owner.preferred_detail() if owner.last_report else None
        if detail and detail.get('context_reused'):
            owner.visual_readiness.setText(owner.visual_readiness.text() + '\nZachowano budynki i korony z ostatniej zapisanej sceny tego atlasu.')


def select_scene_layers(owner, saved_names=None):
    """Only recognizable role names; never treat arbitrary parcels as buildings."""
    aliases = dict(lasy=('ptlz', 'lasy', 'las ', 'forest', 'zadrzew'),
                   drzewa=('drzewa', 'trees', 'drzewo'), budynki_3d=('bubd', 'budynki', 'buildings', 'building'))
    for role, combo in owner.scene_layers.items():
        if combo.currentLayer() is not None:
            continue
        kind = QgsWkbTypes.PointGeometry if role == 'drzewa' else QgsWkbTypes.PolygonGeometry
        candidates = []
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() != layer.VectorLayer or not layer.isValid() or layer.geometryType() != kind:
                continue
            if layer.customProperty('nmt_nmpt/atlas_run', ''):
                continue
            name = layer.name().lower()
            score = 100 if saved_names and layer.name() == saved_names.get(role) else 10 if any(a in name for a in aliases[role]) else 0
            if score:
                candidates.append((score, layer.name(), layer))
        if candidates:
            combo.setLayer(max(candidates, key=lambda p: (p[0], p[1]))[2])
    update_visual_workflow(owner)
