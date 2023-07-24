from pathlib import Path

import imagesize
from PySide6.QtCore import (QAbstractListModel, QPersistentModelIndex,
                            QSettings, QSize, Qt, Slot)
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QMessageBox

from image import Image
from settings import get_separator


class ImageListModel(QAbstractListModel):
    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        self.images = []

    def rowCount(self, parent=None) -> int:
        return len(self.images)

    def data(self, index, role=None) -> Image | str | QIcon | QSize:
        image = self.images[index.row()]
        if role == Qt.UserRole:
            return image
        if role == Qt.DisplayRole:
            # The text shown next to the thumbnail in the image list.
            return image.path.name
        image_width = int(self.settings.value('image_list_image_width'))
        if role == Qt.DecorationRole:
            # The thumbnail.
            pixmap = QPixmap(str(image.path)).scaledToWidth(image_width)
            return QIcon(pixmap)
        if role == Qt.SizeHintRole:
            dimensions = image.dimensions
            if dimensions:
                width, height = dimensions
                # Scale the dimensions to the image width.
                return QSize(image_width, int(image_width * height / width))
            return QSize(image_width, image_width)

    def load_directory(self, path: Path):
        self.images.clear()
        file_paths = set(path.glob('*'))
        text_file_paths = set(path.glob('*.txt'))
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
                text_file_path = path / f'{image_path.stem}.txt'
                caption = text_file_path.read_text()
                if caption:
                    tags = caption.split(get_separator(self.settings))
                else:
                    tags = []
                image = Image(image_path, dimensions, tags)
            else:
                image = Image(image_path, dimensions)
            self.images.append(image)
        self.images.sort(key=lambda image_: image_.path.name)
        self.modelReset.emit()

    def write_image_tags_to_disk(self, image: Image):
        try:
            image.path.with_suffix('.txt').write_text(
                get_separator(self.settings).join(image.tags))
        except OSError:
            error_message_box = QMessageBox()
            error_message_box.setWindowTitle('Error')
            error_message_box.setIcon(QMessageBox.Icon.Critical)
            error_message_box.setText(f'An error occurred while saving the '
                                      f'tags for {image.path.name}.')
            error_message_box.exec()

    def update_image_tags(self, image_index: QPersistentModelIndex,
                          tags: list[str]):
        image: Image = self.data(image_index, Qt.UserRole)
        image.tags = tags
        self.dataChanged.emit(image_index, image_index)
        self.write_image_tags_to_disk(image)

    @Slot(str, str)
    def rename_tag(self, old_tag: str, new_tag: str):
        """Rename all instances of a tag in all images."""
        changed_image_indices = []
        for image_index, image in enumerate(self.images):
            if old_tag in image.tags:
                changed_image_indices.append(image_index)
                image.tags = [new_tag if image_tag == old_tag else image_tag
                              for image_tag in image.tags]
                self.write_image_tags_to_disk(image)
        self.dataChanged.emit(self.index(changed_image_indices[0]),
                              self.index(changed_image_indices[-1]))

    @Slot(str)
    def delete_tag(self, tag: str):
        """Delete all instances of a tag from all images."""
        changed_image_indices = []
        for image_index, image in enumerate(self.images):
            if tag in image.tags:
                changed_image_indices.append(image_index)
                image.tags = [image_tag for image_tag in image.tags
                              if image_tag != tag]
                self.write_image_tags_to_disk(image)
        self.dataChanged.emit(self.index(changed_image_indices[0]),
                              self.index(changed_image_indices[-1]))
