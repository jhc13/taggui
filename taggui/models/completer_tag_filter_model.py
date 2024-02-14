from PySide6.QtCore import QSortFilterProxyModel
from PySide6.QtCore import (QItemSelection, QKeyCombination, QModelIndex, QUrl,
                            Qt, Slot)

class CompleterTagFilterModel(QSortFilterProxyModel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filter_tags = set()

    def setFilterTags(self, tags):
        self.filter_tags = set(tags)
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        tag, count = model.data(model.index(source_row, 0), Qt.UserRole)
        return tag not in self.filter_tags