from enum import Enum
from math import ceil, floor
from pathlib import Path
from PySide6.QtCore import (QEvent, QModelIndex, QObject, QPersistentModelIndex,
                            QPoint, QPointF, QRect, QRectF, QSize, QSizeF, Qt,
                            Signal, Slot)
from PySide6.QtGui import (QAction, QActionGroup, QCursor, QColor, QIcon,
                           QPainter, QPainterPath, QPen, QPixmap, QTransform)
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsLineItem,
                               QGraphicsPixmapItem, QGraphicsRectItem,
                               QGraphicsTextItem, QGraphicsScene, QGraphicsView,
                               QMenu, QVBoxLayout, QWidget)
from utils.settings import settings
from models.proxy_image_list_model import ProxyImageListModel
from utils.image import Image, ImageMarking, Marking
import utils.target_dimension as target_dimension
from utils.grid import Grid
from dialogs.export_dialog import BucketStrategy

# Grid for alignment to latent space
grid = Grid(QRect(0, 0, 1, 1))

marking_colors = {
    ImageMarking.CROP: Qt.blue,
    ImageMarking.HINT: Qt.gray,
    ImageMarking.INCLUDE: Qt.green,
    ImageMarking.EXCLUDE: Qt.red,
}

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

def calculate_grid(content: QRect):
    global grid
    grid = Grid(content)

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
    # Static link to the single ImageGraphicsView in this application
    image_view = None
    show_marking_latent = True

    def __init__(self, rect: QRect, rect_type: ImageMarking,
                 parent = None):
        super().__init__(rect.toRectF(), parent)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)
        self.setAcceptHoverEvents(True)
        self.signal = RectItemSignal()
        self.rect_type = rect_type
        self.label: MarkingLabel | None = None
        self.color = marking_colors[rect_type]
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
        if (event.button() == Qt.MouseButton.LeftButton and
            self.handle_selected != RectPosition.NONE):
            self.mouse_press_pos = event.pos()
            self.mouse_press_scene_pos = event.scenePos()
            self.mouse_press_rect = self.rect()
            self.signal.move.emit(self.rect(), self.handle_selected)
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
                    pos_quantizised = grid.snap(event.pos().toPoint()).toPoint()
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
        bucket_strategy = settings.value('export_bucket_strategy', type=str)
        if self.rect_type == ImageMarking.CROP:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 0, 0, 127))
            path = QPainterPath()
            path.addRect(self.rect())
            path.addRect(grid.visible)
            painter.drawPath(path)
        elif self.rect_type == ImageMarking.INCLUDE and self.show_marking_latent:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 255, 0, 127))
            painter.drawRect(QRectF(grid.snap(self.rect().toRect().topLeft(), ceil),
                                    grid.snap(self.rect().toRect().bottomRight(), floor)))
        elif self.rect_type == ImageMarking.EXCLUDE and self.show_marking_latent:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 0, 0, 127))
            painter.drawRect(QRectF(grid.snap(self.rect().toRect().topLeft(), floor),
                                    grid.snap(self.rect().toRect().bottomRight(), ceil)))

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
        bbox = self.rect().adjusted(-adjust, -adjust, adjust, adjust)
        if self.rect_type == ImageMarking.EXCLUDE:
            bbox = bbox.united(QRectF(grid.snap(self.rect().toRect().topLeft(), floor),
                                      grid.snap(self.rect().toRect().bottomRight(), ceil)))
        return bbox

    def size_changed(self):
        if self.rect_type == ImageMarking.CROP:
            old_grid = grid
            calculate_grid(self.rect().toRect())
            if old_grid != grid:
                self.image_view.image_viewer.recalculate_markings(self)
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
    editingFinished = Signal()

    def __init__(self, text, parent):
        super().__init__(text, parent)
        self.setDefaultTextColor(Qt.black)
        self.setTextInteractionFlags(Qt.TextEditorInteraction)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.editingFinished.emit()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Enter, Qt.Key_Return):
            self.clearFocus()
            self.editingFinished.emit()
        else:
            super().keyPressEvent(event)
            self.parentItem().setRect(self.sceneBoundingRect())

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
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.showContextMenu)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.image_viewer = image_viewer
        MarkingItem.image_view = self
        self.last_pos = None
        self.clear_scene()

    def showContextMenu(self, pos):
        scene_pos = self.mapToScene(pos)
        item = self.scene().itemAt(scene_pos, self.transform())
        if item is not None and item.handle_selected != RectPosition.NONE:
            menu = QMenu()
            if isinstance(item, MarkingLabel):
                item = item.parentItem().parentItem()
            if isinstance(item, MarkingItem):
                if item.rect_type != ImageMarking.NONE:
                    if item.rect_type != ImageMarking.CROP:
                        marking_group = QActionGroup(menu)
                        change_to_hint_action = QAction('Hint', marking_group)
                        change_to_hint_action.setCheckable(True)
                        change_to_hint_action.setChecked(item.rect_type == ImageMarking.HINT)
                        change_to_hint_action.triggered.connect(
                            lambda: self.image_viewer.change_marking([item], ImageMarking.HINT))
                        menu.addAction(change_to_hint_action)
                        change_to_exclude_action = QAction('Exclude', marking_group)
                        change_to_exclude_action.setCheckable(True)
                        change_to_exclude_action.setChecked(item.rect_type == ImageMarking.EXCLUDE)
                        change_to_exclude_action.triggered.connect(
                            lambda: self.image_viewer.change_marking([item], ImageMarking.EXCLUDE))
                        menu.addAction(change_to_exclude_action)
                        change_to_include_action = QAction('Include', marking_group)
                        change_to_include_action.setCheckable(True)
                        change_to_include_action.setChecked(item.rect_type == ImageMarking.INCLUDE)
                        change_to_include_action.triggered.connect(
                            lambda: self.image_viewer.change_marking([item], ImageMarking.INCLUDE))
                        menu.addAction(change_to_include_action)
                        menu.addSeparator()
                    delete_marking_action = QAction(
                        QIcon.fromTheme('edit-delete'), 'Delete', self)
                    delete_marking_action.triggered.connect(
                        lambda: self.image_viewer.delete_markings([item]))
                    menu.addAction(delete_marking_action)
            menu.exec(self.mapToGlobal(pos))

    def clear_scene(self):
        """Use this and not scene.clear() due to resource management."""
        self.insertion_mode = False
        self.horizontal_line = None
        self.vertical_line = None
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
            if self.horizontal_line:
                self.scene().removeItem(self.horizontal_line)
                self.horizontal_line = None
                self.scene().removeItem(self.vertical_line)
                self.vertical_line = None

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
            self.last_pos = grid.snap(last_pos_raw.toPoint()).toPoint()
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
            edited_item = self.scene().focusItem()
            if not (isinstance(edited_item, MarkingLabel) and
                edited_item.textInteractionFlags() == Qt.TextEditorInteraction):
                # Delete marking only when not editing the label
                self.image_viewer.delete_markings()
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
        self.show_marking_state = True
        self.show_label_state = True
        self.show_marking_latent_state = True
        self.marking_to_add = ImageMarking.NONE
        self.scene = QGraphicsScene()
        self.view = ImageGraphicsView(self.scene, self)
        self.crop_marking: ImageMarking | None = None
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

        self.marking_items.clear()
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
        self.accept_crop_addition.emit(image.crop == None)
        if image.crop != None:
            self.add_rectangle(image.crop, ImageMarking.CROP)
        else:
            calculate_grid(MarkingItem.image_size)
        for marking in image.markings:
            self.add_rectangle(marking.rect, marking.type, name=marking.label)

    @Slot()
    def setting_change(self, key, value):
        if key in ['export_resolution', 'export_bucket_res_size',
                   'export_latent_size', 'export_upscaling',
                   'export_bucket_strategy']:
            self.recalculate_markings()

    def recalculate_markings(self, ignore: MarkingItem | None = None):
        if self.crop_marking:
            calculate_grid(self.crop_marking.rect().toRect())
        else:
            calculate_grid(MarkingItem.image_size)
        for marking in self.marking_items:
            if marking != ignore:
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

    @Slot()
    def change_marking(self, items: list[MarkingItem] | None = None,
                       new_marking: ImageMarking = ImageMarking.NONE):
        if items == None:
            items = self.scene.selectedItems()
        for item in items:
            if new_marking == ImageMarking.NONE:
                # default: toggle between all types
                item.rect_type = {ImageMarking.HINT: ImageMarking.EXCLUDE,
                                  ImageMarking.INCLUDE: ImageMarking.HINT,
                                  ImageMarking.EXCLUDE: ImageMarking.INCLUDE
                                 }[item.rect_type]
            else:
                item.rect_type = new_marking
            item.color = marking_colors[item.rect_type]
            item.label.parentItem().setBrush(item.color)
            self.marking_changed(item)
            item.update()

    @Slot(bool)
    def show_marking(self, checked: bool):
        self.show_marking_state = checked
        for marking in self.marking_items:
            marking.setVisible(checked)

    @Slot(bool)
    def show_label(self, checked: bool):
        self.show_label_state = checked
        for marking in self.marking_items:
            if marking.label:
                marking.label.setVisible(checked)
                marking.label.parentItem().setVisible(checked)

    @Slot(bool)
    def show_marking_latent(self, checked: bool):
        MarkingItem.show_marking_latent = checked
        for marking in self.marking_items:
            if marking.rect_type in [ImageMarking.INCLUDE, ImageMarking.EXCLUDE]:
                marking.update()

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
        self.marking_to_add = ImageMarking.NONE
        marking_item = MarkingItem(rect, rect_type, size)
        marking_item.setVisible(self.show_marking_state)
        if rect_type == ImageMarking.CROP:
            marking_item.signal.move.connect(self.hud_item.setValues)
            self.crop_marking = marking_item
            marking_item.size_changed() # call after self.crop_marking was set!
        elif name == '' and rect_type != ImageMarking.NONE:
            image: Image = self.proxy_image_index.data(Qt.ItemDataRole.UserRole)
            name = {ImageMarking.HINT: 'hint',
                    ImageMarking.INCLUDE: 'include',
                    ImageMarking.EXCLUDE: 'exclude'}[rect_type]
            image.markings.append(Marking(name, rect_type, rect))
        marking_item.setData(0, name)
        if rect_type != ImageMarking.CROP and rect_type != ImageMarking.NONE:
            label_background = QGraphicsRectItem(marking_item)
            label_background.setBrush(marking_item.color)
            label_background.setPen(Qt.NoPen)
            label_background.setVisible(self.show_label_state)
            marking_item.label = MarkingLabel(name, label_background)
            marking_item.label.setVisible(self.show_label_state)
            marking_item.label.editingFinished.connect(self.label_changed)
            marking_item.adjust_layout()
        marking_item.signal.change.connect(self.marking_changed)
        self.scene.addItem(marking_item)
        self.marking_items.append(marking_item)
        self.marking.emit(ImageMarking.NONE)
        if rect_type == ImageMarking.CROP:
            self.accept_crop_addition.emit(False)

    @Slot()
    def label_changed(self, do_emit = True):
        """Slot to call when a marking label was changed to sync the information
        in the image."""
        image: Image = self.proxy_image_index.data(Qt.ItemDataRole.UserRole)
        image.markings.clear()
        for marking in self.marking_items:
            if marking.rect_type != ImageMarking.CROP:
                marking.label.parentItem().parentItem().setData(0, marking.label.toPlainText())
                image.markings.append(Marking(marking.data(0),
                                      marking.rect_type,
                                      marking.rect().toRect()))
        if do_emit:
            self.proxy_image_list_model.sourceModel().dataChanged.emit(
                self.proxy_image_index, self.proxy_image_index)

    @Slot(QGraphicsRectItem)
    def marking_changed(self, marking: QGraphicsRectItem):
        """Slot to call when a marking was changed to sync the information
        in the image."""
        assert self.proxy_image_index != None
        assert self.proxy_image_index.isValid()
        image: Image = self.proxy_image_index.data(Qt.ItemDataRole.UserRole)

        if marking.rect_type == ImageMarking.CROP:
            image.thumbnail = None
            image.crop = marking.rect().toRect() # ensure int!
            image.target_dimension = grid.target
        else:
            image.markings = [Marking(marking.data(0),
                                      marking.rect_type,
                                      marking.rect().toRect())
                                    for marking in self.marking_items if marking.rect_type != ImageMarking.CROP]
        self.proxy_image_list_model.sourceModel().dataChanged.emit(
            self.proxy_image_index, self.proxy_image_index)

    def get_selected_type(self) -> ImageMarking:
        if len(self.scene.selectedItems()) > 0:
            return self.scene.selectedItems()[0].rect_type
        return ImageMarking.NONE

    @Slot()
    def delete_markings(self, items: list[MarkingItem] | None = None):
        """Slot to delete the list of items or when items = None all currently
        selected marking items."""
        image: Image = self.proxy_image_index.data(Qt.ItemDataRole.UserRole)
        if items == None:
            items = self.scene.selectedItems()
        for item in items:
            if item.rect_type == ImageMarking.CROP:
                self.crop_marking = None
                image.thumbnail = None
                image.crop = None
                image.target_dimension = None
                self.accept_crop_addition.emit(True)
                calculate_grid(MarkingItem.image_size)
            else:
                self.marking_items.remove(item)
                self.label_changed(False)
            self.scene.removeItem(item)
        self.proxy_image_list_model.sourceModel().dataChanged.emit(
            self.proxy_image_index, self.proxy_image_index)

    def resizeEvent(self, event):
        super().resizeEvent(event)
