from PySide6.QtCore import QStringListModel, Qt
from PySide6.QtWidgets import QDockWidget, QListView


class ImageTagEditor(QDockWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName('image_tag_editor')
        self.setWindowTitle('Tags')
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.list_view = QListView(self)
        self.model = QStringListModel(self)
        self.list_view.setModel(self.model)
        self.list_view.setWordWrap(True)
        self.list_view.setSpacing(4)
        self.setWidget(self.list_view)

    def set_tags(self, tags: list[str]):
        self.model.setStringList(tags)
