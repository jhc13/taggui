import json
import os
from pathlib import Path

from PySide6.QtCore import (QAbstractListModel, Qt)
from PySide6.QtWidgets import (QDockWidget, QListView, QVBoxLayout, QWidget)

class HistoryListModel(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self.history_list = []

    def data(self, index, role):
        item = self.history_list[index.row()]
        if role == Qt.UserRole:
            return item
        if role == Qt.DisplayRole:
            ret = f"{item['date']}: {item['settings']['prompt']}"
            return ret

    def rowCount(self, parent=None) -> int:
        return len(self.history_list)

    def load_directory(self, directory_path: Path):
        self.history_list = []
        history_path = directory_path / "!0_history.jsonl"
        if history_path.exists():
            with open(history_path) as file:
                for line in file:
                    item = json.loads(line)
                    self.history_list.append(item)

class HistoryList(QDockWidget):
    def __init__(self, model: HistoryListModel):
        super().__init__()
        self.setObjectName('history_list')
        self.setWindowTitle('History')
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea
                             | Qt.DockWidgetArea.RightDockWidgetArea)

        container = QWidget()

        self.listView = QListView()
        self.listView.setModel(model)
        selection_model = self.listView.selectionModel()
        selection_model.currentChanged.connect(self.item_clicked)

        layout = QVBoxLayout(container)
        layout.addWidget(self.listView)

        self.setWidget(container)

    def item_clicked(self, current):
        if current.isValid():
            index = self.listView.currentIndex()
            data = self.listView.model().data(index, Qt.UserRole)
            print(json.dumps(data))
