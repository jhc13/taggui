from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtGui import QIcon


@dataclass
class Image:
    path: Path
    dimensions: tuple[int, int] | None
    tags: list[str] = field(default_factory=list)
    target_dimensions: tuple[int, int] | None = None
    # store for each crop (x, y, width, height) the target dimension (width, heiht)
    crops: dict[tuple[int, int, int, int], tuple[int, int]] | None = None
    thumbnail: QIcon | None = None
