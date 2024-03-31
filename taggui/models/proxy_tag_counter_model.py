from fnmatch import fnmatchcase

from PySide6.QtCore import QModelIndex, QSortFilterProxyModel

from models.tag_counter_model import TagCounterModel
from utils.enums import AllTagsSortBy


class ProxyTagCounterModel(QSortFilterProxyModel):
    def __init__(self, tag_counter_model: TagCounterModel):
        super().__init__()
        self.setSourceModel(tag_counter_model)
        self.tag_counter_model = tag_counter_model
        self.sort_by = None
        self.filter = None

    # Setting a sort role results in lots of calls to `data()` and is very
    # slow, so implement a custom `lessThan()` method instead.
    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        left_tag, left_count = self.tag_counter_model.most_common_tags[
            left.row()]
        right_tag, right_count = self.tag_counter_model.most_common_tags[
            right.row()]
        if self.sort_by == AllTagsSortBy.FREQUENCY:
            return left_count < right_count
        elif self.sort_by == AllTagsSortBy.NAME:
            return left_tag < right_tag
        elif self.sort_by == AllTagsSortBy.LENGTH:
            return len(left_tag) < len(right_tag)

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex):
        if self.filter is None:
            return True
        tag, _ = self.tag_counter_model.most_common_tags[source_row]
        return fnmatchcase(tag, f'*{self.filter}*')
