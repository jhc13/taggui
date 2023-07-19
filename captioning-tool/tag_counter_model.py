from collections import Counter

from PySide6.QtCore import QAbstractListModel, Qt, Slot

from image import Image


class TagCounterModel(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self.tag_counter = Counter()
        self.most_common_tags = None

    def rowCount(self, parent=None):
        return len(self.tag_counter)

    def data(self, index, role=None):
        if role == Qt.DisplayRole:
            tag, count = self.most_common_tags[index.row()]
            return f'{tag} ({count})'
        elif role == Qt.EditRole:
            tag = self.most_common_tags[index.row()][0]
            return tag

    @Slot()
    def count_tags(self, images: list[Image]):
        self.tag_counter.clear()
        for image in images:
            self.tag_counter.update(image.tags)
        self.most_common_tags = self.tag_counter.most_common()
        self.dataChanged.emit(self.index(0, 0),
                              self.index(len(self.most_common_tags) - 1, 0))
