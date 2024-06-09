from dataclasses import dataclass, field
from pathlib import Path
from PIL import Image as PilImage, ImageColor
from PIL.Image import Resampling

from PySide6.QtGui import QIcon


@dataclass
class Image:
    path: Path
    dimensions: tuple[int, int] | None
    tags: list[str] = field(default_factory=list)
    thumbnail: QIcon | None = None

# https://pillow.readthedocs.io/en/stable/handbook/concepts.html#filters
def prepare_img_stretch_and_squish(img: PilImage, target_size: int, resampling=Resampling.LANCZOS) -> PilImage
    """Preprocesses an image for the model by simply stretching and squishing it to the target size. Does not retain shapes (see https://github.com/THUDM/CogVLM2/discussions/83)"""
    return img

def prepare_img_scale_and_centercrop(img: PilImage, target_size: int, resampling=Resampling.LANCZOS) -> PilImage:
    """Preprocesses an image for the model by scaling the short side to target size and then center cropping a square. May crop important content especially in very rectangular images (this method was used in Stable Diffusion 1 see https://arxiv.org/abs/2112.10752)"""
    return img

def prepare_img_scale_and_fill(img: PilImage, target_size: int, resampling=Resampling.LANCZOS, method: str = "black") -> PilImage:
    """
    Preprocesses an image for the model by scaling the long side to target size and filling borders of the short side with content according to method (color, repeat, noise) until it is square. Introduces new content that wasn't there before which might be caught up by the model ("This image showcases a portrait of a person. On the left and right side are black borders.")
    - method: can be on of "noise", "repeat" or a color value ("gray", "#000000", "rgb(100%,100%,100%)" etc.) which can be interpreted by Pillow (see https://pillow.readthedocs.io/en/stable/reference/ImageColor.html and https://developer.mozilla.org/en-US/docs/Web/CSS/named-color)
    """
    color = None
    try:
        color = ImageColor.getrgb(method)
        method = "color"
    except ValueError:
        pass

    match method:
        case "color": pass # fill borders with color
        case "noise": pass # fill borders with RGB noise
        case "repeat": pass # fill borders with color value of the edge
        case _:

    return img
