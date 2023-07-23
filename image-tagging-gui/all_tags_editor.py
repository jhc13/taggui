from PySide6.QtCore import QSortFilterProxyModel, Qt, Slot
from PySide6.QtWidgets import (QDockWidget, QLabel, QLineEdit, QListView,
                               QPushButton, QVBoxLayout, QWidget)

from tag_counter_model import TagCounterModel


class ProxyTagCounterModel(QSortFilterProxyModel):
    def __init__(self, tag_counter_model: TagCounterModel):
        super().__init__()
        self.setSourceModel(tag_counter_model)


class FilterLineEdit(QLineEdit):
    def __init__(self):
        super().__init__()
        self.setPlaceholderText('Search tags')
        self.setStyleSheet('padding: 8px;')


class AllTagsList(QListView):
    def __init__(self, proxy_tag_counter_model: ProxyTagCounterModel):
        super().__init__()
        self.setModel(proxy_tag_counter_model)
        self.setSpacing(4)
        self.setWordWrap(True)


class AllTagsEditor(QDockWidget):
    def __init__(self, tag_counter_model: TagCounterModel):
        super().__init__()
        self.tag_counter_model = tag_counter_model

        # Each `QDockWidget` needs a unique object name for saving its state.
        self.setObjectName('all_tags_editor')
        self.setWindowTitle('All Tags')
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.proxy_tag_counter_model = ProxyTagCounterModel(
            self.tag_counter_model)
        self.proxy_tag_counter_model.setFilterRole(Qt.EditRole)
        filter_line_edit = FilterLineEdit()
        self.clear_filter_button = QPushButton('Clear Filter')
        self.all_tags_list = AllTagsList(self.proxy_tag_counter_model)
        self.tag_count_label = QLabel()
        # A container widget is required to use a layout with a `QDockWidget`.
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(filter_line_edit)
        layout.addWidget(self.clear_filter_button)
        layout.addWidget(self.all_tags_list)
        layout.addWidget(self.tag_count_label)
        self.setWidget(container)

        filter_line_edit.textChanged.connect(
            self.proxy_tag_counter_model.setFilterFixedString)
        self.proxy_tag_counter_model.modelReset.connect(
            self.update_tag_count_label)
        self.proxy_tag_counter_model.rowsInserted.connect(
            self.update_tag_count_label)
        self.proxy_tag_counter_model.rowsRemoved.connect(
            self.update_tag_count_label)

    @Slot()
    def update_tag_count_label(self):
        total_tag_count = self.tag_counter_model.rowCount()
        filtered_tag_count = self.proxy_tag_counter_model.rowCount()
        self.tag_count_label.setText(f'{filtered_tag_count} / '
                                     f'{total_tag_count} tags')
