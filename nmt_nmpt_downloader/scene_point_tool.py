"""A one-click map position, cancelable with Escape."""
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.gui import QgsMapToolEmitPoint


class ScenePointTool(QgsMapToolEmitPoint):
    canceled = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.canceled.emit()
        else:
            super().keyPressEvent(event)
