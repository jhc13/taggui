from PySide6.QtCore import QModelIndex, QSize, Qt, Slot
from PySide6.QtWidgets import (QAbstractItemView, QDockWidget, QLabel,
                               QListView, QVBoxLayout, QWidget)

from models.proxy_image_list_model import ProxyImageListModel


class ImageList(QDockWidget):
    def __init__(self, image_width: int,
                 proxy_image_list_model: ProxyImageListModel):
        super().__init__()
        self.proxy_image_list_model = proxy_image_list_model
        # Each `QDockWidget` needs a unique object name for saving its state.
        self.setObjectName('image_list')
        self.setWindowTitle('Images')
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self.list_view = QListView(self)
        self.list_view.setModel(self.proxy_image_list_model)
        self.list_view.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_view.setWordWrap(True)
        # If the actual height of the image is greater than 3 times the width,
        # the image will be scaled down to fit.
        self.list_view.setIconSize(QSize(image_width, image_width * 3))
        self.image_index_label = QLabel()
        # A container widget is required to use a layout with a `QDockWidget`.
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self.list_view)
        layout.addWidget(self.image_index_label)
        self.setWidget(container)

    @Slot()
    def update_image_index_label(self, proxy_image_index: QModelIndex):
        image_count = self.proxy_image_list_model.rowCount()
        self.image_index_label.setText(
            f'Image {proxy_image_index.row() + 1} / {image_count}')

    def get_selected_image_indices(self) -> list[QModelIndex]:
        selected_proxy_image_indices = self.list_view.selectedIndexes()
        selected_image_indices = [
            self.proxy_image_list_model.mapToSource(index)
            for index in selected_proxy_image_indices]
        return selected_image_indices
