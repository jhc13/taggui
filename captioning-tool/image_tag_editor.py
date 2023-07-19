from PySide6.QtCore import QPersistentModelIndex, QStringListModel, Qt, Slot
from PySide6.QtWidgets import (QAbstractItemView, QDockWidget, QLineEdit,
                               QListView, QVBoxLayout,
                               QWidget)


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
        else:
            super().keyPressEvent(event)


class ImageTagEditor(QDockWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName('image_tag_editor')
        self.setWindowTitle('Tags')
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self.input_box = QLineEdit(self)
        self.input_box.setStyleSheet('padding: 8px;')
        self.input_box.setPlaceholderText('Add tag')
        self.input_box.returnPressed.connect(self.add_tag)

        self.model = QStringListModel(self)
        self.image_tag_list = ImageTagList(self.model, self)

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.addWidget(self.input_box)
        layout.addWidget(self.image_tag_list)
        self.setWidget(container)

    def set_tags(self, tags: list[str]):
        self.model.setStringList(tags)

    @Slot()
    def add_tag(self):
        tag = self.input_box.text()
        if not tag:
            return
        self.model.insertRow(self.model.rowCount())
        self.model.setData(self.model.index(self.model.rowCount() - 1), tag)
        self.input_box.clear()
