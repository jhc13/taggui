import random
import re
import sys
from collections import Counter, deque
from dataclasses import dataclass
from enum import Enum
from math import floor, ceil
from pathlib import Path
import json

import exifread
import imagesize
from PySide6.QtCore import (QAbstractListModel, QModelIndex, QPoint, QRect,
                            QSize, Qt, Signal, Slot)
from PySide6.QtGui import QIcon, QImageReader, QPixmap
from PySide6.QtWidgets import QMessageBox

from utils.image import Image, ImageMarking, Marking
from utils.settings import DEFAULT_SETTINGS, settings
from utils.utils import get_confirmation_dialog_reply, pluralize
import utils.target_dimension as target_dimension

UNDO_STACK_SIZE = 32


def get_file_paths(directory_path: Path) -> set[Path]:
    """
    Recursively get all file paths in a directory, including those in
    subdirectories.
    """
    file_paths = set()
    for path in directory_path.iterdir():
        if path.is_file():
            file_paths.add(path)
        elif path.is_dir():
            file_paths.update(get_file_paths(path))
    return file_paths


@dataclass
class HistoryItem:
    action_name: str
    tags: list[dict[str, list[str] | QRect | None | list[Marking]]]
    should_ask_for_confirmation: bool


class Scope(str, Enum):
    ALL_IMAGES = 'All images'
    FILTERED_IMAGES = 'Filtered images'
    SELECTED_IMAGES = 'Selected images'


class ImageListModel(QAbstractListModel):
    update_undo_and_redo_actions_requested = Signal()

    def __init__(self, image_list_image_width: int, tag_separator: str):
        super().__init__()
        self.image_list_image_width = image_list_image_width
        self.tag_separator = tag_separator
        self.images: list[Image] = []
        self.undo_stack = deque(maxlen=UNDO_STACK_SIZE)
        self.redo_stack = []
        self.proxy_image_list_model = None
        self.image_list_selection_model = None

    def rowCount(self, parent=None) -> int:
        return len(self.images)

    def data(self, index, role=None) -> Image | str | QIcon | QSize:
        image = self.images[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return image
        if role == Qt.ItemDataRole.DisplayRole:
            # The text shown next to the thumbnail in the image list.
            text = image.path.name
            if image.tags:
                caption = self.tag_separator.join(image.tags)
                text += f'\n{caption}'
            return text
        if role == Qt.ItemDataRole.DecorationRole:
            # The thumbnail. If the image already has a thumbnail stored, use
            # it. Otherwise, generate a thumbnail and save it to the image.
            if image.thumbnail:
                return image.thumbnail
            image_reader = QImageReader(str(image.path))
            # Rotate the image based on the orientation tag.
            image_reader.setAutoTransform(True)
            if image.crop:
                crop = image.crop
            else:
                crop = QRect(QPoint(0, 0), image_reader.size())
            if crop.height() > crop.width()*3:
                # keep it reasonable, higher than 3x the width doesn't make sense
                crop.setTop((crop.height() - crop.width()*3)//2) # center crop
                crop.setHeight(crop.width()*3)
            image_reader.setClipRect(crop)
            pixmap = QPixmap.fromImageReader(image_reader).scaledToWidth(
                self.image_list_image_width,
                Qt.TransformationMode.SmoothTransformation)
            thumbnail = QIcon(pixmap)
            image.thumbnail = thumbnail
            return thumbnail
        if role == Qt.ItemDataRole.SizeHintRole:
            if image.thumbnail:
                return image.thumbnail.availableSizes()[0]
            dimensions = image.crop.size().toTuple() if image.crop else image.dimensions
            if not dimensions:
                return QSize(self.image_list_image_width,
                             self.image_list_image_width)
            width, height = dimensions
            # Scale the dimensions to the image width.
            return QSize(self.image_list_image_width,
                         int(self.image_list_image_width * min(height / width, 3)))
        if role == Qt.ItemDataRole.ToolTipRole:
            path = image.path.relative_to(settings.value('directory_path', type=str))
            dimensions = f'{image.dimensions[0]}:{image.dimensions[1]}'
            if not image.target_dimension:
                if image.crop:
                    image.target_dimension = target_dimension.get(image.crop.size())
                else:
                    image.target_dimension = target_dimension.get(QSize(*image.dimensions))
            target = f'{image.target_dimension.width()}:{image.target_dimension.height()}'
            return f'{path}\n{dimensions} 🠮 {target}'

    def load_directory(self, directory_path: Path):
        self.images.clear()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.update_undo_and_redo_actions_requested.emit()
        error_messages: list[str] = []
        file_paths = get_file_paths(directory_path)
        image_suffixes_string = settings.value(
            'image_list_file_formats',
            defaultValue=DEFAULT_SETTINGS['image_list_file_formats'], type=str)
        image_suffixes = []
        for suffix in image_suffixes_string.split(','):
            suffix = suffix.strip().lower()
            if not suffix.startswith('.'):
                suffix = '.' + suffix
            image_suffixes.append(suffix)
        image_paths = {path for path in file_paths
                       if path.suffix.lower() in image_suffixes}
        # Comparing paths is slow on some systems, so convert the paths to
        # strings.
        text_file_path_strings = {str(path) for path in file_paths
                                  if path.suffix == '.txt'}
        json_file_path_strings = {str(path) for path in file_paths
                                  if path.suffix == '.json'}
        for image_path in image_paths:
            try:
                dimensions = imagesize.get(image_path)
                # Check the Exif orientation tag and rotate the dimensions if
                # necessary.
                with open(image_path, 'rb') as image_file:
                    try:
                        exif_tags = exifread.process_file(
                            image_file, details=False,
                            stop_tag='Image Orientation')
                        if 'Image Orientation' in exif_tags:
                            orientations = (exif_tags['Image Orientation']
                                            .values)
                            if any(value in orientations
                                   for value in (5, 6, 7, 8)):
                                dimensions = (dimensions[1], dimensions[0])
                    except Exception as exception:
                        error_messages.append(f'Failed to get Exif tags for '
                                              f'{image_path}: {exception}')
            except (ValueError, OSError) as exception:
                error_messages.append(f'Failed to get dimensions for '
                                      f'{image_path}: {exception}')
                dimensions = None
            tags = []
            text_file_path = image_path.with_suffix('.txt')
            if str(text_file_path) in text_file_path_strings:
                # `errors='replace'` inserts a replacement marker such as '?'
                # when there is malformed data.
                caption = text_file_path.read_text(encoding='utf-8',
                                                   errors='replace')
                if caption:
                    tags = caption.split(self.tag_separator)
                    tags = [tag.strip() for tag in tags]
                    tags = [tag for tag in tags if tag]
            image = Image(image_path, dimensions, tags)
            json_file_path = image_path.with_suffix('.json')
            if (str(json_file_path) in json_file_path_strings and
                json_file_path.stat().st_size > 0):
                with json_file_path.open(encoding='UTF-8') as source:
                    try:
                        meta = json.load(source)
                    except json.JSONDecodeError as e:
                        error_messages.append(f'Invalid JSON in '
                                              f'"{json_file_path}": {e.msg}')
                        break
                    except UnicodeDecodeError as e:
                        error_messages.append(f'Invalid Unicode in JSON in '
                                              f'"{json_file_path}": {e.reason}')
                        break

                    if meta.get('version') == 1:
                        crop = meta.get('crop')
                        if crop and type(crop) is list and len(crop) == 4:
                            image.crop = QRect(*crop)
                        rating = meta.get('rating')
                        if rating:
                            image.rating = rating
                        markings = meta.get('markings')
                        if markings and type(markings) is list:
                            for marking in markings:
                                marking = Marking(label=marking.get('label'),
                                                  type=ImageMarking[marking.get('type')],
                                                  rect=QRect(*marking.get('rect')),
                                                  confidence=marking.get('confidence', 1.0))
                                image.markings.append(marking)
                    else:
                        error_messages.append(f'Invalid version '
                                              f'"{meta.get('version')}" in '
                                              f'"{json_file_path}"')
            self.images.append(image)
        self.images.sort(key=lambda image_: image_.path)
        self.modelReset.emit()
        if len(error_messages) > 0:
            print('\n'.join(error_messages), file=sys.stderr)
            error_message_box = QMessageBox()
            error_message_box.setWindowTitle('Directory reading error')
            error_message_box.setIcon(QMessageBox.Icon.Warning)
            error_message_box.setText('\n'.join(error_messages))
            error_message_box.exec()

    def add_to_undo_stack(self, action_name: str,
                          should_ask_for_confirmation: bool):
        """Add the current state of the image tags to the undo stack."""
        tags = [{'tags': image.tags.copy(),
                 'rating': image.rating,
                 'crop': QRect(image.crop) if image.crop is not None else None,
                 'markings': image.markings.copy()} for image in self.images]
        self.undo_stack.append(HistoryItem(action_name, tags,
                                           should_ask_for_confirmation))
        self.redo_stack.clear()
        self.update_undo_and_redo_actions_requested.emit()

    def write_image_tags_to_disk(self, image: Image):
        try:
            image.path.with_suffix('.txt').write_text(
                self.tag_separator.join(image.tags), encoding='utf-8',
                errors='replace')
        except OSError:
            error_message_box = QMessageBox()
            error_message_box.setWindowTitle('Error')
            error_message_box.setIcon(QMessageBox.Icon.Critical)
            error_message_box.setText(f'Failed to save tags for {image.path}.')
            error_message_box.exec()

    def write_meta_to_disk(self, image: Image):
        does_exist = image.path.with_suffix('.json').exists()
        meta: dict[str, any] = {'version': 1, 'rating': image.rating}
        if image.crop is not None:
            meta['crop'] = image.crop.getRect()
        meta['markings'] = [{'label': marking.label,
                             'type': marking.type.name,
                             'confidence': marking.confidence,
                             'rect': marking.rect.getRect()} for marking in image.markings]
        if does_exist or len(meta.keys()) > 1:
            try:
                with image.path.with_suffix('.json').open('w', encoding='UTF-8') as meta_file:
                    json.dump(meta, meta_file)
            except OSError:
                error_message_box = QMessageBox()
                error_message_box.setWindowTitle('Error')
                error_message_box.setIcon(QMessageBox.Icon.Critical)
                error_message_box.setText(f'Failed to save JSON for {image.path}.')
                error_message_box.exec()

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
        tags = [{'tags': image.tags.copy(),
                 'rating': image.rating,
                 'crop': QRect(image.crop) if image.crop is not None else None,
                 'markings': image.markings.copy()} for image in self.images]
        destination_stack.append(HistoryItem(
            history_item.action_name, tags,
            history_item.should_ask_for_confirmation))
        changed_image_indices = []
        for image_index, (image, history_image_tags) in enumerate(
                zip(self.images, history_item.tags)):
            if (image.tags == history_image_tags['tags'] and
                image.rating == history_image_tags['rating'] and
                image.crop == history_image_tags['crop'] and
                image.markings == history_image_tags['markings']):
                continue
            changed_image_indices.append(image_index)
            image.tags = history_image_tags['tags']
            image.rating = history_image_tags['rating']
            image.crop = history_image_tags['crop']
            image.markings = history_image_tags['markings']
            self.write_image_tags_to_disk(image)
            self.write_meta_to_disk(image)
        if changed_image_indices:
            self.dataChanged.emit(self.index(changed_image_indices[0]),
                                  self.index(changed_image_indices[-1]))
        self.update_undo_and_redo_actions_requested.emit()

    @Slot()
    def undo(self):
        """Undo the last action."""
        self.restore_history_tags(is_undo=True)

    @Slot()
    def redo(self):
        """Redo the last undone action."""
        self.restore_history_tags(is_undo=False)

    def is_image_in_scope(self, scope: Scope | str, image_index: int,
                          image: Image) -> bool:
        if scope == Scope.ALL_IMAGES:
            return True
        if scope == Scope.FILTERED_IMAGES:
            return self.proxy_image_list_model.is_image_in_filtered_images(
                image)
        if scope == Scope.SELECTED_IMAGES:
            proxy_index = self.proxy_image_list_model.mapFromSource(
                self.index(image_index))
            return self.image_list_selection_model.isSelected(proxy_index)

    def get_text_match_count(self, text: str, scope: Scope | str,
                             whole_tags_only: bool, use_regex: bool) -> int:
        """Get the number of instances of a text in all captions."""
        match_count = 0
        for image_index, image in enumerate(self.images):
            if not self.is_image_in_scope(scope, image_index, image):
                continue
            if whole_tags_only:
                if use_regex:
                    match_count += len([
                        tag for tag in image.tags
                        if re.fullmatch(pattern=text, string=tag)
                    ])
                else:
                    match_count += image.tags.count(text)
            else:
                caption = self.tag_separator.join(image.tags)
                if use_regex:
                    match_count += len(re.findall(pattern=text,
                                                  string=caption))
                else:
                    match_count += caption.count(text)
        return match_count

    def find_and_replace(self, find_text: str, replace_text: str,
                         scope: Scope | str, use_regex: bool):
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
            if not self.is_image_in_scope(scope, image_index, image):
                continue
            caption = self.tag_separator.join(image.tags)
            if use_regex:
                if not re.search(pattern=find_text, string=caption):
                    continue
                caption = re.sub(pattern=find_text, repl=replace_text,
                                 string=caption)
            else:
                if find_text not in caption:
                    continue
                caption = caption.replace(find_text, replace_text)
            changed_image_indices.append(image_index)
            image.tags = caption.split(self.tag_separator)
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
            old_caption = self.tag_separator.join(image.tags)
            if do_not_reorder_first_tag:
                first_tag = image.tags[0]
                image.tags = [first_tag] + sorted(image.tags[1:])
            else:
                image.tags.sort()
            new_caption = self.tag_separator.join(image.tags)
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
            old_caption = self.tag_separator.join(image.tags)
            if do_not_reorder_first_tag:
                first_tag = image.tags[0]
                image.tags = [first_tag] + sorted(
                    image.tags[1:], key=lambda tag: tag_counter[tag],
                    reverse=True)
            else:
                image.tags.sort(key=lambda tag: tag_counter[tag], reverse=True)
            new_caption = self.tag_separator.join(image.tags)
            if new_caption != old_caption:
                changed_image_indices.append(image_index)
                self.write_image_tags_to_disk(image)
        if changed_image_indices:
            self.dataChanged.emit(self.index(changed_image_indices[0]),
                                  self.index(changed_image_indices[-1]))

    def reverse_tags_order(self, do_not_reorder_first_tag: bool):
        """Reverse the order of the tags for each image."""
        self.add_to_undo_stack(action_name='Reverse Order of Tags',
                               should_ask_for_confirmation=True)
        changed_image_indices = []
        for image_index, image in enumerate(self.images):
            if len(image.tags) < 2:
                continue
            changed_image_indices.append(image_index)
            if do_not_reorder_first_tag:
                image.tags = [image.tags[0]] + list(reversed(image.tags[1:]))
            else:
                image.tags = list(reversed(image.tags))
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

    def sort_sentences_down(self, separate_newline: bool):
        """Sort the tags so that the sentences are on the bottom."""
        self.add_to_undo_stack(action_name='Sort Sentence Tags',
                               should_ask_for_confirmation=True)
        changed_image_indices = []
        for image_index, image in enumerate(self.images):
            changed_image_indices.append(image_index)
            sentence_tags = []
            non_sentence_tags = []
            for tag in image.tags:
                if separate_newline and tag == '#newline':
                    continue
                if tag.endswith('.'):
                    sentence_tags.append(tag)
                else:
                    non_sentence_tags.append(tag)
            if separate_newline:
                if len(sentence_tags) > 0:
                    non_sentence_tags.append(sentence_tags.pop())
                for tag in sentence_tags:
                    non_sentence_tags.append('#newline')
                    non_sentence_tags.append(tag)
            else:
                non_sentence_tags.extend(sentence_tags)
            image.tags = non_sentence_tags
            self.write_image_tags_to_disk(image)
        if changed_image_indices:
            self.dataChanged.emit(self.index(changed_image_indices[0]),
                                  self.index(changed_image_indices[-1]))

    def move_tags_to_front(self, tags_to_move: list[str]):
        """
        Move one or more tags to the front of the tags list for each image.
        """
        self.add_to_undo_stack(action_name='Move Tags to Front',
                               should_ask_for_confirmation=True)
        changed_image_indices = []
        for image_index, image in enumerate(self.images):
            if not any(tag in image.tags for tag in tags_to_move):
                continue
            old_caption = self.tag_separator.join(image.tags)
            moved_tags = []
            for tag in tags_to_move:
                tag_count = image.tags.count(tag)
                moved_tags.extend([tag] * tag_count)
            unmoved_tags = [tag for tag in image.tags if tag not in moved_tags]
            image.tags = moved_tags + unmoved_tags
            new_caption = self.tag_separator.join(image.tags)
            if new_caption != old_caption:
                changed_image_indices.append(image_index)
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

    def update_image_tags(self, image_index: QModelIndex, tags: list[str]):
        image: Image = self.data(image_index, Qt.ItemDataRole.UserRole)
        if image.tags == tags:
            return
        image.tags = tags
        self.dataChanged.emit(image_index, image_index)
        self.write_image_tags_to_disk(image)

    @Slot(list, list)
    def add_tags(self, tags: list[str], image_indices: list[QModelIndex]):
        """Add one or more tags to one or more images."""
        if not image_indices:
            return
        action_name = f'Add {pluralize("Tag", len(tags))}'
        should_ask_for_confirmation = len(image_indices) > 1
        self.add_to_undo_stack(action_name, should_ask_for_confirmation)
        for image_index in image_indices:
            image: Image = self.data(image_index, Qt.ItemDataRole.UserRole)
            image.tags.extend(tags)
            self.write_image_tags_to_disk(image)
        min_image_index = min(image_indices, key=lambda index: index.row())
        max_image_index = max(image_indices, key=lambda index: index.row())
        self.dataChanged.emit(min_image_index, max_image_index)

    @Slot(list, str)
    def rename_tags(self, old_tags: list[str], new_tag: str,
                    scope: Scope | str = Scope.ALL_IMAGES,
                    use_regex: bool = False):
        self.add_to_undo_stack(
            action_name=f'Rename {pluralize("Tag", len(old_tags))}',
            should_ask_for_confirmation=True)
        changed_image_indices = []
        for image_index, image in enumerate(self.images):
            if not self.is_image_in_scope(scope, image_index, image):
                continue
            if use_regex:
                pattern = old_tags[0]
                if not any(re.fullmatch(pattern=pattern, string=image_tag)
                           for image_tag in image.tags):
                    continue
                image.tags = [new_tag if re.fullmatch(pattern=pattern,
                                                      string=image_tag)
                              else image_tag for image_tag in image.tags]
            else:
                if not any(old_tag in image.tags for old_tag in old_tags):
                    continue
                image.tags = [new_tag if image_tag in old_tags else image_tag
                              for image_tag in image.tags]
            changed_image_indices.append(image_index)
            self.write_image_tags_to_disk(image)
        if changed_image_indices:
            self.dataChanged.emit(self.index(changed_image_indices[0]),
                                  self.index(changed_image_indices[-1]))

    @Slot(list)
    def delete_tags(self, tags: list[str],
                    scope: Scope | str = Scope.ALL_IMAGES,
                    use_regex: bool = False):
        self.add_to_undo_stack(
            action_name=f'Delete {pluralize("Tag", len(tags))}',
            should_ask_for_confirmation=True)
        changed_image_indices = []
        for image_index, image in enumerate(self.images):
            if not self.is_image_in_scope(scope, image_index, image):
                continue
            if use_regex:
                pattern = tags[0]
                if not any(re.fullmatch(pattern=pattern, string=image_tag)
                           for image_tag in image.tags):
                    continue
                image.tags = [image_tag for image_tag in image.tags
                              if not re.fullmatch(pattern=pattern,
                                                  string=image_tag)]
            else:
                if not any(tag in image.tags for tag in tags):
                    continue
                image.tags = [image_tag for image_tag in image.tags
                              if image_tag not in tags]
            changed_image_indices.append(image_index)
            self.write_image_tags_to_disk(image)
        if changed_image_indices:
            self.dataChanged.emit(self.index(changed_image_indices[0]),
                                  self.index(changed_image_indices[-1]))

    def add_image_markings(self, image_index: QModelIndex, markings: list[dict]):
        image: Image = self.data(image_index, Qt.ItemDataRole.UserRole)
        for marking in markings:
            marking_type = {
                'hint': ImageMarking.HINT,
                'include': ImageMarking.INCLUDE,
                'exclude': ImageMarking.EXCLUDE}[marking['type']]
            box = marking['box']
            top_left = QPoint(floor(box[0]), floor(box[1]))
            bottom_right = QPoint(ceil(box[2]), ceil(box[3]))
            image.markings.append(Marking(label=marking['label'],
                                          type=marking_type,
                                          rect=QRect(top_left, bottom_right),
                                          confidence=marking['confidence']))
        if len(markings) > 0:
            self.dataChanged.emit(image_index, image_index)
            self.write_meta_to_disk(image)
