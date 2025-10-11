from enum import Enum


# `StrEnum` is a Python 3.11 feature that can be used here.
class AllTagsSortBy(str, Enum):
    FREQUENCY = 'Frequency'
    NAME = 'Name'
    LENGTH = 'Length'


class SortOrder(str, Enum):
    ASCENDING = 'Ascending'
    DESCENDING = 'Descending'


class CaptionPosition(str, Enum):
    BEFORE_FIRST_TAG = 'Insert before first tag'
    AFTER_LAST_TAG = 'Insert after last tag'
    OVERWRITE_FIRST_TAG = 'Overwrite first tag'
    OVERWRITE_ALL_TAGS = 'Overwrite all tags'
    DO_NOT_ADD = 'Do not add to tags'


class CaptionDevice(str, Enum):
    GPU = 'GPU if available'
    CPU = 'CPU'


class GeneratedTagOrder(str, Enum):
    PROBABILITY = 'Highest Probability'
    ALPHABETICAL = 'Alphabetical'
    MODEL_DEFAULT = 'Unsorted (Model Default)'
