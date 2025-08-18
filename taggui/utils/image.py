from enum import Enum
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QRect, QSize
from PySide6.QtGui import QIcon


class ImageMarking(str, Enum):
    CROP = 'crop'
    HINT = 'hint'
    INCLUDE = 'include in mask'
    EXCLUDE = 'exclude from mask'
    NONE = 'no marking'


@dataclass
class Marking:
    label: str
    type: ImageMarking
    rect: QRect
    confidence: float = 1.0


@dataclass
class Image:
    path: Path
    dimensions: tuple[int, int] | None
    tags: list[str] = field(default_factory=list)
    target_dimension: QSize | None = None
    crop: QRect | None = None
    markings: list[Marking] = field(default_factory=list)
    rating: float = 0.0
    thumbnail: QIcon | None = None
