import operator
from pathlib import Path

from PySide6.QtCore import QPersistentModelIndex, QStringListModel, Qt, Slot
from PySide6.QtWidgets import (QAbstractItemView, QCompleter, QDockWidget,
                               QLabel, QLineEdit, QListView, QVBoxLayout,
                               QWidget)
from transformers import AutoTokenizer

from image_list import ImageListModel
from settings import get_separator
from tag_counter_model import TagCounterModel

TOKENIZER_PATH = Path('../tokenizer')


class TagInputBox(QLineEdit):
    def __init__(self, image_list: QDockWidget,
                 tag_list_model: QStringListModel,
                 tag_counter_model: TagCounterModel, parent):
        super().__init__(parent)
        self.image_list = image_list
        self.tag_list_model = tag_list_model
        self.parent = parent
        completer = QCompleter(tag_counter_model, self)
        completer.activated.connect(self.add_tag, Qt.QueuedConnection)
        self.setCompleter(completer)
        self.setStyleSheet('padding: 8px;')
        self.setPlaceholderText('Add tag')
        self.returnPressed.connect(self.add_tag, Qt.QueuedConnection)

    def keyPressEvent(self, event):
        image_list_view = self.image_list.list_view
        if event.key() in (Qt.Key_Up, Qt.Key_Down):
            operator_ = (operator.add if event.key() == Qt.Key_Down
                         else operator.sub)
            new_index = image_list_view.currentIndex().siblingAtRow(
                image_list_view.currentIndex().row() + operator_(0, 1))
            if new_index.isValid():
                image_list_view.setCurrentIndex(new_index)
        else:
            super().keyPressEvent(event)

    @Slot()
    def add_tag(self):
        tag = self.text()
        if not tag:
            return
        self.tag_list_model.insertRow(self.tag_list_model.rowCount())
        new_tag_index = self.tag_list_model.index(
            self.tag_list_model.rowCount() - 1)
        self.tag_list_model.setData(new_tag_index, tag)
        self.clear()
        self.parent.image_tag_list.setCurrentIndex(new_tag_index)
        self.parent.image_tag_list.scrollToBottom()


class ImageTagList(QListView):
    def __init__(self, model: QStringListModel, parent):
        super().__init__(parent)
        self.model = model
        self.setModel(self.model)
        self.setSpacing(4)
        self.setWordWrap(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            selected_indexes = [QPersistentModelIndex(index) for index
                                in self.selectedIndexes()]
            for index in selected_indexes:
                self.model.removeRow(index.row())
            # Select the next tag in the list, or the last tag if there is no
            # next tag.
            index_to_select = (
                self.model.index(self.currentIndex().row() + 1, 0)
                if self.currentIndex().row() + 1 < self.model.rowCount()
                else self.model.index(self.model.rowCount() - 1, 0))
            self.setCurrentIndex(index_to_select)
        else:
            super().keyPressEvent(event)


class ImageTagEditor(QDockWidget):
    def __init__(self, tag_counter_model: TagCounterModel,
                 image_list_model: ImageListModel, image_list: QDockWidget,
                 settings, parent):
        super().__init__(parent)
        self.image_list_model = image_list_model
        self.settings = settings
        self.tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_PATH)

        self.setObjectName('image_tag_editor')
        self.setWindowTitle('Tags')
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self.image_index = None
        self.tag_list_model = QStringListModel(self)
        # `rowsInserted` does not have to be connected because `dataChanged`
        # is emitted when a tag is added.
        self.tag_list_model.dataChanged.connect(self.update_image_list_model)
        self.tag_list_model.rowsRemoved.connect(self.update_image_list_model)
        self.tag_list_model.dataChanged.connect(self.count_tokens)
        self.tag_list_model.rowsRemoved.connect(self.count_tokens)

        tag_input_box = TagInputBox(image_list, self.tag_list_model,
                                    tag_counter_model, self)
        self.image_tag_list = ImageTagList(self.tag_list_model, self)
        self.token_count_label = QLabel(self)
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.addWidget(tag_input_box)
        layout.addWidget(self.image_tag_list)
        layout.addWidget(self.token_count_label)
        self.setWidget(container)

    def load_tags(self, index: QPersistentModelIndex, tags: list[str]):
        self.image_index = index
        self.tag_list_model.setStringList(tags)

    @Slot()
    def update_image_list_model(self):
        self.image_list_model.update_tags(self.image_index,
                                          self.tag_list_model.stringList())

    @Slot()
    def count_tokens(self):
        caption = get_separator(self.settings).join(
            self.tag_list_model.stringList())
        # Subtract 2 for the `<|startoftext|>` and `<|endoftext|>` tokens.
        caption_token_count = len(self.tokenizer(caption).input_ids) - 2
        if caption_token_count > 75:
            self.token_count_label.setStyleSheet('color: red;')
        else:
            self.token_count_label.setStyleSheet('')
        self.token_count_label.setText(f'{caption_token_count} / 75 tokens')
