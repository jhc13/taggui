from PySide6.QtCore import QSettings, QSize, Qt, Slot
from PySide6.QtWidgets import QDockWidget, QListView

from image_list_model import ImageListModel


class ImageList(QDockWidget):
    def __init__(self, settings: QSettings, image_list_model: ImageListModel):
        super().__init__()
        self.settings = settings
        # Each `QDockWidget` needs a unique object name for saving its state.
        self.setObjectName('image_list')
        self.setWindowTitle('Images')
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.list_view = QListView(self)
        self.list_view.setModel(image_list_model)
        self.list_view.setWordWrap(True)
        self.set_image_width()
        self.setWidget(self.list_view)

    @Slot()
    def set_image_width(self):
        image_width = int(self.settings.value('image_list_image_width'))
        # If the actual height of the image is greater than 3 times the width,
        # the image will be scaled down to fit.
        self.list_view.setIconSize(QSize(image_width, image_width * 3))
