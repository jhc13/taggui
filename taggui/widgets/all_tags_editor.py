from enum import Enum

from PySide6.QtCore import (QItemSelection, QItemSelectionModel, Qt, Signal,
                            Slot)
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (QAbstractItemView, QDockWidget, QHBoxLayout,
                               QLabel, QLineEdit, QListView, QMessageBox,
                               QVBoxLayout, QWidget)

from models.proxy_tag_counter_model import ProxyTagCounterModel
from models.tag_counter_model import TagCounterModel
from utils.big_widgets import TallPushButton
from utils.enums import AllTagsSortBy, SortOrder
from utils.settings_widgets import SettingsComboBox
from utils.text_edit_item_delegate import TextEditItemDelegate
from utils.utils import get_confirmation_dialog_reply, list_with_and, pluralize


class FilterLineEdit(QLineEdit):
    def __init__(self):
        super().__init__()
        self.setPlaceholderText('Search Tags')
        self.setStyleSheet('padding: 8px;')
        self.setClearButtonEnabled(True)


class ClickAction(str, Enum):
    FILTER_IMAGES = 'Filter images for tag'
    ADD_TO_SELECTED = 'Add tag to selected images'


class AllTagsList(QListView):
    image_list_filter_requested = Signal(str)
    tag_addition_requested = Signal(str)
    tags_deletion_requested = Signal(list)

    def __init__(self, proxy_tag_counter_model: ProxyTagCounterModel,
                 all_tags_editor: 'AllTagsEditor'):
        super().__init__()
        self.setModel(proxy_tag_counter_model)
        self.all_tags_editor = all_tags_editor
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setItemDelegate(TextEditItemDelegate(self))
        self.setWordWrap(True)
        # `selectionChanged` must be used and not `currentChanged` because
        # `currentChanged` is not emitted when the same tag is deselected and
        # selected again.
        self.selectionModel().selectionChanged.connect(
            self.handle_selection_change)

    def mousePressEvent(self, event: QMouseEvent):
        click_action = (self.all_tags_editor.click_action_combo_box
                        .currentText())
        if click_action == ClickAction.ADD_TO_SELECTED:
            index = self.indexAt(event.pos())
            tag = index.data(Qt.ItemDataRole.EditRole)
            self.tag_addition_requested.emit(tag)
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        """
        Delete all instances of the selected tag when the delete key is
        pressed.
        """
        if event.key() != Qt.Key.Key_Delete:
            super().keyPressEvent(event)
            return
        selected_indices = self.selectedIndexes()
        if not selected_indices:
            return
        tags = []
        tags_count = 0
        for selected_index in selected_indices:
            tag, tag_count = selected_index.data(Qt.ItemDataRole.UserRole)
            tags.append(tag)
            tags_count += tag_count
        question = (f'Delete {tags_count} {pluralize("instance", tags_count)} '
                    f'of ')
        if len(tags) < 10:
            quoted_tags = [f'"{tag}"' for tag in tags]
            question += (f'{pluralize("tag", len(tags))} '
                         f'{list_with_and(quoted_tags)}?')
        else:
            question += f'{len(tags)} tags?'
        reply = get_confirmation_dialog_reply(
            title=f'Delete {pluralize("Tag", len(tags))}', question=question)
        if reply == QMessageBox.StandardButton.Yes:
            self.tags_deletion_requested.emit(tags)

    def handle_selection_change(self, selected: QItemSelection, _):
        click_action = (self.all_tags_editor.click_action_combo_box
                        .currentText())
        if click_action != ClickAction.FILTER_IMAGES:
            return
        if not selected.indexes():
            return
        selected_tag = selected.indexes()[0].data(Qt.ItemDataRole.EditRole)
        self.image_list_filter_requested.emit(selected_tag)


class AllTagsEditor(QDockWidget):
    def __init__(self, tag_counter_model: TagCounterModel):
        super().__init__()
        self.tag_counter_model = tag_counter_model

        # Each `QDockWidget` needs a unique object name for saving its state.
        self.setObjectName('all_tags_editor')
        self.setWindowTitle('All Tags')
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea
                             | Qt.DockWidgetArea.RightDockWidgetArea)
        self.proxy_tag_counter_model = ProxyTagCounterModel(
            self.tag_counter_model)
        self.proxy_tag_counter_model.setFilterRole(Qt.ItemDataRole.EditRole)
        self.filter_line_edit = FilterLineEdit()
        self.clear_filter_button = TallPushButton('Clear Image Filter')
        self.clear_filter_button.setFixedHeight(
            int(self.clear_filter_button.sizeHint().height() * 1.5))
        click_action_layout = QHBoxLayout()
        click_action_label = QLabel('Tag click action')
        self.click_action_combo_box = SettingsComboBox(
            key='all_tags_click_action')
        self.click_action_combo_box.addItems(list(ClickAction))
        click_action_layout.addWidget(click_action_label)
        click_action_layout.addWidget(self.click_action_combo_box, stretch=1)
        sort_layout = QHBoxLayout()
        sort_label = QLabel('Sort by')
        self.sort_by_combo_box = SettingsComboBox(key='all_tags_sort_by',
                                                  default='Frequency')
        self.sort_by_combo_box.addItems(list(AllTagsSortBy))
        self.sort_by_combo_box.currentTextChanged.connect(self.sort_tags)
        self.sort_order_combo_box = SettingsComboBox(key='all_tags_sort_order',
                                                     default='Descending')
        self.sort_order_combo_box.addItems(list(SortOrder))
        self.sort_order_combo_box.currentTextChanged.connect(self.sort_tags)
        sort_layout.addWidget(sort_label)
        sort_layout.addWidget(self.sort_by_combo_box, stretch=1)
        sort_layout.addWidget(self.sort_order_combo_box, stretch=1)
        self.all_tags_list = AllTagsList(self.proxy_tag_counter_model,
                                         all_tags_editor=self)
        self.tag_count_label = QLabel()
        # A container widget is required to use a layout with a `QDockWidget`.
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self.filter_line_edit)
        layout.addWidget(self.clear_filter_button)
        layout.addLayout(click_action_layout)
        layout.addLayout(sort_layout)
        layout.addWidget(self.all_tags_list)
        layout.addWidget(self.tag_count_label)
        self.setWidget(container)

        self.proxy_tag_counter_model.modelReset.connect(
            self.update_tag_count_label)
        self.proxy_tag_counter_model.rowsInserted.connect(
            self.update_tag_count_label)
        self.proxy_tag_counter_model.rowsRemoved.connect(
            self.update_tag_count_label)
        self.filter_line_edit.textChanged.connect(self.set_filter)
        self.filter_line_edit.textChanged.connect(self.update_tag_count_label)
        self.click_action_combo_box.currentTextChanged.connect(
            self.set_selection_mode)
        self.set_selection_mode(self.click_action_combo_box.currentText())
        self.sort_tags()

    @Slot()
    def sort_tags(self):
        self.proxy_tag_counter_model.sort_by = (self.sort_by_combo_box
                                                .currentText())
        if self.sort_order_combo_box.currentText() == SortOrder.ASCENDING:
            sort_order = Qt.SortOrder.AscendingOrder
        else:
            sort_order = Qt.SortOrder.DescendingOrder
        # `invalidate()` must be called to force the proxy model to re-sort.
        self.proxy_tag_counter_model.invalidate()
        self.proxy_tag_counter_model.sort(0, sort_order)

    @Slot(str)
    def set_filter(self, filter_):
        # Replace escaped wildcard characters to make them compatible with
        # the `fnmatch` module.
        filter_ = filter_.replace(r'\?', '[?]').replace(r'\*', '[*]')
        self.proxy_tag_counter_model.filter = filter_
        # `invalidate()` must be called to force the proxy model to re-filter.
        self.proxy_tag_counter_model.invalidate()

    @Slot()
    def update_tag_count_label(self):
        total_tag_count = self.tag_counter_model.rowCount()
        filtered_tag_count = self.proxy_tag_counter_model.rowCount()
        self.tag_count_label.setText(f'{filtered_tag_count} / '
                                     f'{total_tag_count} Tags')

    @Slot(str)
    def set_selection_mode(self, click_action: str):
        if click_action == ClickAction.FILTER_IMAGES:
            self.all_tags_list.setSelectionMode(
                QAbstractItemView.SelectionMode.ExtendedSelection)
        elif click_action == ClickAction.ADD_TO_SELECTED:
            self.all_tags_list.setSelectionMode(
                QAbstractItemView.SelectionMode.SingleSelection)
            self.all_tags_list.selectionModel().select(
                self.all_tags_list.selectionModel().currentIndex(),
                QItemSelectionModel.SelectionFlag.ClearAndSelect)
