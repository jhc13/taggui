from collections import Counter

from PySide6.QtCore import QAbstractListModel, Qt, Signal, Slot
from PySide6.QtWidgets import QMessageBox

from utils.image import Image
from utils.utils import get_confirmation_dialog_reply, pluralize


class TagCounterModel(QAbstractListModel):
    tag_renaming_requested = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.tag_counter = Counter()
        self.most_common_tags = []

    def rowCount(self, parent=None) -> int:
        return len(self.most_common_tags)

    def data(self, index, role=None) -> tuple[str, int] | str:
        tag, count = self.most_common_tags[index.row()]
        if role == Qt.UserRole:
            return tag, count
        if role == Qt.DisplayRole:
            return f'{tag} ({count})'
        if role == Qt.EditRole:
            return tag

    def flags(self, index) -> Qt.ItemFlags:
        """Make the tags editable."""
        return Qt.ItemIsSelectable | Qt.ItemIsEditable | Qt.ItemIsEnabled

    def setData(self, index, value: str, role=Qt.EditRole) -> bool:
        if not value or role != Qt.EditRole:
            return False
        tag, count = self.data(index, Qt.UserRole)
        question = (f'Rename {count} {pluralize("instance", count)} of tag '
                    f'"{tag}" to "{value}"?')
        reply = get_confirmation_dialog_reply(title='Rename Tag',
                                              question=question)
        if reply == QMessageBox.StandardButton.Yes:
            self.tag_renaming_requested.emit(tag, value)
            return True
        return False

    @Slot()
    def count_tags(self, images: list[Image]):
        self.tag_counter.clear()
        for image in images:
            self.tag_counter.update(image.tags)
        self.most_common_tags = self.tag_counter.most_common()
        self.modelReset.emit()
