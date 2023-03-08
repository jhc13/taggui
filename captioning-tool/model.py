from dataclasses import dataclass, field
from pathlib import Path

import imagesize


@dataclass
class Image:
    path: Path
    dimensions: tuple[int, int] | None
    caption: str | None = None
    tags: list[str] = field(default_factory=list)


class Model:
    def __init__(self, separator: str, insert_space_after_separator: bool):
        self.separator = separator
        self.insert_space_after_separator = insert_space_after_separator
        self.directory_path = None
        self.images = None

    def get_tags_from_caption(self, caption: str) -> list[str]:
        separator = (self.separator + ' ' if self.insert_space_after_separator
                     else self.separator)
        tags = caption.split(separator)
        return tags

    def load_directory(self, directory_path: Path) -> list[Image]:
        self.images = []
        self.directory_path = directory_path
        file_paths = set(directory_path.glob('*'))
        text_file_paths = set(directory_path.glob('*.txt'))
        image_paths = file_paths - text_file_paths
        text_file_stems = {path.stem for path in text_file_paths}
        image_stems = {path.stem for path in image_paths}
        image_stems_with_captions = image_stems & text_file_stems
        for image_path in image_paths:
            try:
                dimensions = imagesize.get(image_path)
            except ValueError:
                dimensions = None
            if image_path.stem in image_stems_with_captions:
                text_file_path = directory_path / f'{image_path.stem}.txt'
                caption = text_file_path.read_text()
                tags = self.get_tags_from_caption(caption)
                image = Image(image_path, dimensions, caption, tags)
            else:
                image = Image(image_path, dimensions)
            self.images.append(image)
        self.images.sort(key=lambda image_: image_.path.name)
        return self.images
