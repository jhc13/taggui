from PySide6.QtCore import QMimeData, QModelIndex, QStringListModel, Qt


class ImageTagListModel(QStringListModel):
    def dropMimeData(self, data: QMimeData, action: Qt.DropAction, row: int,
                     column: int, parent: QModelIndex) -> bool:
        # Overriding this method like this somehow disables dropping a tag onto
        # another tag, preventing tags from being overwritten.
        return False
