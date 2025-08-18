from enum import Enum
from math import floor, ceil

from PySide6.QtCore import QPoint, QRect, QSize, QPointF, QRectF, Qt


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

def map_rect_position_to_cursor(handle: RectPosition) -> Qt.CursorShape | None:
    if handle == RectPosition.TL or handle == RectPosition.BR:
        return Qt.CursorShape.SizeFDiagCursor
    elif handle == RectPosition.TR or handle == RectPosition.BL:
        return Qt.CursorShape.SizeBDiagCursor
    elif handle == RectPosition.TOP or handle == RectPosition.BOTTOM:
        return Qt.CursorShape.SizeVerCursor
    elif handle == RectPosition.LEFT or handle == RectPosition.RIGHT:
        return Qt.CursorShape.SizeHorCursor
    return None

def get_rect_position(left: bool, right: bool, top: bool, bottom: bool) -> RectPosition:
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
    """Change `rect` to move `rect_pos` at `pos`."""
    if rect_pos == RectPosition.TL:
        rect.setTopLeft(pos)
    elif rect_pos == RectPosition.TOP:
        rect.setTop(pos.y())
    elif rect_pos == RectPosition.TR:
        rect.setTopRight(pos)
    elif rect_pos == RectPosition.RIGHT:
        rect.setRight(pos.x() - 1)
    elif rect_pos == RectPosition.BR:
        rect.setBottomRight(pos - QPoint(1, 1))
    elif rect_pos == RectPosition.BOTTOM:
        rect.setBottom(pos.y() - 1)
    elif rect_pos == RectPosition.BL:
        rect.setBottomLeft(pos)
    elif rect_pos == RectPosition.LEFT:
        rect.setLeft(pos.x())
    return rect

def change_rectF(rect: QRectF, rect_pos: RectPosition, pos: QPointF) -> QRectF:
    """Change `rect` to move `rect_pos` at `pos`."""
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

def change_rect_round(rect: QRect, rect_pos: RectPosition, pos: QPointF, grow: bool) -> QRect:
    """Change `rect` to move `rect_pos` at `pos` and round by growing or shrinking the rect as `grow` demands."""
    round_tl = floor if grow else ceil
    round_br = ceil if grow else floor

    if rect_pos == RectPosition.TL:
        rect.setTopLeft(QPoint(round_tl(pos.x()), round_tl(pos.y())))
    elif rect_pos == RectPosition.TOP:
        rect.setTop(round_tl(pos.y()))
    elif rect_pos == RectPosition.TR:
        rect.setTopRight(QPoint(round_br(pos.x()), round_tl(pos.y())))
    elif rect_pos == RectPosition.RIGHT:
        rect.setRight(round_br(pos.x()))
    elif rect_pos == RectPosition.BR:
        rect.setBottomRight(QPoint(round_br(pos.x()), round_br(pos.y())))
    elif rect_pos == RectPosition.BOTTOM:
        rect.setBottom(round_br(pos.y()))
    elif rect_pos == RectPosition.BL:
        rect.setBottomLeft(QPoint(round_tl(pos.x()), round_br(pos.y())))
    elif rect_pos == RectPosition.LEFT:
        rect.setLeft(round_tl(pos.x()))
    return rect

def change_rect_to_match_size(rect: QRectF, rect_pos: RectPosition, size: QSize) -> QRect:
    """Change the `rect` at place `rect_pos` so that the size matches `size`.

    Moving one side will ignore the value in the size of the perpendicular side.
    """
    rect_new = QRectF(rect)
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
    return rect_new.toRect()
