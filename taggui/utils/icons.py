from pathlib import Path

from PySide6.QtGui import QColor, QPixmap, QIcon, QPainter, QPen, Qt, QPainterPath, QImage
from PySide6.QtCore import QRect

from utils.utils import get_resource_path

ICON_PATH = Path('images/icon.ico')
TOGGLE_MARKING_ICON_PATH = Path('images/toggle_marking.png')
SHOW_MARKINGS_ICON_PATH = Path('images/show_marking.png')
SHOW_LABELS_ICON_PATH = Path('images/show_label.png')
SHOW_MARKING_LATENT_ICON_PATH = Path('images/show_marking_latent.png')

def taggui_icon():
    return QIcon(str(get_resource_path(ICON_PATH)))

def toggle_marking_icon():
    return QIcon(str(get_resource_path(TOGGLE_MARKING_ICON_PATH)))

def show_markings_icon():
    return QIcon(str(get_resource_path(SHOW_MARKINGS_ICON_PATH)))

def show_labels_icon():
    return QIcon(str(get_resource_path(SHOW_LABELS_ICON_PATH)))

def show_marking_latent_icon():
    return QIcon(str(get_resource_path(SHOW_MARKING_LATENT_ICON_PATH)))

def create_add_box_icon(color: QColor) -> QPixmap:
    """Create a QPixmap for an icon"""
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor('transparent'))

    # Create a painter to draw on the pixmap
    painter = QPainter(pixmap)

    # Draw a bordered rectangle in the specified color
    rect = QRect(2, 2, 28, 28)
    painter.setPen(QPen(color, 2))
    painter.drawRect(rect)

    # Draw a plus sign in the middle
    painter.setPen(QPen(Qt.black, 1))
    path = QPainterPath()
    path.moveTo(16, 10)
    path.lineTo(16, 22)
    path.moveTo(10, 16)
    path.lineTo(22, 16)
    painter.drawPath(path)
    painter.end()

    return pixmap
