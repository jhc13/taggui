import random
from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path

import imagesize
from PySide6.QtCore import QAbstractListModel, QModelIndex, QSize, Qt, Slot
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QMessageBox

from utils.image import Image
from utils.utils import get_confirmation_dialog_reply

UNDO_STACK_SIZE = 32


@dataclass
class HistoryItem:
    action_name: str
    tags: list[list[str]]
    should_ask_for_confirmation: bool


class ImageListModel(QAbstractListModel):
    def __init__(self, image_list_image_width: int, separator: str):
        super().__init__()
        self.image_list_image_width = image_list_image_width
        self.separator = separator
        self.images = []
        self.undo_stack = deque(maxlen=UNDO_STACK_SIZE)
        self.redo_stack = []

    def rowCount(self, parent=None) -> int:
        return len(self.images)

    def data(self, index, role=None) -> Image | str | QIcon | QSize:
        image = self.images[index.row()]
        if role == Qt.UserRole:
            return image
        if role == Qt.DisplayRole:
            # The text shown next to the thumbnail in the image list.
            text = image.path.name
            if image.tags:
                caption = self.separator.join(image.tags)
                text += f'\n{caption}'
            return text
        if role == Qt.DecorationRole:
            # The thumbnail. If the image already has a thumbnail stored, use
            # it. Otherwise, generate a thumbnail and save it to the image.
            if image.thumbnail:
                return image.thumbnail
            thumbnail = QIcon(
                QPixmap(str(image.path)).scaledToWidth(
                    self.image_list_image_width))
            image.thumbnail = thumbnail
            return thumbnail
        if role == Qt.SizeHintRole:
            dimensions = image.dimensions
            if dimensions:
                width, height = dimensions
                # Scale the dimensions to the image width.
                return QSize(self.image_list_image_width,
                             int(self.image_list_image_width * height / width))
            return QSize(self.image_list_image_width,
                         self.image_list_image_width)

    def get_file_paths(self, directory_path: Path) -> set[Path]:
        """
        Recursively get all file paths in a directory, including those in
        subdirectories.
        """
        file_paths = set()
        for path in directory_path.iterdir():
            if path.is_file():
                file_paths.add(path)
            elif path.is_dir():
                file_paths.update(self.get_file_paths(path))
        return file_paths

    def load_directory(self, directory_path: Path):
        self.images.clear()
        self.undo_stack.clear()
        self.redo_stack.clear()
        file_paths = self.get_file_paths(directory_path)
        text_file_paths = {path for path in file_paths
                           if path.suffix == '.txt'}
        image_paths = file_paths - text_file_paths
        for image_path in image_paths:
            try:
                dimensions = imagesize.get(image_path)
            except ValueError:
                dimensions = None
            tags = []
            text_file_path = image_path.with_suffix('.txt')
            if text_file_path in text_file_paths:
                caption = text_file_path.read_text()
                if caption:
                    tags = caption.split(self.separator)
                    tags = [tag.strip() for tag in tags]
                    tags = [tag for tag in tags if tag]
            image = Image(image_path, dimensions, tags)
            self.images.append(image)
        self.images.sort(key=lambda image_: image_.path)
        self.modelReset.emit()

    def add_to_undo_stack(self, action_name: str,
                          should_ask_for_confirmation: bool):
        """Add the current state of the image tags to the undo stack."""
        tags = [image.tags.copy() for image in self.images]
        self.undo_stack.append(HistoryItem(action_name, tags,
                                           should_ask_for_confirmation))
        self.redo_stack.clear()

    def write_image_tags_to_disk(self, image: Image):
        try:
            image.path.with_suffix('.txt').write_text(
                self.separator.join(image.tags))
        except OSError:
            error_message_box = QMessageBox()
            error_message_box.setWindowTitle('Error')
            error_message_box.setIcon(QMessageBox.Icon.Critical)
            error_message_box.setText(f'An error occurred while saving the '
                                      f'tags for {image.path.name}.')
            error_message_box.exec()

    def update_image_tags(self, image_index: QModelIndex, tags: list[str]):
        image: Image = self.data(image_index, Qt.UserRole)
        if image.tags == tags:
            return
        image.tags = tags
        self.dataChanged.emit(image_index, image_index)
        self.write_image_tags_to_disk(image)

    def restore_history_tags(self, is_undo: bool):
        if is_undo:
            source_stack = self.undo_stack
            destination_stack = self.redo_stack
        else:
            # Redo.
            source_stack = self.redo_stack
            destination_stack = self.undo_stack
        if not source_stack:
            return
        history_item = source_stack[-1]
        if history_item.should_ask_for_confirmation:
            undo_or_redo_string = 'Undo' if is_undo else 'Redo'
            reply = get_confirmation_dialog_reply(
                title=undo_or_redo_string,
                question=f'{undo_or_redo_string} '
                         f'"{history_item.action_name}"?')
            if reply != QMessageBox.StandardButton.Yes:
                return
        source_stack.pop()
        tags = [image.tags for image in self.images]
        destination_stack.append(HistoryItem(
            history_item.action_name, tags,
            history_item.should_ask_for_confirmation))
        changed_image_indices = []
        for image_index, (image, history_image_tags) in enumerate(
                zip(self.images, history_item.tags)):
            if image.tags == history_image_tags:
                continue
            changed_image_indices.append(image_index)
            image.tags = history_image_tags
            self.write_image_tags_to_disk(image)
        if changed_image_indices:
            self.dataChanged.emit(self.index(changed_image_indices[0]),
                                  self.index(changed_image_indices[-1]))

    @Slot()
    def undo(self):
        """Undo the last action."""
        self.restore_history_tags(is_undo=True)

    @Slot()
    def redo(self):
        """Redo the last undone action."""
        self.restore_history_tags(is_undo=False)

    def get_text_match_count(self, text: str) -> int:
        """Get the number of instances of a text in all captions."""
        match_count = 0
        for image in self.images:
            caption = self.separator.join(image.tags)
            match_count += caption.count(text)
        return match_count

    def find_and_replace(self, find_text: str, replace_text: str):
        """
        Find and replace arbitrary text in captions, within and across tag
        boundaries.
        """
        if not find_text:
            return
        self.add_to_undo_stack(action_name='Find and Replace',
                               should_ask_for_confirmation=True)
        changed_image_indices = []
        for image_index, image in enumerate(self.images):
            caption = self.separator.join(image.tags)
            if find_text not in caption:
                continue
            changed_image_indices.append(image_index)
            caption = caption.replace(find_text, replace_text)
            image.tags = caption.split(self.separator)
            self.write_image_tags_to_disk(image)
        if changed_image_indices:
            self.dataChanged.emit(self.index(changed_image_indices[0]),
                                  self.index(changed_image_indices[-1]))

    def sort_tags_alphabetically(self, do_not_reorder_first_tag: bool):
        """Sort the tags for each image in alphabetical order."""
        self.add_to_undo_stack(action_name='Sort Tags',
                               should_ask_for_confirmation=True)
        changed_image_indices = []
        for image_index, image in enumerate(self.images):
            if len(image.tags) < 2:
                continue
            old_caption = self.separator.join(image.tags)
            if do_not_reorder_first_tag:
                first_tag = image.tags[0]
                image.tags = [first_tag] + sorted(image.tags[1:])
            else:
                image.tags.sort()
            new_caption = self.separator.join(image.tags)
            if new_caption != old_caption:
                changed_image_indices.append(image_index)
                self.write_image_tags_to_disk(image)
        if changed_image_indices:
            self.dataChanged.emit(self.index(changed_image_indices[0]),
                                  self.index(changed_image_indices[-1]))

    def sort_tags_by_frequency(self, tag_counter: Counter,
                               do_not_reorder_first_tag: bool):
        """
        Sort the tags for each image by the total number of times a tag appears
        across all images.
        """
        self.add_to_undo_stack(action_name='Sort Tags',
                               should_ask_for_confirmation=True)
        changed_image_indices = []
        for image_index, image in enumerate(self.images):
            if len(image.tags) < 2:
                continue
            old_caption = self.separator.join(image.tags)
            if do_not_reorder_first_tag:
                first_tag = image.tags[0]
                image.tags = [first_tag] + sorted(
                    image.tags[1:], key=lambda tag: tag_counter[tag],
                    reverse=True)
            else:
                image.tags.sort(key=lambda tag: tag_counter[tag], reverse=True)
            new_caption = self.separator.join(image.tags)
            if new_caption != old_caption:
                changed_image_indices.append(image_index)
                self.write_image_tags_to_disk(image)
        if changed_image_indices:
            self.dataChanged.emit(self.index(changed_image_indices[0]),
                                  self.index(changed_image_indices[-1]))

    def shuffle_tags(self, do_not_reorder_first_tag: bool):
        """Shuffle the tags for each image randomly."""
        self.add_to_undo_stack(action_name='Shuffle Tags',
                               should_ask_for_confirmation=True)
        changed_image_indices = []
        for image_index, image in enumerate(self.images):
            if len(image.tags) < 2:
                continue
            changed_image_indices.append(image_index)
            if do_not_reorder_first_tag:
                first_tag, *remaining_tags = image.tags
                random.shuffle(remaining_tags)
                image.tags = [first_tag] + remaining_tags
            else:
                random.shuffle(image.tags)
            self.write_image_tags_to_disk(image)
        if changed_image_indices:
            self.dataChanged.emit(self.index(changed_image_indices[0]),
                                  self.index(changed_image_indices[-1]))

    def remove_duplicate_tags(self) -> int:
        """
        Remove duplicate tags for each image. Return the number of removed
        tags.
        """
        self.add_to_undo_stack(action_name='Remove Duplicate Tags',
                               should_ask_for_confirmation=True)
        changed_image_indices = []
        removed_tag_count = 0
        for image_index, image in enumerate(self.images):
            tag_count = len(image.tags)
            unique_tag_count = len(set(image.tags))
            if tag_count == unique_tag_count:
                continue
            changed_image_indices.append(image_index)
            removed_tag_count += tag_count - unique_tag_count
            # Use a dictionary instead of a set to preserve the order.
            image.tags = list(dict.fromkeys(image.tags))
            self.write_image_tags_to_disk(image)
        if changed_image_indices:
            self.dataChanged.emit(self.index(changed_image_indices[0]),
                                  self.index(changed_image_indices[-1]))
        return removed_tag_count

    def remove_empty_tags(self) -> int:
        """
        Remove empty tags (tags that are empty strings or only contain
        whitespace) for each image. Return the number of removed tags.
        """
        self.add_to_undo_stack(action_name='Remove Empty Tags',
                               should_ask_for_confirmation=True)
        changed_image_indices = []
        removed_tag_count = 0
        for image_index, image in enumerate(self.images):
            old_tag_count = len(image.tags)
            image.tags = [tag for tag in image.tags if tag.strip()]
            new_tag_count = len(image.tags)
            if old_tag_count == new_tag_count:
                continue
            changed_image_indices.append(image_index)
            removed_tag_count += old_tag_count - new_tag_count
            self.write_image_tags_to_disk(image)
        if changed_image_indices:
            self.dataChanged.emit(self.index(changed_image_indices[0]),
                                  self.index(changed_image_indices[-1]))
        return removed_tag_count

    @Slot(str, list)
    def add_tag_to_multiple_images(self, tag: str,
                                   image_indices: list[QModelIndex]):
        """Add a tag to multiple images."""
        self.add_to_undo_stack(action_name='Add Tag',
                               should_ask_for_confirmation=True)
        for image_index in image_indices:
            image: Image = self.data(image_index, Qt.UserRole)
            image.tags.append(tag)
            self.write_image_tags_to_disk(image)
        self.dataChanged.emit(image_indices[0], image_indices[-1])

    @Slot(str, str)
    def rename_tag(self, old_tag: str, new_tag: str):
        """Rename all instances of a tag in all images."""
        self.add_to_undo_stack(action_name='Rename Tag',
                               should_ask_for_confirmation=True)
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
        self.add_to_undo_stack(action_name='Delete Tag',
                               should_ask_for_confirmation=True)
        changed_image_indices = []
        for image_index, image in enumerate(self.images):
            if tag in image.tags:
                changed_image_indices.append(image_index)
                image.tags = [image_tag for image_tag in image.tags
                              if image_tag != tag]
                self.write_image_tags_to_disk(image)
        self.dataChanged.emit(self.index(changed_image_indices[0]),
                              self.index(changed_image_indices[-1]))
