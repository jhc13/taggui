import shutil
from enum import Enum
from functools import reduce
from operator import or_
from pathlib import Path

from PySide6.QtCore import (QFile, QItemSelection, QItemSelectionModel,
                            QItemSelectionRange, QModelIndex, QSize, QUrl, Qt,
                            Signal, Slot, QPersistentModelIndex)
from PySide6.QtGui import QDesktopServices, QColor, QPixmap, QPainter, QDrag
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QDockWidget,
                               QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QListView, QMenu, QMessageBox, QVBoxLayout,
                               QWidget, QStyledItemDelegate)
from pyparsing import (CaselessKeyword, CaselessLiteral, Group, OpAssoc,
                       ParseException, QuotedString, Suppress, Word,
                       infix_notation, nums, one_of, printables)

from models.proxy_image_list_model import ProxyImageListModel
from utils.image import Image
from utils.settings import settings
from utils.settings_widgets import SettingsComboBox
from utils.utils import get_confirmation_dialog_reply, pluralize
from utils.grid import Grid


def replace_filter_wildcards(filter_: str | list) -> str | list:
    """
    Replace escaped wildcard characters to make them compatible with the
    `fnmatch` module.
    """
    if isinstance(filter_, str):
        filter_ = filter_.replace(r'\*', '[*]').replace(r'\?', '[?]')
        return filter_
    replaced_filter = []
    for element in filter_:
        replaced_element = replace_filter_wildcards(element)
        replaced_filter.append(replaced_element)
    return replaced_filter


class FilterLineEdit(QLineEdit):
    def __init__(self):
        super().__init__()
        self.setPlaceholderText('Filter Images')
        self.setStyleSheet('padding: 8px;')
        self.setClearButtonEnabled(True)
        optionally_quoted_string = (QuotedString(quote_char='"', esc_char='\\')
                                    | QuotedString(quote_char="'",
                                                   esc_char='\\')
                                    | Word(printables, exclude_chars='()'))
        string_filter_keys = ['tag', 'caption', 'marking', 'crops', 'visible',
                              'name', 'path', 'size', 'target']
        string_filter_expressions = [Group(CaselessLiteral(key) + Suppress(':')
                                           + optionally_quoted_string)
                                     for key in string_filter_keys]
        comparison_operator = one_of('= == != < > <= >=')
        number_filter_keys = ['tags', 'chars', 'tokens', 'stars', 'width',
                              'height', 'area']
        number_filter_expressions = [Group(CaselessLiteral(key) + Suppress(':')
                                           + comparison_operator + Word(nums))
                                     for key in number_filter_keys]
        string_filter_expressions = reduce(or_, string_filter_expressions)
        number_filter_expressions = reduce(or_, number_filter_expressions)
        filter_expressions = (string_filter_expressions
                              | number_filter_expressions
                              | optionally_quoted_string)
        self.filter_text_parser = infix_notation(
            filter_expressions,
            # Operator, number of operands, associativity.
            [(CaselessKeyword('NOT'), 1, OpAssoc.RIGHT),
             (CaselessKeyword('AND'), 2, OpAssoc.LEFT),
             (CaselessKeyword('OR'), 2, OpAssoc.LEFT)])

    def parse_filter_text(self) -> list | str | None:
        filter_text = self.text()
        if not filter_text:
            self.setStyleSheet('padding: 8px;')
            return None
        try:
            filter_ = self.filter_text_parser.parse_string(
                filter_text, parse_all=True).as_list()[0]
            filter_ = replace_filter_wildcards(filter_)
            self.setStyleSheet('padding: 8px;')
            return filter_
        except ParseException:
            # Change the background color when the filter text is invalid.
            if self.palette().color(self.backgroundRole()).lightness() < 128:
                # Dark red for dark mode.
                self.setStyleSheet('padding: 8px; background-color: #442222;')
            else:
                # Light red for light mode.
                self.setStyleSheet('padding: 8px; background-color: #ffdddd;')
            return None


class SelectionMode(str, Enum):
    DEFAULT = 'Default'
    TOGGLE = 'Toggle'


class ImageDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.labels = {}

    def sizeHint(self, option, index):
        return index.data(Qt.ItemDataRole.SizeHintRole)

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        p_index = QPersistentModelIndex(index)
        if p_index in self.labels:
            label_text = self.labels[p_index]
            painter.setBrush(QColor(255, 255, 255, 163))
            painter.drawRect(option.rect)
            painter.drawText(option.rect, label_text, Qt.AlignCenter)

    def update_label(self, index: QModelIndex, label: str):
        p_index = QPersistentModelIndex(index)
        self.labels[p_index] = label
        self.parent().update(p_index)

    def remove_label(self, index: QPersistentModelIndex):
        p_index = QPersistentModelIndex(index)
        if p_index in self.labels:
            del self.labels[p_index]
            self.parent().update(index)


class ImageListView(QListView):
    tags_paste_requested = Signal(list, list)
    directory_reload_requested = Signal()

    def __init__(self, parent, proxy_image_list_model: ProxyImageListModel,
                 tag_separator: str, image_width: int):
        super().__init__(parent)
        self.proxy_image_list_model = proxy_image_list_model
        self.tag_separator = tag_separator
        self.setModel(proxy_image_list_model)
        self.delegate = ImageDelegate(self)
        self.setItemDelegate(self.delegate)
        self.setWordWrap(True)
        self.setDragEnabled(True)
        # If the actual height of the image is greater than 3 times the width,
        # the image will be scaled down to fit.
        self.setIconSize(QSize(image_width, image_width * 3))

        invert_selection_action = self.addAction('Invert Selection')
        invert_selection_action.setShortcut('Ctrl+I')
        invert_selection_action.triggered.connect(self.invert_selection)
        copy_tags_action = self.addAction('Copy Tags')
        copy_tags_action.setShortcut('Ctrl+C')
        copy_tags_action.triggered.connect(
            self.copy_selected_image_tags)
        paste_tags_action = self.addAction('Paste Tags')
        paste_tags_action.setShortcut('Ctrl+V')
        paste_tags_action.triggered.connect(
            self.paste_tags)
        self.copy_file_names_action = self.addAction('Copy File Name')
        self.copy_file_names_action.setShortcut('Ctrl+Alt+C')
        self.copy_file_names_action.triggered.connect(
            self.copy_selected_image_file_names)
        self.copy_paths_action = self.addAction('Copy Path')
        self.copy_paths_action.setShortcut('Ctrl+Shift+C')
        self.copy_paths_action.triggered.connect(
            self.copy_selected_image_paths)
        self.move_images_action = self.addAction('Move Images to...')
        self.move_images_action.setShortcut('Ctrl+M')
        self.move_images_action.triggered.connect(
            self.move_selected_images)
        self.copy_images_action = self.addAction('Copy Images to...')
        self.copy_images_action.setShortcut('Ctrl+Shift+M')
        self.copy_images_action.triggered.connect(
            self.copy_selected_images)
        self.delete_images_action = self.addAction('Delete Images')
        # Setting the shortcut to `Del` creates a conflict with tag deletion.
        self.delete_images_action.setShortcut('Ctrl+Del')
        self.delete_images_action.triggered.connect(
            self.delete_selected_images)
        self.open_image_action = self.addAction('Open Image in Default App')
        self.open_image_action.setShortcut('Ctrl+O')
        self.open_image_action.triggered.connect(self.open_image)

        self.context_menu = QMenu(self)
        self.context_menu.addAction('Select All Images', self.selectAll,
                                    shortcut='Ctrl+A')
        self.context_menu.addAction(invert_selection_action)
        self.context_menu.addSeparator()
        self.context_menu.addAction(copy_tags_action)
        self.context_menu.addAction(paste_tags_action)
        self.context_menu.addAction(self.copy_file_names_action)
        self.context_menu.addAction(self.copy_paths_action)
        self.context_menu.addSeparator()
        self.context_menu.addAction(self.move_images_action)
        self.context_menu.addAction(self.copy_images_action)
        self.context_menu.addAction(self.delete_images_action)
        self.context_menu.addAction(self.open_image_action)
        self.selectionModel().selectionChanged.connect(
            self.update_context_menu_actions)

    def contextMenuEvent(self, event):
        self.context_menu.exec_(event.globalPos())

    def startDrag(self, supportedActions: Qt.DropAction):
        indices = self.selectedIndexes()
        if not indices:
            return

        # Use mimeData from the model.
        mime_data = self.model().mimeData(indices)
        if not mime_data:
            return

        # The pixmap is just the icon of the first selected item.
        # This avoids including the text.
        icon = indices[0].data(Qt.ItemDataRole.DecorationRole)
        pixmap = icon.pixmap(self.iconSize())

        # Create a new pixmap with transparency for the drag image.
        drag_pixmap = QPixmap(pixmap.size())
        drag_pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(drag_pixmap)
        painter.setOpacity(0.7)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()

        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.setPixmap(drag_pixmap)
        drag.setHotSpot(drag_pixmap.rect().center())
        drag.exec(supportedActions)

    @Slot(Grid)
    def show_crop_size(self, grid):
        index = self.currentIndex()
        if index.isValid():
            image = index.data(Qt.ItemDataRole.UserRole)
            if grid is None:
                self.delegate.remove_label(index)
            else:
                crop_delta = grid.screen.size() - grid.visible.size()
                crop_fit = max(crop_delta.width(), crop_delta.height())
                crop_fit_text = f' (-{crop_fit})' if crop_fit > 0 else ''
                label = f'image: {image.dimensions[0]}x{image.dimensions[1]}\n'\
                        f'crop: {grid.screen.width()}x{grid.screen.height()}{crop_fit_text}\n'\
                        f'target: {grid.target.width()}x{grid.target.height()}'
                if grid.aspect_ratio is not None:
                    label += '✅' if grid.aspect_ratio[2] else ''
                    label += f'  {grid.aspect_ratio[0]}:{grid.aspect_ratio[1]}'
                self.delegate.update_label(index, label)

    @Slot()
    def invert_selection(self):
        selected_proxy_rows = {index.row() for index in self.selectedIndexes()}
        all_proxy_rows = set(range(self.proxy_image_list_model.rowCount()))
        unselected_proxy_rows = all_proxy_rows - selected_proxy_rows
        first_unselected_proxy_row = min(unselected_proxy_rows, default=0)
        item_selection = QItemSelection()
        for row in unselected_proxy_rows:
            item_selection.append(
                QItemSelectionRange(self.proxy_image_list_model.index(row, 0)))
        self.setCurrentIndex(self.model().index(first_unselected_proxy_row, 0))
        self.selectionModel().select(
            item_selection, QItemSelectionModel.SelectionFlag.ClearAndSelect)

    def get_selected_images(self) -> list[Image]:
        selected_image_proxy_indices = self.selectedIndexes()
        selected_images = [index.data(Qt.ItemDataRole.UserRole)
                           for index in selected_image_proxy_indices]
        return selected_images

    @Slot()
    def copy_selected_image_tags(self):
        selected_images = self.get_selected_images()
        selected_image_captions = [self.tag_separator.join(image.tags)
                                   for image in selected_images]
        QApplication.clipboard().setText('\n'.join(selected_image_captions))

    def get_selected_image_indices(self) -> list[QModelIndex]:
        selected_image_proxy_indices = self.selectedIndexes()
        selected_image_indices = [
            self.proxy_image_list_model.mapToSource(proxy_index)
            for proxy_index in selected_image_proxy_indices]
        return selected_image_indices

    @Slot()
    def paste_tags(self):
        selected_image_count = len(self.selectedIndexes())
        if selected_image_count > 1:
            reply = get_confirmation_dialog_reply(
                title='Paste Tags',
                question=f'Paste tags to {selected_image_count} selected '
                         f'images?')
            if reply != QMessageBox.StandardButton.Yes:
                return
        tags = QApplication.clipboard().text().split(self.tag_separator)
        selected_image_indices = self.get_selected_image_indices()
        self.tags_paste_requested.emit(tags, selected_image_indices)

    @Slot()
    def copy_selected_image_file_names(self):
        selected_images = self.get_selected_images()
        selected_image_file_names = [image.path.name
                                     for image in selected_images]
        QApplication.clipboard().setText('\n'.join(selected_image_file_names))

    @Slot()
    def copy_selected_image_paths(self):
        selected_images = self.get_selected_images()
        selected_image_paths = [str(image.path) for image in selected_images]
        QApplication.clipboard().setText('\n'.join(selected_image_paths))

    @Slot()
    def move_selected_images(self):
        selected_images = self.get_selected_images()
        selected_image_count = len(selected_images)
        caption = (f'Select directory to move {selected_image_count} selected '
                   f'{pluralize("Image", selected_image_count)} and '
                   f'{pluralize("caption", selected_image_count)} to')
        move_directory_path = QFileDialog.getExistingDirectory(
            parent=self, caption=caption,
            dir=settings.value('directory_path', type=str))
        if not move_directory_path:
            return
        move_directory_path = Path(move_directory_path)
        for image in selected_images:
            try:
                image.path.replace(move_directory_path / image.path.name)
                caption_file_path = image.path.with_suffix('.txt')
                if caption_file_path.exists():
                    caption_file_path.replace(
                        move_directory_path / caption_file_path.name)
            except OSError:
                QMessageBox.critical(self, 'Error',
                                     f'Failed to move {image.path} to '
                                     f'{move_directory_path}.')
        self.directory_reload_requested.emit()

    @Slot()
    def copy_selected_images(self):
        selected_images = self.get_selected_images()
        selected_image_count = len(selected_images)
        caption = (f'Select directory to copy {selected_image_count} selected '
                   f'{pluralize("Image", selected_image_count)} and '
                   f'{pluralize("caption", selected_image_count)} to')
        copy_directory_path = QFileDialog.getExistingDirectory(
            parent=self, caption=caption,
            dir=settings.value('directory_path', type=str))
        if not copy_directory_path:
            return
        copy_directory_path = Path(copy_directory_path)
        for image in selected_images:
            try:
                shutil.copy(image.path, copy_directory_path)
                caption_file_path = image.path.with_suffix('.txt')
                if caption_file_path.exists():
                    shutil.copy(caption_file_path, copy_directory_path)
            except OSError:
                QMessageBox.critical(self, 'Error',
                                     f'Failed to copy {image.path} to '
                                     f'{copy_directory_path}.')

    @Slot()
    def delete_selected_images(self):
        selected_images = self.get_selected_images()
        selected_image_count = len(selected_images)
        title = f'Delete {pluralize("Image", selected_image_count)}'
        question = (f'Delete {selected_image_count} selected '
                    f'{pluralize("image", selected_image_count)} and '
                    f'{"its" if selected_image_count == 1 else "their"} '
                    f'{pluralize("caption", selected_image_count)}?')
        reply = get_confirmation_dialog_reply(title, question)
        if reply != QMessageBox.StandardButton.Yes:
            return
        for image in selected_images:
            image_file = QFile(image.path)
            if not image_file.moveToTrash():
                QMessageBox.critical(self, 'Error',
                                     f'Failed to delete {image.path}.')
            caption_file_path = image.path.with_suffix('.txt')
            caption_file = QFile(caption_file_path)
            if caption_file.exists():
                if not caption_file.moveToTrash():
                    QMessageBox.critical(self, 'Error',
                                         f'Failed to delete '
                                         f'{caption_file_path}.')
        self.directory_reload_requested.emit()

    @Slot()
    def open_image(self):
        selected_images = self.get_selected_images()
        image_path = selected_images[0].path
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(image_path)))

    @Slot()
    def update_context_menu_actions(self):
        selected_image_count = len(self.selectedIndexes())
        copy_file_names_action_name = (
            f'Copy File {pluralize("Name", selected_image_count)}')
        copy_paths_action_name = (f'Copy '
                                  f'{pluralize("Path", selected_image_count)}')
        move_images_action_name = (
            f'Move {pluralize("Image", selected_image_count)} to...')
        copy_images_action_name = (
            f'Copy {pluralize("Image", selected_image_count)} to...')
        delete_images_action_name = (
            f'Delete {pluralize("Image", selected_image_count)}')
        self.copy_file_names_action.setText(copy_file_names_action_name)
        self.copy_paths_action.setText(copy_paths_action_name)
        self.move_images_action.setText(move_images_action_name)
        self.copy_images_action.setText(copy_images_action_name)
        self.delete_images_action.setText(delete_images_action_name)
        self.open_image_action.setVisible(selected_image_count == 1)


class ImageList(QDockWidget):
    def __init__(self, proxy_image_list_model: ProxyImageListModel,
                 tag_separator: str, image_width: int):
        super().__init__()
        self.proxy_image_list_model = proxy_image_list_model
        # Each `QDockWidget` needs a unique object name for saving its state.
        self.setObjectName('image_list')
        self.setWindowTitle('Images')
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea
                             | Qt.DockWidgetArea.RightDockWidgetArea)

        self.filter_line_edit = FilterLineEdit()
        selection_mode_layout = QHBoxLayout()
        selection_mode_label = QLabel('Selection mode')
        self.selection_mode_combo_box = SettingsComboBox(
            key='image_list_selection_mode')
        self.selection_mode_combo_box.addItems(list(SelectionMode))
        selection_mode_layout.addWidget(selection_mode_label)
        selection_mode_layout.addWidget(self.selection_mode_combo_box,
                                        stretch=1)
        self.list_view = ImageListView(self, proxy_image_list_model,
                                       tag_separator, image_width)
        self.image_index_label = QLabel()
        # A container widget is required to use a layout with a `QDockWidget`.
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self.filter_line_edit)
        layout.addLayout(selection_mode_layout)
        layout.addWidget(self.list_view)
        layout.addWidget(self.image_index_label)
        self.setWidget(container)

        self.selection_mode_combo_box.currentTextChanged.connect(
            self.set_selection_mode)
        self.set_selection_mode(self.selection_mode_combo_box.currentText())

    def set_selection_mode(self, selection_mode: str):
        if selection_mode == SelectionMode.DEFAULT:
            self.list_view.setSelectionMode(
                QAbstractItemView.SelectionMode.ExtendedSelection)
        elif selection_mode == SelectionMode.TOGGLE:
            self.list_view.setSelectionMode(
                QAbstractItemView.SelectionMode.MultiSelection)

    @Slot()
    def update_image_index_label(self, proxy_image_index: QModelIndex):
        image_count = self.proxy_image_list_model.rowCount()
        unfiltered_image_count = (self.proxy_image_list_model.sourceModel()
                                  .rowCount())
        label_text = f'Image {proxy_image_index.row() + 1} / {image_count}'
        if image_count != unfiltered_image_count:
            label_text += f' ({unfiltered_image_count} total)'
        self.image_index_label.setText(label_text)

    @Slot()
    def go_to_previous_image(self):
        if self.list_view.selectionModel().currentIndex().row() == 0:
            return
        self.list_view.clearSelection()
        previous_image_index = self.proxy_image_list_model.index(
            self.list_view.selectionModel().currentIndex().row() - 1, 0)
        self.list_view.setCurrentIndex(previous_image_index)

    @Slot()
    def go_to_next_image(self):
        if (self.list_view.selectionModel().currentIndex().row()
                == self.proxy_image_list_model.rowCount() - 1):
            return
        self.list_view.clearSelection()
        next_image_index = self.proxy_image_list_model.index(
            self.list_view.selectionModel().currentIndex().row() + 1, 0)
        self.list_view.setCurrentIndex(next_image_index)

    @Slot()
    def jump_to_first_untagged_image(self):
        """
        Select the first image that has no tags, or the last image if all
        images are tagged.
        """
        proxy_image_index = None
        for proxy_image_index in range(self.proxy_image_list_model.rowCount()):
            image: Image = self.proxy_image_list_model.data(
                self.proxy_image_list_model.index(proxy_image_index, 0),
                Qt.ItemDataRole.UserRole)
            if not image.tags:
                break
        if proxy_image_index is None:
            return
        self.list_view.clearSelection()
        self.list_view.setCurrentIndex(
            self.proxy_image_list_model.index(proxy_image_index, 0))

    def get_selected_image_indices(self) -> list[QModelIndex]:
        return self.list_view.get_selected_image_indices()

