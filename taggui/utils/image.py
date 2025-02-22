from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtGui import QIcon


@dataclass
class Image:
    path: Path
    dimensions: tuple[int, int] | None
    tags: list[str] = field(default_factory=list)
    target_dimension: tuple[int, int] | None = None
    # (x, y, width, height)
    crop: tuple[int, int, int, int] | None = None
    hints: dict[str, tuple[int, int, int, int]] = field(default_factory=dict)
    includes: dict[str, tuple[int, int, int, int]] = field(default_factory=dict)
    excludes: dict[str, tuple[int, int, int, int]] = field(default_factory=dict)
    thumbnail: QIcon | None = None
