from PySide6.QtCore import QModelIndex, QSettings, QSize, Qt, Slot
from PySide6.QtWidgets import (QDockWidget, QLabel, QListView, QVBoxLayout,
                               QWidget)

from image_list_model import ImageListModel


class ImageList(QDockWidget):
    def __init__(self, settings: QSettings, image_list_model: ImageListModel):
        super().__init__()
        self.settings = settings
        self.image_list_model = image_list_model
        # Each `QDockWidget` needs a unique object name for saving its state.
        self.setObjectName('image_list')
        self.setWindowTitle('Images')
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self.list_view = QListView(self)
        self.list_view.setModel(self.image_list_model)
        self.list_view.setWordWrap(True)
        self.set_image_width()
        self.image_index_label = QLabel()

        # A container widget is required to use a layout with a `QDockWidget`.
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self.list_view)
        layout.addWidget(self.image_index_label)
        self.setWidget(container)

        self.list_view.selectionModel().currentChanged.connect(
            self.update_image_index_label)

    @Slot()
    def set_image_width(self):
        image_width = int(self.settings.value('image_list_image_width'))
        # If the actual height of the image is greater than 3 times the width,
        # the image will be scaled down to fit.
        self.list_view.setIconSize(QSize(image_width, image_width * 3))

    @Slot()
    def update_image_index_label(self, image_index: QModelIndex):
        image_count = self.image_list_model.rowCount()
        self.image_index_label.setText(
            f'Image {image_index.row() + 1} / {image_count}')
