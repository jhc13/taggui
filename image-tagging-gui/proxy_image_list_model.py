from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Qt

from image import Image
from image_list_model import ImageListModel


class ProxyImageListModel(QSortFilterProxyModel):
    def __init__(self, image_list_model: ImageListModel):
        super().__init__()
        self.setSourceModel(image_list_model)

    def filterAcceptsRow(self, source_row: int,
                         source_parent: QModelIndex) -> bool:
        """Only show images that have the filter tag."""
        # The filter tag is just a tag and not a regular expression, but it has
        # to be stored as one to be able to be retrieved here.
        filter_tag = self.filterRegularExpression().pattern()
        # If the filter tag is an empty string, all images should be shown.
        if not filter_tag:
            return True
        index = self.sourceModel().index(source_row, 0)
        image: Image = self.sourceModel().data(index, Qt.UserRole)
        return filter_tag in image.tags
