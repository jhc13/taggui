from PySide6.QtCore import QModelIndex, QSize, Qt, Signal, Slot
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QDockWidget,
                               QLabel, QListView, QMenu, QMessageBox,
                               QVBoxLayout, QWidget)

from models.proxy_image_list_model import ProxyImageListModel
from utils.image import Image
from utils.utils import get_confirmation_dialog_reply


class ImageListView(QListView):
    tags_paste_requested = Signal(list, list)

    def __init__(self, parent, proxy_image_list_model: ProxyImageListModel,
                 separator: str, image_width: int):
        super().__init__(parent)
        self.proxy_image_list_model = proxy_image_list_model
        self.separator = separator
        self.setModel(proxy_image_list_model)
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setWordWrap(True)
        # If the actual height of the image is greater than 3 times the width,
        # the image will be scaled down to fit.
        self.setIconSize(QSize(image_width, image_width * 3))

        copy_tags_action = self.addAction('Copy Tags')
        copy_tags_action.setShortcut('Ctrl+C')
        copy_tags_action.triggered.connect(
            self.copy_selected_image_tags)
        self.addAction(copy_tags_action)
        paste_tags_action = self.addAction('Paste Tags')
        paste_tags_action.setShortcut('Ctrl+V')
        paste_tags_action.triggered.connect(
            self.paste_tags)
        self.addAction(paste_tags_action)
        self.copy_file_names_action = self.addAction('Copy File Name')
        self.copy_file_names_action.setShortcut('Ctrl+Alt+C')
        self.copy_file_names_action.triggered.connect(
            self.copy_selected_image_file_names)
        self.addAction(self.copy_file_names_action)
        self.copy_paths_action = self.addAction('Copy Path')
        self.copy_paths_action.setShortcut('Ctrl+Shift+C')
        self.copy_paths_action.triggered.connect(
            self.copy_selected_image_paths)
        self.addAction(self.copy_paths_action)
        self.context_menu = QMenu(self)
        self.context_menu.addAction(copy_tags_action)
        self.context_menu.addAction(paste_tags_action)
        self.context_menu.addAction(self.copy_file_names_action)
        self.context_menu.addAction(self.copy_paths_action)
        self.selectionModel().selectionChanged.connect(
            self.update_context_menu_action_names)

    def contextMenuEvent(self, event):
        self.context_menu.exec_(event.globalPos())

    def get_selected_images(self) -> list[Image]:
        selected_image_proxy_indices = self.selectedIndexes()
        selected_images = [index.data(Qt.UserRole)
                           for index in selected_image_proxy_indices]
        return selected_images

    def copy_selected_image_tags(self):
        selected_images = self.get_selected_images()
        selected_image_captions = [self.separator.join(image.tags)
                                   for image in selected_images]
        QApplication.clipboard().setText('\n'.join(selected_image_captions))

    def get_selected_image_indices(self) -> list[QModelIndex]:
        selected_image_proxy_indices = self.selectedIndexes()
        selected_image_indices = [
            self.proxy_image_list_model.mapToSource(proxy_index)
            for proxy_index in selected_image_proxy_indices]
        return selected_image_indices

    def paste_tags(self):
        selected_image_count = len(self.selectedIndexes())
        if selected_image_count > 1:
            reply = get_confirmation_dialog_reply(
                title='Paste Tags',
                question=f'Paste tags to {selected_image_count} selected '
                         f'images?')
            if reply != QMessageBox.StandardButton.Yes:
                return
        tags = QApplication.clipboard().text().split(self.separator)
        selected_image_indices = self.get_selected_image_indices()
        self.tags_paste_requested.emit(tags, selected_image_indices)

    def copy_selected_image_file_names(self):
        selected_images = self.get_selected_images()
        selected_image_file_names = [image.path.name
                                     for image in selected_images]
        QApplication.clipboard().setText('\n'.join(selected_image_file_names))

    def copy_selected_image_paths(self):
        selected_images = self.get_selected_images()
        selected_image_paths = [str(image.path) for image in selected_images]
        QApplication.clipboard().setText('\n'.join(selected_image_paths))

    def update_context_menu_action_names(self):
        selected_image_count = len(self.selectedIndexes())
        if selected_image_count == 1:
            copy_file_names_action_name = 'Copy File Name'
            copy_paths_action_name = 'Copy Path'
        else:
            copy_file_names_action_name = 'Copy File Names'
            copy_paths_action_name = 'Copy Paths'
        self.copy_file_names_action.setText(copy_file_names_action_name)
        self.copy_paths_action.setText(copy_paths_action_name)


class ImageList(QDockWidget):
    def __init__(self, proxy_image_list_model: ProxyImageListModel,
                 separator: str, image_width: int):
        super().__init__()
        self.proxy_image_list_model = proxy_image_list_model
        # Each `QDockWidget` needs a unique object name for saving its state.
        self.setObjectName('image_list')
        self.setWindowTitle('Images')
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self.list_view = ImageListView(self, proxy_image_list_model,
                                       separator, image_width)
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
        return self.list_view.get_selected_image_indices()
