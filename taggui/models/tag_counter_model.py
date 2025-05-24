from collections import Counter

from PySide6.QtCore import QAbstractListModel, Qt, Signal, Slot
from PySide6.QtWidgets import QMessageBox

from utils.image import Image
from utils.utils import get_confirmation_dialog_reply, list_with_and, pluralize


class TagCounterModel(QAbstractListModel):
    tags_renaming_requested = Signal(list, str)

    def __init__(self):
        super().__init__()
        self.tag_counter = Counter()
        self.most_common_tags = []
        self.most_common_tags_filtered = None
        self.all_tags_list = None

    def rowCount(self, parent=None) -> int:
        return len(self.most_common_tags)

    def data(self, index, role=None) -> tuple[str, int] | str:
        tag, count = self.most_common_tags[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return tag, count
        if role == Qt.ItemDataRole.DisplayRole:
            if self.most_common_tags_filtered is None:
                return f'{tag} ({count})'
            else:
                return f'{tag} ({self.most_common_tags_filtered[tag]}/{count})'
        if role == Qt.ItemDataRole.EditRole:
            return tag

    def flags(self, index) -> Qt.ItemFlag:
        """Make the tags editable."""
        return (Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
                | Qt.ItemFlag.ItemIsEnabled)

    def setData(self, index, value: str,
                role=Qt.ItemDataRole.EditRole) -> bool:
        new_tag = value
        if not new_tag or role != Qt.ItemDataRole.EditRole:
            return False
        old_tag = self.data(index, Qt.ItemDataRole.EditRole)
        if new_tag == old_tag:
            return False
        selected_indices = self.all_tags_list.selectedIndexes()
        old_tags = []
        old_tags_count = 0
        for selected_index in selected_indices:
            old_tag, old_tag_count = selected_index.data(
                Qt.ItemDataRole.UserRole)
            old_tags.append(old_tag)
            old_tags_count += old_tag_count
        question = (f'Rename {old_tags_count} '
                    f'{pluralize("instance", old_tags_count)} of ')
        if len(old_tags) < 10:
            quoted_tags = [f'"{tag}"' for tag in old_tags]
            question += (f'{pluralize("tag", len(old_tags))} '
                         f'{list_with_and(quoted_tags)} ')
        else:
            question += f'{len(old_tags)} tags '
        question += f'to "{new_tag}"?'
        reply = get_confirmation_dialog_reply(
            title=f'Rename {pluralize("Tag", len(old_tags))}',
            question=question)
        if reply == QMessageBox.StandardButton.Yes:
            self.tags_renaming_requested.emit(old_tags, new_tag)
            return True
        return False

    @Slot()
    def count_tags(self, images: list[Image]):
        self.tag_counter.clear()
        self.most_common_tags_filtered = None
        for image in images:
            self.tag_counter.update(image.tags)
        self.most_common_tags = self.tag_counter.most_common()
        self.modelReset.emit()

    @Slot()
    def count_tags_filtered(self, images: list[Image] | None):
        if images is None:
            self.most_common_tags_filtered = None
        else:
            self.most_common_tags_filtered = Counter()
            for image in images:
                self.most_common_tags_filtered.update(image.tags)
        self.modelReset.emit()
