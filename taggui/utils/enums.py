from enum import Enum


# `StrEnum` is a Python 3.11 feature that can be used here.
class AllTagsSortBy(str, Enum):
    FREQUENCY = 'Frequency'
    FREQUENCY_FILTERED = 'Frequency (filtered)'
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


class ExportFilter(str, Enum):
    NONE = 'All images'
    FILTERED = 'Filtered images'
    SELECTED = 'Selected images'


Presets = {
    'manual': (0, 0, 1, '1:1, 2:1, 3:2, 4:3, 16:9, 21:9'),
    'Direct feed through': (0, 1, 1, '1:1, 2:1, 3:2, 4:3, 16:9, 21:9'),
    'SD1': (512, 64, 8, '512:512, 640:320, 576:384, 512:384, 640:384, 768:320'),
    'SDXL, SD3, Flux': (1024, 64, 8, '1024:1024, 1408:704, 1216:832, 1152:896, 1344:768, 1536:640')
}

class MaskingStrategy(str, Enum):
    IGNORE = 'ignore'
    REPLACE = 'replace'
    REMOVE = 'remove'
    MASK_FILE = 'create mask files'


class MaskedContent(str, Enum):
    ORIGINAL = 'original'
    BLUR = 'blur'
    BLUR_NOISE = 'blur + noise'
    GREY = 'grey'
    GREY_NOISE = 'grey + noise'
    BLACK = 'black'
    WHITE = 'white'


class ExportFormat(str, Enum):
    JPG = '.jpg - JPEG'
    JPGXL = '.jxl - JPEG XL'
    PNG = '.png - PNG'
    WEBP = '.webp - WEBP'


ExportFormatDict = {
    ExportFormat.JPG: 'jpeg',
    ExportFormat.JPGXL: 'jxl',
    ExportFormat.PNG: 'png',
    ExportFormat.WEBP: 'webp'
}


class IccProfileList(str, Enum):
    SRgb = 'sRGB'
    SRgbLinear = 'sRGB (linear gamma)'
    AdobeRgb = 'AdobeRGB'
    DisplayP3 = 'DisplayP3'
    ProPhotoRgb = 'ProPhotoRGB'
    Bt2020 = 'BT.2020'
    Bt2100Pq = 'BT.2100(PQ)'
    Bt2100Hlg = 'BT.2100 (HLG)'


class BucketStrategy(str, Enum):
    CROP = 'crop'
    SCALE = 'scale'
    CROP_SCALE = 'crop and scale'


class CaptionStrategy(str, Enum):
    TAG_LIST = 'tag list (using tag separator)'
    FIRST = 'only first tag'
    LAST = 'only last tag'
    ENUMERATION = 'enumeration ("t1, t2, t3, and t4")'
    PREFIX_ENUMERATION = 'prefixed enumeration ("t1 t2, t3, and t4")'


class HashNewlineHandling(str, Enum):
    IGNORE = 'No special handling'
    MULTILINE = 'Create additional line'
    MULTIFILE = 'Create additional file'
