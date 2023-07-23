from pathlib import Path

from PySide6.QtCore import (QModelIndex, QPersistentModelIndex, QSettings,
                            QStringListModel, Qt, Slot)
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (QAbstractItemView, QCompleter, QDockWidget,
                               QLabel, QLineEdit, QListView, QVBoxLayout,
                               QWidget)
from transformers import AutoTokenizer

from image import Image
from image_list import ImageListModel
from settings import get_separator
from tag_counter_model import TagCounterModel

TOKENIZER_PATH = Path('../clip-vit-base-patch32')
MAX_TOKEN_COUNT = 75


class TagInputBox(QLineEdit):
    def __init__(self, image_tag_list_model: QStringListModel,
                 tag_counter_model: TagCounterModel):
        super().__init__()
        self.image_tag_list_model = image_tag_list_model

        completer = QCompleter(tag_counter_model)
        self.setCompleter(completer)
        self.setPlaceholderText('Add tag')
        self.setStyleSheet('padding: 8px;')

        self.returnPressed.connect(self.add_tag, Qt.QueuedConnection)
        completer.activated.connect(self.add_tag, Qt.QueuedConnection)

    @Slot()
    def add_tag(self):
        tag = self.text()
        if not tag:
            return
        # Add an empty tag and set it to the new tag.
        self.image_tag_list_model.insertRow(
            self.image_tag_list_model.rowCount())
        new_tag_index = self.image_tag_list_model.index(
            self.image_tag_list_model.rowCount() - 1)
        self.image_tag_list_model.setData(new_tag_index, tag)
        self.clear()


class ImageTagsList(QListView):
    def __init__(self, image_tag_list_model: QStringListModel):
        super().__init__()
        self.image_tag_list_model = image_tag_list_model
        self.setModel(self.image_tag_list_model)
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSpacing(4)
        self.setWordWrap(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

    def keyPressEvent(self, event: QKeyEvent):
        """Delete selected tags when the delete key is pressed."""
        if event.key() == Qt.Key_Delete:
            # The selected indices must be converted to `QPersistentModelIndex`
            # objects to properly delete multiple tags.
            selected_indices = [QPersistentModelIndex(index) for index
                                in self.selectedIndexes()]
            for index in selected_indices:
                self.image_tag_list_model.removeRow(index.row())
            # The current index is set but not selected automatically after the
            # tags are deleted, so select it.
            self.setCurrentIndex(self.currentIndex())
        else:
            super().keyPressEvent(event)


class ImageTagsEditor(QDockWidget):
    def __init__(self, settings: QSettings, image_list_model: ImageListModel,
                 tag_counter_model: TagCounterModel,
                 image_tag_list_model: QStringListModel):
        super().__init__()
        self.settings = settings
        self.image_list_model = image_list_model
        self.image_tag_list_model = image_tag_list_model
        self.tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_PATH)
        self.image_index = None

        # Each `QDockWidget` needs a unique object name for saving its state.
        self.setObjectName('image_tags_editor')
        self.setWindowTitle('Image Tags')
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.tag_input_box = TagInputBox(self.image_tag_list_model,
                                         tag_counter_model)
        self.image_tags_list = ImageTagsList(self.image_tag_list_model)
        self.token_count_label = QLabel()
        # A container widget is required to use a layout with a `QDockWidget`.
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self.tag_input_box)
        layout.addWidget(self.image_tags_list)
        layout.addWidget(self.token_count_label)
        self.setWidget(container)

        # When a tag is added, select it and scroll to the bottom of the list.
        self.image_tag_list_model.rowsInserted.connect(
            lambda _, __, last_index: self.image_tags_list.setCurrentIndex(
                self.image_tag_list_model.index(last_index)))
        self.image_tag_list_model.rowsInserted.connect(
            self.image_tags_list.scrollToBottom)
        # `rowsInserted` does not have to be connected because `dataChanged`
        # is emitted when a tag is added.
        self.image_tag_list_model.dataChanged.connect(self.count_tokens)
        self.image_tag_list_model.rowsRemoved.connect(self.count_tokens)

    @Slot()
    def count_tokens(self):
        caption = get_separator(self.settings).join(
            self.image_tag_list_model.stringList())
        # Subtract 2 for the `<|startoftext|>` and `<|endoftext|>` tokens.
        caption_token_count = len(self.tokenizer(caption).input_ids) - 2
        if caption_token_count > MAX_TOKEN_COUNT:
            self.token_count_label.setStyleSheet('color: red;')
        else:
            self.token_count_label.setStyleSheet('')
        self.token_count_label.setText(f'{caption_token_count} / '
                                       f'{MAX_TOKEN_COUNT} tokens')

    @Slot()
    def load_image_tags(self, index: QModelIndex):
        # Store the index as a `QPersistentModelIndex` to make sure it stays
        # valid even when the image list is updated.
        persistent_index = QPersistentModelIndex(index)
        self.image_index = persistent_index
        image: Image = self.image_list_model.data(index, Qt.UserRole)
        self.image_tag_list_model.setStringList(image.tags)
        self.count_tokens()
