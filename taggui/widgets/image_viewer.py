from enum import Enum
from math import floor
from pathlib import Path
from PySide6.QtCore import (QEvent, QModelIndex, QObject, QPersistentModelIndex,
                            QPoint, QPointF, QRect, QRectF, QSize, QSizeF, Qt,
                            Signal, Slot)
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
    NONE = 'none'

def flip_rect_position(pos: RectPosition, h_flip: bool, v_flip: bool) -> RectPosition:
    if pos == RectPosition.NONE:
        return RectPosition.NONE

    if pos == RectPosition.TL or pos == RectPosition.TOP or pos == RectPosition.TR:
        v = 2 if v_flip else 0
    elif pos == RectPosition.LEFT or pos == RectPosition.RIGHT:
        v = 1
    else:
        v = 0 if v_flip else 2

    if pos == RectPosition.TL or pos == RectPosition.LEFT or pos == RectPosition.BL:
        h = 2 if h_flip else 0
    elif pos == RectPosition.TOP or pos == RectPosition.BOTTOM:
        h = 1
    else:
        h = 0 if h_flip else 2

    return {
         0: RectPosition.TL,    1: RectPosition.TOP,     2: RectPosition.TR,
        10: RectPosition.LEFT,                          12: RectPosition.RIGHT,
        20: RectPosition.BL,   21: RectPosition.BOTTOM, 22: RectPosition.BR,
        }[h+10*v]

class RectItemSignal(QObject):
    change = Signal(QGraphicsRectItem, name='rectChanged')
    move = Signal(QRectF, RectPosition, name='rectIsMoving')

class CustomRectItem(QGraphicsRectItem):
    # the halfed size of the pen in local coordinates to make sure it stays the
    # same during zooming
    pen_half_width = 1.0
    # the minimal size of the active area in scene coordinates
    handle_half_size = 5
    zoom_factor = 1.0
    # The size of the image this rect belongs to
    image_size = QRectF(0, 0, 1, 1)

    def __init__(self, rect: QRect, rect_type: ImageMarking,
                 target_size: QSize | None = None, parent = None):
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

    def handleAt(self, point: QPointF) -> RectPosition:
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

        return RectPosition.NONE

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
            self.unsetCursor()
            event.ignore()
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        self.handle_selected = self.handleAt(event.pos())
        if self.handle_selected != RectPosition.NONE:
            self.mouse_press_pos = event.pos()
            self.mouse_press_scene_pos = event.scenePos()
            self.mouse_press_rect = self.rect()
            self.signal.move.emit(self.rect(), self.handle_selected)
        else:
            event.ignore()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.handle_selected:
            rect = self.rect()
            pos_quantizised = event.scenePos().toPoint().toPointF()
            if self.handle_selected == RectPosition.TL:
                rect.setTopLeft(pos_quantizised)
            elif self.handle_selected == RectPosition.TOP:
                rect.setTop(pos_quantizised.y())
            elif self.handle_selected == RectPosition.TR:
                rect.setTopRight(pos_quantizised)
            elif self.handle_selected == RectPosition.RIGHT:
                rect.setRight(pos_quantizised.x())
            elif self.handle_selected == RectPosition.BR:
                rect.setBottomRight(pos_quantizised)
            elif self.handle_selected == RectPosition.BOTTOM:
                rect.setBottom(pos_quantizised.y())
            elif self.handle_selected == RectPosition.BL:
                rect.setBottomLeft(pos_quantizised)
            elif self.handle_selected == RectPosition.LEFT:
                rect.setLeft(pos_quantizised.x())
            self.handle_selected = flip_rect_position(self.handle_selected, rect.width() < 0, rect.height() < 0)

            if rect.width() == 0 or rect.height() == 0:
                self.setRect(rect)
            else:
                rect = rect.intersected(self.image_size)
                self.setRect(rect)
                self.size_changed()

            self.signal.move.emit(self.rect(), self.handle_selected)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.handle_selected:
            self.handle_selected = RectPosition.NONE
            self.signal.move.emit(self.rect(), self.handle_selected)
        self.signal.change.emit(self)
        super().mouseReleaseEvent(event)

    def paint(self, painter, option, widget=None):
        if self.rect_type == ImageMarking.CROP:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 0, 0, 127))
            path = QPainterPath()
            path.addRect(self.rect())
            to_crop = self.rect().size() - self.target_size
            path.addRect(QRectF(QPointF(self.rect().x()+floor(to_crop.width()/2),
                                        self.rect().y()+floor(to_crop.height()/2)), self.target_size))
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

class ResizeHintHUD(QGraphicsItem):
    zoom_factor = 1.0

    def __init__(self, boundingRect: QRectF, parent=None):
        super().__init__(parent)
        self._boundingRect = boundingRect
        self.rect = QRectF(0, 0, 1, 1)
        self.path = QPainterPath()

    @Slot(QRectF, RectPosition)
    def setValues(self, rect: QRectF, pos: RectPosition):
        if self.rect == rect and self.isVisible() == (pos != RectPosition.NONE):
            return

        self.rect = rect
        self.setVisible(pos != RectPosition.NONE)

        self.path = QPainterPath()

        if pos == RectPosition.TL:
            self.add_hyperbola_limit(self.rect.bottomRight(), -1, -1)
        elif pos == RectPosition.TOP:
            self.add_line_limit_lr(self.rect.bottom(), -1)
        elif pos == RectPosition.TR:
            self.add_hyperbola_limit(self.rect.bottomLeft(), 1, -1)
        elif pos == RectPosition.RIGHT:
            self.add_line_limit_td(self.rect.x(), 1)
        elif pos == RectPosition.BR:
            self.add_hyperbola_limit(self.rect.topLeft(), 1, 1)
        elif pos == RectPosition.BOTTOM:
            self.add_line_limit_lr(self.rect.y(), 1)
        elif pos == RectPosition.BL:
            self.add_hyperbola_limit(self.rect.topRight(), -1, 1)
        elif pos == RectPosition.LEFT:
            self.add_line_limit_td(self.rect.right(), -1)

        self.update()

    def add_line_limit_td(self, x: int, lr: int):
        width = settings.value('export_resolution', type=int)**2 / self.rect.height()
        self.path.moveTo(x + lr * width, self.rect.y()                     )
        self.path.lineTo(x + lr * width, self.rect.y() + self.rect.height())

        for ar in target_dimension.get_preferred_sizes():
            f = max(self._boundingRect.width() / ar[0],
                    self._boundingRect.height() / ar[1], 2)
            self.path.moveTo(x + lr * ar[0]    , self.rect.y()      + ar[1]    )
            self.path.lineTo(x + lr * ar[0] * f, self.rect.y()      + ar[1] * f)
            self.path.moveTo(x + lr * ar[0]    , self.rect.bottom() - ar[1]    )
            self.path.lineTo(x + lr * ar[0] * f, self.rect.bottom() - ar[1] * f)

    def add_line_limit_lr(self, y: int, td: int):
        height = settings.value('export_resolution', type=int)**2 / self.rect.width()
        self.path.moveTo(self.rect.x(),                     y + td * height)
        self.path.lineTo(self.rect.x() + self.rect.width(), y + td * height)

        for ar in target_dimension.get_preferred_sizes():
            f = max(self._boundingRect.width() / ar[0],
                    self._boundingRect.height() / ar[1], 2)
            self.path.moveTo(self.rect.x()     + ar[0]    , y + td * ar[1]    )
            self.path.lineTo(self.rect.x()     + ar[0] * f, y + td * ar[1] * f)
            self.path.moveTo(self.rect.right() - ar[0]    , y + td * ar[1]    )
            self.path.lineTo(self.rect.right() - ar[0] * f, y + td * ar[1] * f)

    def add_hyperbola_limit(self, pos: QPoint, lr: int, td: int):
        target_area = settings.value('export_resolution', type=int)**2
        res_size = max(settings.value('export_bucket_res_size', type=int), 1)
        dx = res_size
        self.path.moveTo(pos.x() + lr * dx, pos.y() + td * target_area / dx)
        while dx * res_size <= target_area:
            self.path.lineTo(pos.x() + lr * dx, pos.y() + td * target_area / dx)
            dx = dx + 10

        for ar in target_dimension.get_preferred_sizes():
            f = max(self._boundingRect.width() / ar[0],
                    self._boundingRect.height() / ar[1], 2)
            self.path.moveTo(pos.x() + lr * ar[0]    , pos.y() + td * ar[1]    )
            self.path.lineTo(pos.x() + lr * ar[0] * f, pos.y() + td * ar[1] * f)

    def boundingRect(self):
        return self._boundingRect

    def paint(self, painter, option, widget=None):
        clip_path = QPainterPath()
        clip_path.addRect(self._boundingRect)
        painter.setClipPath(clip_path)
        pen = QPen(QColor(255, 255, 255, 127), 3 / self.zoom_factor)
        painter.setPen(pen)
        painter.drawPath(self.path)
        pen = QPen(QColor(0, 0, 0), 1 / self.zoom_factor)
        painter.setPen(pen)
        painter.drawPath(self.path)

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

        self.proxy_image_index: QPersistentModelIndex = None
        self.rect_items: list[CustomRectItem] = []

        self.view.wheelEvent = self.wheelEvent

    @Slot()
    def load_image(self, proxy_image_index: QModelIndex):
        self.proxy_image_index = QPersistentModelIndex(proxy_image_index)

        self.scene.clear()
        if not self.proxy_image_index.isValid():
            return

        image: Image = self.proxy_image_index.data(Qt.ItemDataRole.UserRole)
        pixmap = QPixmap(str(image.path))
        image_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(image_item)
        self.scene.setSceneRect(image_item.boundingRect()
                                .adjusted(-1, -1, 1, 1)) # space for rect border
        CustomRectItem.image_size = image_item.boundingRect()
        self.zoom_fit()

        self.hud_item = ResizeHintHUD(CustomRectItem.image_size)
        self.scene.addItem(self.hud_item)

        if image.crop:
            if not image.target_dimension:
                image.target_dimension = target_dimension.get(image.crop[2:])
            self.add_rectangle(QRect(*image.crop), ImageMarking.CROP,
                               size=QSize(*image.target_dimension))
        for name, rect in image.hints.items():
            self.add_rectangle(QRect(*rect), ImageMarking.HINT, name=name)
        for name, rect in image.includes.items():
            self.add_rectangle(QRect(*rect), ImageMarking.INCLUDE, name=name)
        for name, rect in image.excludes.items():
            self.add_rectangle(QRect(*rect), ImageMarking.EXCLUDE, name=name)

    @Slot()
    def setting_change(self, key, value):
        if key == 'export_bucket_strategy':
            for rect in self.rect_items:
                rect.size_changed()
            self.scene.invalidate()

    @Slot(QGraphicsRectItem)
    def marking_change(self, rect: QGraphicsRectItem):
        assert self.proxy_image_index != None
        assert self.proxy_image_index.isValid()
        image: Image = self.proxy_image_index.data(Qt.ItemDataRole.UserRole)

        if rect.rect_type == ImageMarking.CROP:
            image.thumbnail = None
            image.crop = rect.rect().toRect().getRect() # ensure int!
            image.target_dimension = rect.target_size.toTuple()
        elif rect.rect_type == ImageMarking.HINT:
            image.hints[rect.data(0)] = rect.rect().toRect().getRect()
        elif rect.rect_type == ImageMarking.INCLUDE:
            image.includes[rect.data(0)] = rect.rect().toRect().getRect()
        elif rect.rect_type == ImageMarking.EXCLUDE:
            image.excludes[rect.data(0)] = rect.rect().toRect().getRect()

        self.proxy_image_list_model.sourceModel().dataChanged.emit(
            self.proxy_image_index, self.proxy_image_index)

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
        ResizeHintHUD.zoom_factor = CustomRectItem.zoom_factor
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

    def add_rectangle(self, rect: QRect, rect_type: ImageMarking,
                      size: QSize = None, name: str = ''):
        rect_item = CustomRectItem(rect, rect_type, size)
        rect_item.setData(0, name)
        if rect_type == ImageMarking.CROP:
            rect_item.signal.move.connect(self.hud_item.setValues)
        rect_item.signal.change.connect(self.marking_change)
        self.scene.addItem(rect_item)
        self.rect_items.append(rect_item)

    def resizeEvent(self, event):
        super().resizeEvent(event)
