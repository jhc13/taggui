from enum import Enum, auto


# `StrEnum` is a Python 3.11 feature that can be used here.
class CaptionPosition(str, Enum):
    BEFORE_FIRST_TAG = 'Insert before first tag'
    AFTER_LAST_TAG = 'Insert after last tag'
    OVERWRITE_FIRST_TAG = 'Overwrite first tag'
    OVERWRITE_ALL_TAGS = 'Overwrite all tags'
    DO_NOT_ADD = 'Do not add to tags'


class Device(str, Enum):
    GPU = 'GPU if available'
    CPU = 'CPU'


class ModelType(Enum):
    LLAVA = auto()
    KOSMOS = auto()
    COGVLM = auto()
    COGAGENT = auto()
    XCOMPOSER2 = auto()
    MOONDREAM = auto()
    OTHER = auto()
