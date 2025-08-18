import operator
import re
from fnmatch import fnmatchcase

from PySide6.QtCore import (QModelIndex, QSortFilterProxyModel, Qt, QRect,
                            QSize, Signal)
from transformers import PreTrainedTokenizerBase

from models.image_list_model import ImageListModel
from utils.image import Image
import utils.target_dimension as target_dimension

comparison_operators = {
    '=': operator.eq,
    '==': operator.eq,
    '!=': operator.ne,
    '<': operator.lt,
    '>': operator.gt,
    '<=': operator.le,
    '>=': operator.ge
}


class ProxyImageListModel(QSortFilterProxyModel):
    filter_changed = Signal()

    def __init__(self, image_list_model: ImageListModel,
                 tokenizer: PreTrainedTokenizerBase, tag_separator: str):
        super().__init__()
        self.setSourceModel(image_list_model)
        self.tokenizer = tokenizer
        self.tag_separator = tag_separator
        self.filter: list | None = None

    def set_filter(self, new_filter: list | None):
        self.filter = new_filter
        self.invalidateFilter()
        self.filter_changed.emit()

    def does_image_match_filter(self, image: Image,
                                filter_: list | str | None) -> bool:
        if filter_ is None:
            return True
        if isinstance(filter_, str):
            return (fnmatchcase(self.tag_separator.join(image.tags),
                                f'*{filter_}*')
                    or fnmatchcase(str(image.path), f'*{filter_}*'))
        if len(filter_) == 1:
            return self.does_image_match_filter(image, filter_[0])
        if len(filter_) == 2:
            if filter_[0] == 'NOT':
                return not self.does_image_match_filter(image, filter_[1])
            if filter_[0] == 'tag':
                return any(fnmatchcase(tag, filter_[1]) for tag in image.tags)
            if filter_[0] == 'caption':
                caption = self.tag_separator.join(image.tags)
                return fnmatchcase(caption, f'*{filter_[1]}*')
            if filter_[0] == 'marking':
                last_colon_index = filter_[1].rfind(':')
                if last_colon_index < 0:
                    return any(fnmatchcase(marking.label, filter_[1])
                               for marking in image.markings)
                else:
                    label = filter_[1][:last_colon_index]
                    confidence = filter_[1][last_colon_index + 1:]
                    pattern =r'^(<=|>=|==|<|>|=)\s*(0?[.,][0-9]+)'
                    match = re.match(pattern, confidence)
                    if not match or len(match.group(2)) == 0:
                        return False
                    comparison_operator = comparison_operators[match.group(1)]
                    confidence_target = float(match.group(2).replace(',', '.'))
                    return any((fnmatchcase(marking.label, label) and
                               comparison_operator(marking.confidence,
                                                   confidence_target))
                               for marking in image.markings)
            if filter_[0] == 'crops':
                crop = image.crop if image.crop is not None else QRect(0, 0, *image.dimensions)
                return any(fnmatchcase(marking.label, filter_[1]) and
                           marking.rect.intersects(crop) and not crop.contains(marking.rect)
                           for marking in image.markings)
            if filter_[0] == 'visible':
                crop = image.crop if image.crop is not None else QRect(0, 0, *image.dimensions)
                return any(fnmatchcase(marking.label, filter_[1]) and
                           marking.rect.intersects(crop)
                           for marking in image.markings)
            if filter_[0] == 'name':
                return fnmatchcase(image.path.name, f'*{filter_[1]}*')
            if filter_[0] == 'path':
                return fnmatchcase(str(image.path), f'*{filter_[1]}*')
            if filter_[0] == 'size':
                # accept any dimension separator of [x:]
                dimension = (filter_[1]).replace(':', 'x').split('x')
                return (len(dimension) == 2
                        and dimension[0] == str(image.dimensions[0])
                        and dimension[1] == str(image.dimensions[1]))
            if filter_[0] == 'target':
                # accept any dimension separator of [x:]
                dimension = (filter_[1]).replace(':', 'x').split('x')
                if image.target_dimension is None:
                    image.target_dimension = target_dimension.get(QSize(*image.dimensions))
                return (len(dimension) == 2
                        and dimension[0] == str(image.target_dimension.width())
                        and dimension[1] == str(image.target_dimension.height()))
        if filter_[1] == 'AND':
            if len(filter_) < 3:
                return self.does_image_match_filter(image, filter_[0])
            return (self.does_image_match_filter(image, filter_[0])
                    and self.does_image_match_filter(image, filter_[2:]))
        if filter_[1] == 'OR':
            if len(filter_) < 3:
                return self.does_image_match_filter(image, filter_[0])
            return (self.does_image_match_filter(image, filter_[0])
                    or self.does_image_match_filter(image, filter_[2:]))
        comparison_operator = comparison_operators[filter_[1]]
        number_to_compare = None
        if filter_[0] == 'tags':
            number_to_compare = len(image.tags)
        elif filter_[0] == 'chars':
            caption = self.tag_separator.join(image.tags)
            number_to_compare = len(caption)
        elif filter_[0] == 'tokens':
            caption = self.tag_separator.join(image.tags)
            # Subtract 2 for the `<|startoftext|>` and `<|endoftext|>` tokens.
            number_to_compare = len(self.tokenizer(caption).input_ids) - 2
        elif filter_[0] == 'stars':
            number_to_compare = image.rating * 5.0
        elif filter_[0] == 'width':
            number_to_compare = image.dimensions[0]
        elif filter_[0] == 'height':
            number_to_compare = image.dimensions[1]
        elif filter_[0] == 'area':
            number_to_compare =  image.dimensions[0] * image.dimensions[1]
        return comparison_operator(number_to_compare, int(filter_[2]))

    def filterAcceptsRow(self, source_row: int,
                         source_parent: QModelIndex) -> bool:
        # Show all images when there is no filter.
        if self.filter is None:
            return True
        image_index = self.sourceModel().index(source_row, 0)
        image: Image = self.sourceModel().data(image_index,
                                               Qt.ItemDataRole.UserRole)
        return self.does_image_match_filter(image, self.filter)

    def is_image_in_filtered_images(self, image: Image) -> bool:
        return (self.filter is None
                or self.does_image_match_filter(image, self.filter))

    def get_list(self) -> list[Image]:
        return [self.data(self.index(row, 0, QModelIndex()), Qt.UserRole)
                for row in range(self.rowCount())]
