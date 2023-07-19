from PySide6.QtCore import QStringListModel, Qt
from PySide6.QtWidgets import (QDockWidget, QLineEdit, QListView, QVBoxLayout,
                               QWidget)


class ImageTagEditor(QDockWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName('image_tag_editor')
        self.setWindowTitle('Tags')
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self.input_box = QLineEdit(self)
        self.input_box.setStyleSheet('padding: 8px;')
        self.input_box.setPlaceholderText('Add tag')

        self.list_view = QListView(self)
        self.model = QStringListModel(self)
        self.list_view.setModel(self.model)
        self.list_view.setWordWrap(True)
        self.list_view.setSpacing(4)

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.addWidget(self.input_box)
        layout.addWidget(self.list_view)
        self.setWidget(container)

    def set_tags(self, tags: list[str]):
        self.model.setStringList(tags)
