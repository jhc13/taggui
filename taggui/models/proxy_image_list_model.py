import operator

from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Qt
from transformers import PreTrainedTokenizerBase

from models.image_list_model import ImageListModel
from utils.image import Image


class ProxyImageListModel(QSortFilterProxyModel):
    def __init__(self, image_list_model: ImageListModel,
                 tokenizer: PreTrainedTokenizerBase, separator: str):
        super().__init__()
        self.setSourceModel(image_list_model)
        self.tokenizer = tokenizer
        self.separator = separator
        self.filter: list | None = None

    def does_image_match_filter(self, image: Image,
                                filter_: list | str) -> bool:
        if isinstance(filter_, str):
            return (filter_ in self.separator.join(image.tags) or
                    filter_ in str(image.path))
        if len(filter_) == 1:
            return self.does_image_match_filter(image, filter_[0])
        if len(filter_) == 2:
            if filter_[0] == 'NOT':
                return not self.does_image_match_filter(image, filter_[1])
            if filter_[0] == 'tag':
                return filter_[1] in image.tags
            if filter_[0] == 'caption':
                return filter_[1] in self.separator.join(image.tags)
            if filter_[0] == 'name':
                return filter_[1] in image.path.name
            if filter_[0] == 'path':
                return filter_[1] in str(image.path)
        if filter_[1] == 'AND':
            return (self.does_image_match_filter(image, filter_[0])
                    and self.does_image_match_filter(image, filter_[2:]))
        if filter_[1] == 'OR':
            return (self.does_image_match_filter(image, filter_[0])
                    or self.does_image_match_filter(image, filter_[2:]))
        comparison_operators = {
            '=': operator.eq,
            '==': operator.eq,
            '!=': operator.ne,
            '<': operator.lt,
            '>': operator.gt,
            '<=': operator.le,
            '>=': operator.ge
        }
        comparison_operator = comparison_operators[filter_[1]]
        number_to_compare = None
        if filter_[0] == 'tags':
            number_to_compare = len(image.tags)
        elif filter_[0] == 'chars':
            caption = self.separator.join(image.tags)
            number_to_compare = len(caption)
        elif filter_[0] == 'tokens':
            caption = self.separator.join(image.tags)
            # Subtract 2 for the `<|startoftext|>` and `<|endoftext|>` tokens.
            number_to_compare = len(self.tokenizer(caption).input_ids) - 2
        return comparison_operator(number_to_compare, int(filter_[2]))

    def filterAcceptsRow(self, source_row: int,
                         source_parent: QModelIndex) -> bool:
        # Show all images if there is no filter.
        if self.filter is None:
            return True
        image_index = self.sourceModel().index(source_row, 0)
        image: Image = self.sourceModel().data(image_index, Qt.UserRole)
        return self.does_image_match_filter(image, self.filter)
