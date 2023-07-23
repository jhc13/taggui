from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QListView, QVBoxLayout, QWidget

from tag_counter_model import TagCounterModel


class AllTagsList(QListView):
    def __init__(self, tag_counter_model: TagCounterModel):
        super().__init__()
        self.setModel(tag_counter_model)
        self.setSpacing(4)
        self.setWordWrap(True)


class AllTagsEditor(QDockWidget):
    def __init__(self, tag_counter_model: TagCounterModel):
        super().__init__()
        # Each `QDockWidget` needs a unique object name for saving its state.
        self.setObjectName('all_tags_editor')
        self.setWindowTitle('All Tags')
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.all_tags_list = AllTagsList(tag_counter_model)
        # A container widget is required to use a layout with a `QDockWidget`.
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self.all_tags_list)
        self.setWidget(container)
