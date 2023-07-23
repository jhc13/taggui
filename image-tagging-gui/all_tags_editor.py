from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtWidgets import (QDockWidget, QLineEdit, QListView, QVBoxLayout,
                               QWidget)

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
        # Each `QDockWidget` needs a unique object name for saving its state.
        self.setObjectName('all_tags_editor')
        self.setWindowTitle('All Tags')
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        proxy_tag_counter_model = ProxyTagCounterModel(tag_counter_model)
        proxy_tag_counter_model.setFilterRole(Qt.EditRole)
        filter_line_edit = FilterLineEdit()
        all_tags_list = AllTagsList(proxy_tag_counter_model)
        # A container widget is required to use a layout with a `QDockWidget`.
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(filter_line_edit)
        layout.addWidget(all_tags_list)
        self.setWidget(container)

        filter_line_edit.textChanged.connect(
            proxy_tag_counter_model.setFilterFixedString)
