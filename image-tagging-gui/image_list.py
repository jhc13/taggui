from PySide6.QtCore import (QSize,
                            Qt)
from PySide6.QtWidgets import QDockWidget, QListView

from image_list_model import ImageListModel


class ImageList(QDockWidget):
    def __init__(self, model: ImageListModel, parent):
        super().__init__(parent)
        self.setObjectName('image_list')
        self.setWindowTitle('Images')
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.list_view = QListView(self)
        self.list_view.setWordWrap(True)
        self.list_view.setModel(model)
        self.setWidget(self.list_view)
        self.set_image_width()

    def set_image_width(self):
        self.list_view.setIconSize(
            QSize(self.parent().image_list_image_width,
                  self.parent().image_list_image_width * 4))
