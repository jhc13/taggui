from PySide6.QtCore import QAbstractListModel, QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QDockWidget, QListView

from model import Image


class ImageListModel(QAbstractListModel):
    def __init__(self, images: list[Image], parent):
        super().__init__(parent)
        self.images = images

    def rowCount(self, parent=None):
        return len(self.images)

    def data(self, index, role=None):
        image = self.images[index.row()]
        image_width = self.parent().image_list_image_width
        if role == Qt.DisplayRole:
            # The text shown next to the image.
            text = image.path.name
            if image.caption:
                text += f'\n{image.caption}'
            return text
        if role == Qt.DecorationRole:
            # The image.
            pixmap = QPixmap(str(image.path)).scaledToWidth(image_width)
            return QIcon(pixmap)
        if role == Qt.SizeHintRole:
            dimensions = image.dimensions
            if dimensions:
                width, height = dimensions
                # Scale the dimensions to the image width.
                return QSize(image_width, int(image_width * height / width))
            return QSize(image_width, image_width)


class ImageList(QDockWidget):
    def __init__(self, model: ImageListModel, parent):
        super().__init__(parent)
        self.setObjectName('image_list')
        self.setWindowTitle('Images')
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        # Use a QListView instead of a QListWidget for faster loading.
        self.list_view = QListView(self)
        self.list_view.setIconSize(QSize(parent.image_list_image_width,
                                         parent.image_list_image_width * 4))
        self.list_view.setWordWrap(True)
        self.list_view.setModel(model)
        self.setWidget(self.list_view)
