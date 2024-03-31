from enum import Enum, auto


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


class CaptionModelType(Enum):
    COGAGENT = auto()
    COGVLM = auto()
    KOSMOS = auto()
    LLAVA_1_5 = auto()
    LLAVA_NEXT_34B = auto()
    LLAVA_NEXT_MISTRAL = auto()
    LLAVA_NEXT_VICUNA = auto()
    MOONDREAM = auto()
    WD_TAGGER = auto()
    XCOMPOSER2 = auto()
    OTHER = auto()
