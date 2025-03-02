from enum import Enum
from math import floor
from pathlib import Path
from PySide6.QtCore import (QEvent, QModelIndex, QObject, QPersistentModelIndex,
                            QPoint, QPointF, QRect, QRectF, QSize, QSizeF, Qt,
                            Signal, Slot)
from PySide6.QtGui import (QCursor, QColor, QPainter, QPainterPath, QPen,
                           QPixmap, QTransform)
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsLineItem,
                               QGraphicsPixmapItem, QGraphicsRectItem,
                               QGraphicsTextItem, QGraphicsScene, QGraphicsView,
                               QVBoxLayout, QWidget)
from utils.settings import settings
from models.proxy_image_list_model import ProxyImageListModel
from utils.image import Image, ImageMarking, Marking
import utils.target_dimension as target_dimension
from dialogs.export_dialog import BucketStrategy

# Alignment base for a grid
base_point: QPoint = QPoint(0, 0)

# stepsize of the grid
grid: int = 8

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

def change_rect(rect: QRect, rect_pos: RectPosition, pos: QPoint) -> QRect:
    if rect_pos == RectPosition.TL:
        rect.setTopLeft(pos)
    elif rect_pos == RectPosition.TOP:
        rect.setTop(pos.y())
    elif rect_pos == RectPosition.TR:
        rect.setTopRight(pos)
    elif rect_pos == RectPosition.RIGHT:
        rect.setRight(pos.x())
    elif rect_pos == RectPosition.BR:
        rect.setBottomRight(pos)
    elif rect_pos == RectPosition.BOTTOM:
        rect.setBottom(pos.y())
    elif rect_pos == RectPosition.BL:
        rect.setBottomLeft(pos)
    elif rect_pos == RectPosition.LEFT:
        rect.setLeft(pos.x())
    return rect

def change_rect_to_match_size(rect: QRect, rect_pos: RectPosition, size: QSize) -> QRect:
    """Change the `rect` at place `rect_pos` so that the size matches `size`.

    Moving a side will ignore the value in the size for the perpendicular side.
    """
    rect_new = QRect(rect)
    if rect_pos == RectPosition.TL:
        rect_new.setSize(size)
        rect_new.moveBottomRight(rect.bottomRight())
    elif rect_pos == RectPosition.TOP:
        rect_new.setHeight(size.height())
        rect_new.moveBottom(rect.bottom())
    elif rect_pos == RectPosition.TR:
        rect_new.setSize(size)
        rect_new.moveBottomLeft(rect.bottomLeft())
    elif rect_pos == RectPosition.RIGHT:
        rect_new.setWidth(size.width())
        rect_new.moveLeft(rect.left())
    elif rect_pos == RectPosition.BR:
        rect_new.setSize(size)
        rect_new.moveTopLeft(rect.topLeft())
    elif rect_pos == RectPosition.BOTTOM:
        rect_new.setHeight(size.height())
        rect_new.moveTop(rect.top())
    elif rect_pos == RectPosition.BL:
        rect_new.setSize(size)
        rect_new.moveTopRight(rect.topRight())
    elif rect_pos == RectPosition.LEFT:
        rect_new.setWidth(size.width())
        rect_new.moveRight(rect.right())
    return rect_new

def map_to_grid(point: QPoint) -> QPoint:
    """Align the point to the closest position on the grid aligned at
    `base_point` and with a step width of `grid`.
    """
    return (QPointF(point - base_point) / grid).toPoint() * grid + base_point

class RectItemSignal(QObject):
    change = Signal(QGraphicsRectItem, name='rectChanged')
    move = Signal(QRectF, RectPosition, name='rectIsMoving')

class MarkingItem(QGraphicsRectItem):
    # the halfed size of the pen in local coordinates to make sure it stays the
    # same during zooming
    pen_half_width = 1.0
    # the minimal size of the active area in scene coordinates
    handle_half_size = 5
    zoom_factor = 1.0
    # The size of the image this rect belongs to
    image_size = QRect(0, 0, 1, 1)
    # the last (quantisized position of the mouse
    #last_pos = None
    # Static link to the single ImageGraphicsView in this application
    image_view = None

    def __init__(self, rect: QRect, rect_type: ImageMarking,
                 target_size: QSize | None = None, parent = None):
        super().__init__(rect.toRectF(), parent)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)
        self.setAcceptHoverEvents(True)
        self.signal = RectItemSignal()
        self.rect_type = rect_type
        self.label: MarkingLabel | None = None
        self.color = {
            ImageMarking.CROP: Qt.blue,
            ImageMarking.HINT: Qt.gray,
            ImageMarking.INCLUDE: Qt.green,
            ImageMarking.EXCLUDE: Qt.red,
            }[rect_type]
        if rect_type == ImageMarking.CROP and target_size == None:
            self.size_changed() # this method sets self.target_size
        else:
            self.target_size = target_size
        self.handle_selected = None
        self.mouse_press_pos = None
        self.mouse_press_rect = None

    def handleAt(self, point: QPointF) -> RectPosition:
        handle_space = -min(self.pen_half_width - self.handle_half_size,
                            0)/self.zoom_factor
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
            if self.rect_type == ImageMarking.CROP:
                global base_point
                if (self.handle_selected == RectPosition.TL or
                    self.handle_selected == RectPosition.TOP):
                    base_point = self.rect().bottomRight().toPoint()
                elif (self.handle_selected == RectPosition.TR or
                      self.handle_selected == RectPosition.RIGHT):
                    base_point = self.rect().bottomLeft().toPoint()
                elif (self.handle_selected == RectPosition.BR or
                      self.handle_selected == RectPosition.BOTTOM):
                    base_point = self.rect().topLeft().toPoint()
                elif (self.handle_selected == RectPosition.BL or
                      self.handle_selected == RectPosition.LEFT):
                    base_point = self.rect().topRight().toPoint()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        if self.handle_selected:
            if ((event.modifiers() & Qt.KeyboardModifier.ShiftModifier) ==
                Qt.KeyboardModifier.ShiftModifier):
                if self.rect_type == ImageMarking.CROP:
                    pos_quantizised = event.pos().toPoint()
                    pos_quantizised_pre = pos_quantizised
                    rect_pre = change_rect(self.rect().toRect(),
                                           self.handle_selected,
                                           pos_quantizised)
                    target = target_dimension.get(rect_pre.size())
                    if rect_pre.height() * target.width() / rect_pre.width() < target.height(): # too wide
                        scale = rect_pre.height() / target.height()
                        target_size0 = QSize(floor(target.width()*scale),
                                             rect_pre.height())
                        target_size1 = QSize(floor(target.width()*scale)+1,
                                             rect_pre.height())
                    else: # too high
                        scale = rect_pre.width() / target.width()
                        target_size0 = QSize(rect_pre.width(),
                                             floor(target.height()*scale))
                        target_size1 = QSize(rect_pre.width(),
                                             floor(target.height()*scale)+1)
                    t0 = target_dimension.get(target_size0)
                    if t0 == target:
                        target_size = target_size0
                    else:
                        target_size = target_size1
                    rect = change_rect_to_match_size(self.rect().toRect(),
                                                     self.handle_selected,
                                                     target_size)
                else:
                    pos_quantizised = map_to_grid(event.pos().toPoint())
                    rect = change_rect(self.rect().toRect(),
                                       self.handle_selected,
                                       pos_quantizised)
            else:
                pos_quantizised = event.pos().toPoint()
                rect = change_rect(self.rect().toRect(),
                                   self.handle_selected,
                                   pos_quantizised)

            self.handle_selected = flip_rect_position(self.handle_selected,
                                                      rect.width() < 0,
                                                      rect.height() < 0)

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
            if self.target_size:
                to_crop = self.rect().size() - self.target_size
                path.addRect(QRectF(QPointF(self.rect().x()+floor(to_crop.width()/2),
                                            self.rect().y()+floor(to_crop.height()/2)),
                                    self.target_size))
            painter.drawPath(path)

        pen_half_width = self.pen_half_width / self.zoom_factor
        pen = QPen(self.color, 2*pen_half_width, Qt.SolidLine, Qt.RoundCap,
                   Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self.rect().adjusted(-pen_half_width, -pen_half_width,
                                              pen_half_width, pen_half_width))

        if self.isSelected():
            s_rect = self.rect().adjusted(-2*pen_half_width, -2*pen_half_width,
                                           2*pen_half_width,  2*pen_half_width)
            painter.setPen(QPen(Qt.white, 1.5 / self.zoom_factor, Qt.SolidLine))
            painter.drawRect(s_rect)
            painter.setPen(QPen(Qt.black, 1.5 / self.zoom_factor, Qt.DotLine))
            painter.drawRect(s_rect)

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
            current = self.rect().size().expandedTo(QSize(1, 1))
            if bucket_strategy == BucketStrategy.SCALE:
                self.target_size = current
            else: # CROP or CROP_SCALE
                target = target_dimension.get(current)
                if current.height() * target.width() / current.width() < target.height(): # too wide
                    scale = current.height() / target.height()
                else: # too high
                    scale = current.width() / target.width()
                self.target_size = QSize(round(target.width()*scale), round(target.height()*scale))
                if bucket_strategy == BucketStrategy.CROP_SCALE:
                    self.target_size = (self.target_size + current.toSize())/2
        self.adjust_layout()

    def adjust_layout(self):
        if self.label != None:
            self.label.changeZoom(self.zoom_factor)
            pen_half_width = self.pen_half_width / self.zoom_factor
            if self.rect().y() > self.label.boundingRect().height():
                self.label.setPos(self.rect().adjusted(
                    -2 * pen_half_width,
                    -pen_half_width - self.label.boundingRect().height(),
                    0, 0).topLeft())
                self.label.parentItem().setRect(self.label.sceneBoundingRect())
            else:
                self.label.setPos(self.rect().adjusted(
                    -pen_half_width, -pen_half_width, 0, 0).topLeft())
                self.label.parentItem().setRect(self.label.sceneBoundingRect())


class MarkingLabel(QGraphicsTextItem):
    editingFinished = Signal(str)

    def __init__(self, text, parent):
        super().__init__(text, parent)
        self.setDefaultTextColor(Qt.black)
        self.setTextInteractionFlags(Qt.TextEditorInteraction)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.editingFinished.emit(self.toPlainText())

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        self.parentItem().setRect(self.sceneBoundingRect())
        if event.key() in (Qt.Key_Enter, Qt.Key_Return):
            self.clearFocus()
            self.editingFinished.emit(self.toPlainText())

    def insertFromMimeData(self, source):
        if source.hasText():
            # Insert only the plain text
            cursor = self.textCursor()
            cursor.insertText(source.text())
        else:
            super().insertFromMimeData(source)
        self.parentItem().setRect(self.sceneBoundingRect())

    def changeZoom(self, zoom_factor):
        font = self.font()
        font.setPointSizeF(10 / zoom_factor)
        self.setFont(font)
        self.parentItem().setRect(self.sceneBoundingRect())


class ResizeHintHUD(QGraphicsItem):
    zoom_factor = 1.0

    def __init__(self, boundingRect: QRect, parent=None):
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

class ImageGraphicsView(QGraphicsView):
    def __init__(self, scene, image_viewer):
        super().__init__(scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.image_viewer = image_viewer
        MarkingItem.image_view = self
        self.last_pos = None
        self.clear_scene()

    def clear_scene(self):
        """Use this and not scene.clear() due to resource management."""
        global grid, base_point
        self.insertion_mode = False
        self.horizontal_line = None
        self.vertical_line = None
        grid = 8
        base_point = QPoint(0, 0)
        self.scene().clear()

    def set_insertion_mode(self, mode):
        self.insertion_mode = mode
        if mode:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
            self.horizontal_line = QGraphicsLineItem()
            self.vertical_line = QGraphicsLineItem()
            self.scene().addItem(self.horizontal_line)
            self.scene().addItem(self.vertical_line)
            self.update_lines_pos()
        else:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.unsetCursor()
            self.scene().removeItem(self.horizontal_line)
            self.scene().removeItem(self.vertical_line)

    def update_lines_pos(self):
        """Show the hint lines at the position self.last_pos.

        Note: do not use a position parameter as then the key event couldn't
        immediately show them as the mouse position would be missing then.
        """
        if self.last_pos:
            view_rect = self.mapToScene(self.viewport().rect()).boundingRect()
            self.horizontal_line.setLine(view_rect.left(), self.last_pos.y(),
                                         view_rect.right(), self.last_pos.y())
            self.vertical_line.setLine(self.last_pos.x(), view_rect.top(),
                                       self.last_pos.x(), view_rect.bottom())


    def mousePressEvent(self, event):
        if self.insertion_mode and event.button() == Qt.MouseButton.LeftButton:
            rect_type = self.image_viewer.marking_to_add
            if rect_type == ImageMarking.NONE:
                if ((event.modifiers() & Qt.KeyboardModifier.AltModifier) ==
                    Qt.KeyboardModifier.AltModifier):
                    rect_type = ImageMarking.EXCLUDE
                else:
                    rect_type = ImageMarking.HINT

            self.image_viewer.add_rectangle(QRect(self.last_pos, QSize(0, 0)),
                                            rect_type)
            self.set_insertion_mode(False)
            super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        last_pos_raw = self.mapToScene(event.position().toPoint())
        if ((event.modifiers() & Qt.KeyboardModifier.ShiftModifier) ==
            Qt.KeyboardModifier.ShiftModifier):
            self.last_pos = map_to_grid(last_pos_raw.toPoint())
        else:
            self.last_pos = last_pos_raw.toPoint()
            pos = last_pos_raw

        if self.insertion_mode:
            self.update_lines_pos()
        else:
            super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Control:
            self.set_insertion_mode(True)
        elif event.key() == Qt.Key.Key_Delete:
            self.image_viewer.delete_selected()
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Control:
            self.set_insertion_mode(False)
        super().keyReleaseEvent(event)

class ImageViewer(QWidget):
    zoom = Signal(float, name='zoomChanged')
    marking = Signal(ImageMarking, name='markingToAdd')
    accept_crop_addition = Signal(bool, name='allowAdditionOfCrop')

    def __init__(self, proxy_image_list_model: ProxyImageListModel):
        super().__init__()
        self.proxy_image_list_model = proxy_image_list_model
        MarkingItem.pen_half_width = round(self.devicePixelRatio())
        MarkingItem.zoom_factor = 1.0
        self.is_zoom_to_fit = True
        self.marking_to_add = ImageMarking.NONE
        self.scene = QGraphicsScene()
        self.view = ImageGraphicsView(self.scene, self)
        settings.change.connect(self.setting_change)

        layout = QVBoxLayout()
        layout.addWidget(self.view)
        self.setLayout(layout)

        self.proxy_image_index: QPersistentModelIndex = None
        self.marking_items: list[MarkingItem] = []

        self.view.wheelEvent = self.wheelEvent

    @Slot()
    def load_image(self, proxy_image_index: QModelIndex):
        self.proxy_image_index = QPersistentModelIndex(proxy_image_index)

        self.view.clear_scene()
        if not self.proxy_image_index.isValid():
            return

        image: Image = self.proxy_image_index.data(Qt.ItemDataRole.UserRole)
        pixmap = QPixmap(str(image.path))
        image_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(image_item)
        self.scene.setSceneRect(image_item.boundingRect()
                                .adjusted(-1, -1, 1, 1)) # space for rect border
        MarkingItem.image_size = image_item.boundingRect().toRect()
        self.zoom_fit()

        self.hud_item = ResizeHintHUD(MarkingItem.image_size)
        self.scene.addItem(self.hud_item)

        self.marking_to_add = ImageMarking.NONE
        self.marking.emit(ImageMarking.NONE)
        self.accept_crop_addition.emit(not image.crop)
        if image.crop:
            if not image.target_dimension:
                image.target_dimension = target_dimension.get(image.crop.size())
            self.add_rectangle(image.crop, ImageMarking.CROP,
                               size=image.target_dimension)
        for marking in image.markings:
            self.add_rectangle(marking.rect, marking.type, name=marking.label)

    @Slot()
    def setting_change(self, key, value):
        if key == 'export_bucket_strategy':
            for marking in self.marking_items:
                marking.size_changed()
            self.scene.invalidate()

    @Slot()
    def zoom_in(self, center_pos: QPoint = None):
        MarkingItem.zoom_factor = min(MarkingItem.zoom_factor * 1.25, 16)
        self.is_zoom_to_fit = False
        self.zoom_emit()

    @Slot()
    def zoom_out(self, center_pos: QPoint = None):
        view = self.view.viewport().size()
        scene = self.scene.sceneRect()
        MarkingItem.zoom_factor = max(MarkingItem.zoom_factor / 1.25,
                                         min(view.width()/scene.width(),
                                             view.height()/scene.height()))
        self.is_zoom_to_fit = False
        self.zoom_emit()

    @Slot()
    def zoom_original(self):
        MarkingItem.zoom_factor = 1.0
        self.is_zoom_to_fit = False
        self.zoom_emit()

    @Slot()
    def zoom_fit(self):
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
        MarkingItem.zoom_factor = self.view.transform().m11()
        self.is_zoom_to_fit = True
        self.zoom_emit()

    def zoom_emit(self):
        ResizeHintHUD.zoom_factor = MarkingItem.zoom_factor
        transform = self.view.transform()
        self.view.setTransform(QTransform(
            MarkingItem.zoom_factor, transform.m12(), transform.m13(),
            transform.m21(), MarkingItem.zoom_factor, transform.m23(),
            transform.m31(), transform.m32(), transform.m33()))
        for marking in self.marking_items:
            marking.adjust_layout()
        if self.is_zoom_to_fit:
            self.zoom.emit(-1)
        else:
            self.zoom.emit(MarkingItem.zoom_factor)

    @Slot(ImageMarking)
    def add_marking(self, marking: ImageMarking):
        self.marking_to_add = marking
        self.view.set_insertion_mode(marking != ImageMarking.NONE)
        grid = 1 if marking == ImageMarking.CROP else 8

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
        marking_item = MarkingItem(rect, rect_type, size)
        if rect_type == ImageMarking.CROP:
            marking_item.signal.move.connect(self.hud_item.setValues)
        elif name == '' and rect_type != ImageMarking.NONE:
            image: Image = self.proxy_image_index.data(Qt.ItemDataRole.UserRole)
            if rect_type == ImageMarking.HINT:
                keys = image.hints.keys()
                pre = 'hint'
            elif rect_type == ImageMarking.INCLUDE:
                keys = image.includes.keys()
                pre = 'include'
            elif rect_type == ImageMarking.EXCLUDE:
                keys = image.excludes.keys()
                pre = 'exclude'
            count = 1
            while f'{pre}{count}' in keys:
                count += 1
            name = f'{pre}{count}'
        marking_item.setData(0, name)
        if rect_type != ImageMarking.CROP and rect_type != ImageMarking.NONE:
            label_background = QGraphicsRectItem(marking_item)
            label_background.setBrush(marking_item.color)
            label_background.setPen(Qt.NoPen)
            marking_item.label = MarkingLabel(name, label_background)
            marking_item.adjust_layout()
        marking_item.signal.change.connect(self.marking_changed)
        self.scene.addItem(marking_item)
        self.marking_items.append(marking_item)
        self.marking.emit(ImageMarking.NONE)
        if rect_type == ImageMarking.CROP:
            self.accept_crop_addition.emit(False)
            self.marking_changed(marking_item)

    @Slot(QGraphicsRectItem)
    def marking_changed(self, marking: QGraphicsRectItem):
        global grid, base_point
        assert self.proxy_image_index != None
        assert self.proxy_image_index.isValid()
        image: Image = self.proxy_image_index.data(Qt.ItemDataRole.UserRole)

        if marking.rect_type == ImageMarking.CROP:
            image.thumbnail = None
            image.crop = marking.rect().toRect() # ensure int!
            image.target_dimension = marking.target_size
            scale = min(image.crop.width()/image.target_dimension.width(),
                        image.crop.height()/image.target_dimension.height())
            base_point = QPoint(image.crop.x()+floor((image.crop.width()-scale*image.target_dimension.width())/2),
                                image.crop.y()+floor((image.crop.height()-scale*image.target_dimension.height())/2))
        else:
            image.markings = [Marking(marking.data(0),
                                      marking.rect_type,
                                      marking.rect().toRect())
                                    for marking in self.marking_items if marking.rect_type != ImageMarking.CROP]
        self.proxy_image_list_model.sourceModel().dataChanged.emit(
            self.proxy_image_index, self.proxy_image_index)

    @Slot()
    def delete_selected(self):
        image: Image = self.proxy_image_index.data(Qt.ItemDataRole.UserRole)
        for item in self.scene.selectedItems():
            if item.rect_type == ImageMarking.CROP:
                global base_point
                image.thumbnail = None
                image.crop = None
                image.target_dimension = None
                base_point = QPoint(0, 0)
                self.accept_crop_addition.emit(True)
            elif item.rect_type == ImageMarking.HINT:
                del image.hints[item.data(0)]
            elif item.rect_type == ImageMarking.INCLUDE:
                del image.includes[item.data(0)]
            elif item.rect_type == ImageMarking.EXCLUDE:
                del image.excludes[item.data(0)]
            self.scene.removeItem(item)
        self.proxy_image_list_model.sourceModel().dataChanged.emit(
            self.proxy_image_index, self.proxy_image_index)

    def resizeEvent(self, event):
        super().resizeEvent(event)
