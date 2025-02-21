from enum import Enum
from math import floor
from pathlib import Path
from PySide6.QtCore import (QEvent, QModelIndex, QObject, QPoint, QPointF,
                            QRect, QRectF, QSize, QSizeF, Qt, Signal, Slot)
from PySide6.QtGui import (QCursor, QColor, QPainter, QPainterPath, QPen,
                           QPixmap, QTransform)
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsPixmapItem,
                               QGraphicsRectItem, QGraphicsScene, QGraphicsView,
                               QVBoxLayout, QWidget)
from utils.settings import settings
from models.proxy_image_list_model import ProxyImageListModel
from utils.image import Image
import utils.target_dimension as target_dimension
from dialogs.export_dialog import BucketStrategy

class ImageMarking(str, Enum):
    CROP = 'crop'
    HINT = 'hint'
    INCLUDE = 'include in mask'
    EXCLUDE = 'exclude from mask'

class RectPosition(str, Enum):
    TL = 'top left'
    TOP = 'top'
    TR = 'top right'
    RIGHT = 'right'
    BR = 'bottom right'
    BOTTOM = 'bottom'
    BL = 'bottom left'
    LEFT = 'left'

class RectItemSignal(QObject):
    change = Signal(QGraphicsRectItem, name='markingChanged')

class CustomRectItem(QGraphicsRectItem):
    # the halfed size of the pen in local coordinates to make sure it stays the
    # same during zooming
    pen_half_width = 1.0
    # the minimal size of the active area in scene coordinates
    handle_half_size = 5
    zoom_factor = 1.0
    # The size of the image this rect belongs to
    image_size = QRectF(0, 0, 1, 1)

    def __init__(self, rect: QRect, rect_type: ImageMarking, target_size: QSize=None, parent=None):
        super().__init__(rect.toRectF(), parent)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)
        self.setAcceptHoverEvents(True)
        self.signal = RectItemSignal()
        self.rect_type = rect_type
        self.color = {
            ImageMarking.CROP: Qt.blue,
            ImageMarking.HINT: Qt.gray,
            ImageMarking.INCLUDE: Qt.green,
            ImageMarking.EXCLUDE: Qt.red,
            }[rect_type]
        self.target_size = target_size
        self.handle_selected = None
        self.mouse_press_pos = None
        self.mouse_press_rect = None

    def change_pen_half_width(self):
        self.prepareGeometryChange()

    def handleAt(self, point: QPointF) -> RectPosition | None:
        handle_space = -min(self.pen_half_width - self.handle_half_size, 0)/self.zoom_factor
        left = point.x() < self.rect().left() + handle_space
        right = point.x() > self.rect().right() - handle_space
        top = point.y() < self.rect().top() + handle_space
        bottom = point.y() > self.rect().bottom() - handle_space
        if top:
            if left:
                return RectPosition.TL
            elif right:
                return RectPosition.TR
            return RectPosition.TOP
        elif bottom:
            if left:
                return RectPosition.BL
            elif right:
                return RectPosition.BR
            return RectPosition.BOTTOM
        if left:
            return RectPosition.LEFT
        elif right:
            return RectPosition.RIGHT

        return None

    def hoverMoveEvent(self, event):
        handle = self.handleAt(event.pos())
        if handle == RectPosition.TL or handle == RectPosition.BR:
            self.setCursor(Qt.SizeFDiagCursor)
        elif handle == RectPosition.TR or handle == RectPosition.BL:
            self.setCursor(Qt.SizeBDiagCursor)
        elif handle == RectPosition.TOP or handle == RectPosition.BOTTOM:
            self.setCursor(Qt.SizeVerCursor)
        elif handle == RectPosition.LEFT or handle == RectPosition.RIGHT:
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.OpenHandCursor)
            event.ignore()
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        self.handle_selected = self.handleAt(event.pos())
        if self.handle_selected:
            self.mouse_press_pos = event.pos()
            self.mouse_press_scene_pos = event.scenePos()
            self.mouse_press_rect = self.rect()
        else:
            event.ignore()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.handle_selected:
            rect = self.rect()
            pos_quantizised = event.scenePos().toPoint().toPointF()
            if self.handle_selected == RectPosition.TL:
                rect.setTopLeft(pos_quantizised)
                if rect.width() < 0 and rect.height() < 0:
                    self.handle_selected = RectPosition.BR
                elif rect.width() < 0:
                    self.handle_selected = RectPosition.TR
                elif rect.height() < 0:
                    self.handle_selected = RectPosition.BL
            elif self.handle_selected == RectPosition.TOP:
                rect.setTop(pos_quantizised.y())
                if rect.height() < 0:
                    self.handle_selected = RectPosition.BOTTOM
            elif self.handle_selected == RectPosition.TR:
                rect.setTopRight(pos_quantizised)
                if rect.width() < 0 and rect.height() < 0:
                    self.handle_selected = RectPosition.BL
                elif rect.width() < 0:
                    self.handle_selected = RectPosition.TL
                elif rect.height() < 0:
                    self.handle_selected = RectPosition.BR
            elif self.handle_selected == RectPosition.RIGHT:
                rect.setRight(pos_quantizised.x())
                if rect.width() < 0:
                    self.handle_selected = RectPosition.LEFT
            elif self.handle_selected == RectPosition.BR:
                rect.setBottomRight(pos_quantizised)
                if rect.width() < 0 and rect.height() < 0:
                    self.handle_selected = RectPosition.TL
                elif rect.width() < 0:
                    self.handle_selected = RectPosition.BL
                elif rect.height() < 0:
                    self.handle_selected = RectPosition.TR
            elif self.handle_selected == RectPosition.BOTTOM:
                rect.setBottom(pos_quantizised.y())
                if rect.height() < 0:
                    self.handle_selected = RectPosition.TOP
            elif self.handle_selected == RectPosition.BL:
                rect.setBottomLeft(pos_quantizised)
                if rect.width() < 0 and rect.height() < 0:
                    self.handle_selected = RectPosition.TR
                elif rect.width() < 0:
                    self.handle_selected = RectPosition.BR
                elif rect.height() < 0:
                    self.handle_selected = RectPosition.TL
            elif self.handle_selected == RectPosition.LEFT:
                rect.setLeft(pos_quantizised.x())
                if rect.width() < 0:
                    self.handle_selected = RectPosition.RIGHT

            if rect.width() == 0 or rect.height() == 0:
                self.setRect(rect)
            else:
                rect = rect.intersected(self.image_size)
                self.setRect(rect)
                self.size_changed()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.handle_selected:
            self.handle_selected = None
        self.signal.change.emit(self)
        super().mouseReleaseEvent(event)

    def paint(self, painter, option, widget=None):
        if self.rect_type == ImageMarking.CROP:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 0, 0, 127))
            path = QPainterPath()
            path.addRect(self.rect())
            to_crop = self.rect().size() - self.target_size
            path.addRect(QRectF(QPointF(self.rect().x()+to_crop.width()/2,
                                        self.rect().y()+to_crop.height()/2), self.target_size))
            painter.drawPath(path)

        pen_half_width = self.pen_half_width / self.zoom_factor
        pen = QPen(self.color, 2*pen_half_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self.rect().adjusted(-pen_half_width, -pen_half_width,
                                              pen_half_width, pen_half_width))

    def shape(self):
        path = super().shape()
        adjust = (self.pen_half_width + max(self.pen_half_width,
                                            self.handle_half_size))/self.zoom_factor
        path.addRect(self.rect().adjusted(-adjust, -adjust, adjust, adjust))
        return path

    def boundingRect(self):
        adjust = (self.pen_half_width + max(self.pen_half_width,
                                            self.handle_half_size))/self.zoom_factor
        return self.rect().adjusted(-adjust, -adjust, adjust, adjust)

    def size_changed(self):
        if self.rect_type == ImageMarking.CROP:
            bucket_strategy = settings.value('export_bucket_strategy', type=str)
            current = self.rect().size()
            if bucket_strategy == BucketStrategy.SCALE:
                self.target_size = current
            else: # CROP or CROP_SCALE
                target_width, target_height = target_dimension.get(current.toTuple())
                if current.height() * target_width / current.width() < target_height: # too wide
                    scale = current.height() / target_height
                else: # too high
                    scale = current.width() / target_width
                self.target_size = QSize(target_width*scale, target_height*scale)
                if bucket_strategy == BucketStrategy.CROP_SCALE:
                    self.target_size = (self.target_size + current.toSize())/2

class ImageViewer(QWidget):
    zoom = Signal(float, name='zoomChanged')

    def __init__(self, proxy_image_list_model: ProxyImageListModel):
        super().__init__()
        self.proxy_image_list_model = proxy_image_list_model
        CustomRectItem.pen_half_width = round(self.devicePixelRatio())
        CustomRectItem.zoom_factor = 1.0
        self.is_zoom_to_fit = True
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.view.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        settings.change.connect(self.setting_change)

        layout = QVBoxLayout()
        layout.addWidget(self.view)
        self.setLayout(layout)

        self.proxy_image_index = None
        self.rect_items: list[CustomRectItem] = []

        self.view.wheelEvent = self.wheelEvent

    @Slot()
    def load_image(self, proxy_image_index: QModelIndex):
        self.proxy_image_index = proxy_image_index
        image: Image = self.proxy_image_list_model.data(
            proxy_image_index, Qt.ItemDataRole.UserRole)

        pixmap = QPixmap(str(image.path))
        self.scene.clear()
        image_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(image_item)
        self.scene.setSceneRect(image_item.boundingRect()
                                .adjusted(-1, -1, 1, 1)) # space for rect border
        CustomRectItem.image_size = image_item.boundingRect()
        self.zoom_fit()

        if image.crop:
            self.add_rectangle(QRect(*image.crop), ImageMarking.CROP, QSize(*image.target_dimension))
        for rect in image.hints:
            self.add_rectangle(QRect(*rect), ImageMarking.HINT)
        for rect in image.includes:
            self.add_rectangle(QRect(*rect), ImageMarking.INCLUDE)
        for rect in image.excludes:
            self.add_rectangle(QRect(*rect), ImageMarking.EXCLUDE)

    @Slot()
    def setting_change(self, key, value):
        if key == 'export_bucket_strategy':
            for rect in self.rect_items:
                rect.size_changed()
            self.scene.invalidate()

    @Slot(QGraphicsRectItem)
    def marking_change(self, rect: QGraphicsRectItem):
        assert self.proxy_image_index != None
        if rect.rect_type == ImageMarking.CROP:
            image: Image = self.proxy_image_list_model.data(
                self.proxy_image_index, Qt.ItemDataRole.UserRole)
            image.thumbnail = None
            image.crop = rect.rect().getRect()
            image.target_dimension = rect.target_size.toTuple()
            self.proxy_image_list_model.dataChanged.emit(self.proxy_image_index,
                                                         self.proxy_image_index)

    @Slot()
    def zoom_in(self, center_pos: QPoint = None):
        CustomRectItem.zoom_factor = min(CustomRectItem.zoom_factor * 1.25, 16)
        self.is_zoom_to_fit = False
        self.zoom_emit()

    @Slot()
    def zoom_out(self, center_pos: QPoint = None):
        view = self.view.viewport().size()
        scene = self.scene.sceneRect()
        CustomRectItem.zoom_factor = max(CustomRectItem.zoom_factor / 1.25,
                                         min(view.width()/scene.width(),
                                             view.height()/scene.height()))
        self.is_zoom_to_fit = False
        self.zoom_emit()

    @Slot()
    def zoom_original(self):
        CustomRectItem.zoom_factor = 1.0
        self.is_zoom_to_fit = False
        self.zoom_emit()

    @Slot()
    def zoom_fit(self):
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
        CustomRectItem.zoom_factor = self.view.transform().m11()
        self.is_zoom_to_fit = True
        self.zoom_emit()

    def zoom_emit(self):
        transform = self.view.transform()
        self.view.setTransform(QTransform(
            CustomRectItem.zoom_factor, transform.m12(), transform.m13(),
            transform.m21(), CustomRectItem.zoom_factor, transform.m23(),
            transform.m31(), transform.m32(), transform.m33()))
        if self.is_zoom_to_fit:
            self.zoom.emit(-1)
        else:
            self.zoom.emit(CustomRectItem.zoom_factor)

    def wheelEvent(self, event):
        old_pos = self.view.mapToScene(event.position().toPoint())

        if event.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()

        new_pos = self.view.mapToScene(event.position().toPoint())
        delta = new_pos - old_pos
        self.view.translate(delta.x(), delta.y())

    def add_rectangle(self, rect: QRect, rect_type: ImageMarking, size: QSize = None):
        rect_item = CustomRectItem(rect, rect_type, size)
        rect_item.signal.change.connect(self.marking_change)
        self.scene.addItem(rect_item)
        self.rect_items.append(rect_item)

    def resizeEvent(self, event):
        super().resizeEvent(event)
