"""Choose a layer for one specific field by clicking the QGIS layer tree."""
from qgis.PyQt.QtCore import QObject, Qt
from qgis.PyQt.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QToolButton, QVBoxLayout, QWidget
from qgis.gui import QgsMapLayerComboBox


class LayerPanelPicker(QObject):
    def __init__(self, owner, iface):
        super().__init__(owner)
        self.owner, self.iface = owner, iface
        self.target = self.notice = None
        self.return_windows = []
        self.buttons = {}
        tree = iface.layerTreeView() if hasattr(iface, 'layerTreeView') else None
        if tree is not None:
            tree.clicked.connect(self.tree_clicked)
        for combo in owner.findChildren(QgsMapLayerComboBox):
            parent = combo.parentWidget()
            if parent is None or parent.layout() is None:
                continue
            row = QWidget(parent)
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            old_item = parent.layout().replaceWidget(combo, row)
            if old_item is None:
                row.deleteLater()
                continue
            del old_item
            layout.addWidget(combo, 1)
            button = QToolButton(row)
            button.setText('↖')
            button.setToolTip('Wskaż warstwę w panelu warstw QGIS')
            button.setAccessibleName('Wskaż warstwę w panelu warstw QGIS')
            button.setProperty('layerCombo', combo)
            button.clicked.connect(self.begin_from_button)
            layout.addWidget(button)
            self.buttons[combo] = button

    def begin_from_button(self):
        self.begin(self.sender().property('layerCombo'))

    def begin(self, combo):
        if self.target is not None:
            self.finish()
        self.target = combo
        window = combo.window()
        self.return_windows = [self.owner]
        if window is not self.owner and isinstance(window, QDialog):
            self.return_windows.append(window)
        for item in reversed(self.return_windows):
            item.hide()
        notice = QDialog(self.iface.mainWindow(), Qt.Tool)
        notice.setWindowTitle('Wybierz warstwę z panelu QGIS')
        layout = QVBoxLayout(notice)
        self.message = QLabel('Kliknij nazwę warstwy w panelu warstw QGIS.\nZmieni się tylko wskazane pole formularza.')
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        cancel = QPushButton('Anuluj wybór')
        cancel.clicked.connect(notice.reject)
        layout.addWidget(cancel)
        notice.rejected.connect(self.finish)
        self.notice = notice
        notice.show()
        if hasattr(self.iface, 'layerTreeView'):
            self.iface.layerTreeView().setFocus()

    def tree_clicked(self, index):
        if self.target is None:
            return
        tree = self.iface.layerTreeView()
        node = tree.index2node(index)
        layer = node.layer() if node is not None and hasattr(node, 'layer') else None
        self.choose(layer)

    def choose(self, layer):
        if self.target is None or layer is None:
            return False
        if not layer.isValid() or not any(self.target.layer(i) is layer for i in range(self.target.count())):
            self.message.setText('Ta warstwa nie pasuje do tego pola (np. wymagane punkty, linie, poligony albo raster).\nWskaż inną warstwę lub anuluj.')
            return False
        self.target.setLayer(layer)
        self.finish()
        return True

    def finish(self, restore=True):
        self.target = None
        notice, self.notice = self.notice, None
        if notice is not None:
            notice.blockSignals(True)
            notice.hide()
            notice.deleteLater()
        windows, self.return_windows = self.return_windows, []
        for window in windows if restore else []:
            window.show()
            window.raise_()


def install_layer_pickers(owner, iface):
    owner.layer_panel_picker = LayerPanelPicker(owner, iface)
