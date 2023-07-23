from collections import Counter

from PySide6.QtCore import QAbstractListModel, Qt, Slot

from image import Image


class TagCounterModel(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self.tag_counter = Counter()
        self.most_common_tags = []

    def rowCount(self, parent=None):
        return len(self.most_common_tags)

    def data(self, index, role=None):
        tag, count = self.most_common_tags[index.row()]
        if role == Qt.DisplayRole:
            return f'{tag} ({count})'
        if role == Qt.EditRole:
            return tag

    @Slot()
    def count_tags(self, images: list[Image]):
        self.tag_counter.clear()
        for image in images:
            self.tag_counter.update(image.tags)
        self.most_common_tags = self.tag_counter.most_common()
        self.modelReset.emit()
