"""Place a photograph and its viewing direction using a drag or two map clicks."""
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.core import QgsPointXY, QgsWkbTypes
from qgis.gui import QgsMapTool, QgsRubberBand, QgsVertexMarker


class PhotoDirectionTool(QgsMapTool):
    picked = pyqtSignal(object, object)
    canceled = pyqtSignal()

    def __init__(self, canvas):
        super().__init__(canvas)
        self.start, self.pressed, self.second, self.done = None, None, False, False
        self.band = QgsRubberBand(canvas, QgsWkbTypes.LineGeometry)
        self.band.setColor(QColor('#16bda5'))
        self.band.setWidth(3)
        self.marker = QgsVertexMarker(canvas)
        self.marker.setColor(QColor('#16bda5'))
        self.marker.setIconType(QgsVertexMarker.ICON_CIRCLE)
        self.marker.setIconSize(12)
        self.marker.setPenWidth(3)
        self.marker.hide()
        self.setCursor(Qt.CrossCursor)

    def canvasPressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.canceled.emit()
            return
        if event.button() != Qt.LeftButton:
            return
        self.pressed = event.pos()
        self.second = self.start is not None
        if self.start is None:
            self.start = QgsPointXY(event.mapPoint())
            self.marker.setCenter(self.start)
            self.marker.show()
        self.preview(event.mapPoint())

    def canvasMoveEvent(self, event):
        if self.start is not None:
            self.preview(event.mapPoint())

    def preview(self, point):
        self.band.reset(QgsWkbTypes.LineGeometry)
        self.band.addPoint(self.start, False)
        self.band.addPoint(point, True)

    def canvasReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or self.start is None or self.pressed is None:
            return
        moved = (event.pos() - self.pressed).manhattanLength()
        if self.second or moved >= 6:
            end = QgsPointXY(event.mapPoint())
            if end != self.start:
                self.done = True
                self.picked.emit(self.start, end)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.canceled.emit()
        else:
            super().keyPressEvent(event)

    def deactivate(self):
        super().deactivate()
        if not self.done:
            self.canceled.emit()

    def cleanup(self):
        self.done = True
        self.canvas().scene().removeItem(self.band)
        self.canvas().scene().removeItem(self.marker)
