from dataclasses import dataclass, field
from pathlib import Path

import imagesize
from PySide6.QtCore import (QAbstractListModel, QPersistentModelIndex, QSize,
                            Qt)
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QDockWidget, QListView

from settings import get_separator


@dataclass
class Image:
    path: Path
    dimensions: tuple[int, int] | None
    tags: list[str] = field(default_factory=list)


class ImageListModel(QAbstractListModel):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.directory_path = None
        self.images = []

    def rowCount(self, parent=None):
        return len(self.images)

    def data(self, index, role=None):
        image = self.images[index.row()]
        image_width = int(self.settings.value('image_list_image_width'))
        if role == Qt.DisplayRole:
            # The text shown next to the image.
            return image.path.name
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

    def load_directory(self, directory_path: Path):
        self.directory_path = directory_path
        self.images.clear()
        file_paths = set(directory_path.glob('*'))
        text_file_paths = set(directory_path.glob('*.txt'))
        image_paths = file_paths - text_file_paths
        text_file_stems = {path.stem for path in text_file_paths}
        image_stems = {path.stem for path in image_paths}
        image_stems_with_captions = image_stems & text_file_stems
        for image_path in image_paths:
            try:
                dimensions = imagesize.get(image_path)
            except ValueError:
                dimensions = None
            if image_path.stem in image_stems_with_captions:
                text_file_path = directory_path / f'{image_path.stem}.txt'
                caption = text_file_path.read_text()
                tags = caption.split(get_separator(self.settings))
                image = Image(image_path, dimensions, tags)
            else:
                image = Image(image_path, dimensions)
            self.images.append(image)
        self.images.sort(key=lambda image_: image_.path.name)

    def update_tags(self, image_index: QPersistentModelIndex, tags: list[str]):
        image = self.images[image_index.row()]
        image.tags = tags
        self.dataChanged.emit(image_index, image_index)


class ImageList(QDockWidget):
    def __init__(self, model: ImageListModel, parent):
        super().__init__(parent)
        self.setObjectName('image_list')
        self.setWindowTitle('Images')
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        # Use a QListView instead of a QListWidget for faster loading.
        self.list_view = QListView(self)
        self.list_view.setWordWrap(True)
        self.list_view.setModel(model)
        self.setWidget(self.list_view)
        self.set_image_width()

    def set_image_width(self):
        self.list_view.setIconSize(
            QSize(self.parent().image_list_image_width,
                  self.parent().image_list_image_width * 4))
