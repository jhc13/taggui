import random

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image as PilImage, ImageColor, ImageOps
from PIL.Image import Resampling
import cv2 as opencv
import numpy as np

from PySide6.QtGui import QIcon


@dataclass
class Image:
    path: Path
    dimensions: tuple[int, int] | None
    tags: list[str] = field(default_factory=list)
    thumbnail: QIcon | None = None

# https://pillow.readthedocs.io/en/stable/handbook/concepts.html#filters
def prepare_img_stretch_and_squish(pil_image: PilImage, target_size: int, resample=Resampling.LANCZOS) -> PilImage:
    """Preprocesses an image for the model by simply stretching and squishing it to the target size. Does not retain shapes (see https://github.com/THUDM/CogVLM2/discussions/83)"""
    ret = pil_image.resize((target_size, target_size), resample=resample)
    return ret

def prepare_img_scale_and_centercrop(pil_image: PilImage, target_size: int, resample=Resampling.LANCZOS) -> PilImage:
    """Preprocesses an image for the model by scaling the short side to target size and then center cropping a square. May crop important content especially in very rectangular images (this method was used in Stable Diffusion 1 see https://arxiv.org/abs/2112.10752)"""
    width, height = pil_image.size
    if width < height:
        new_width = target_size
        new_height = int(target_size * height / width)
    else:
        new_height = target_size
        new_width = int(target_size * width / height)

    # Resize the image with the calculated dimensions
    ret = pil_image.resize((new_width, new_height), resample=resample)

    # Center crop a square from the resized image (make sure that there are no off-by-one errors)
    left = (new_width - target_size) / 2
    top = (new_height - target_size) / 2
    right = left + target_size
    bottom = top + target_size
    ret = ret.crop((left, top, right, bottom))
    return ret

def prepare_img_scale_and_fill(pil_image: PilImage, target_size: int, resample=Resampling.LANCZOS, method: str = "black") -> PilImage:
    """
    Preprocesses an image for the model by scaling the long side to target size and filling borders of the short side with content according to method (color, noise, replicate, reflect) until it is square. Introduces new content that wasn't there before which might be caught up by the model ("This image showcases a portrait of a person. On the left and right side are black borders.")
    - method: can be on of "noise", "replicate", "reflect" or a color value ("gray", "#000000", "rgb(100%,100%,100%)" etc.) which can be interpreted by Pillow (see https://pillow.readthedocs.io/en/stable/reference/ImageColor.html and https://developer.mozilla.org/en-US/docs/Web/CSS/named-color)
    """
    color = None
    try:
        color = ImageColor.getrgb(method)
        method = "color"
    except ValueError:
        pass

    width, height = pil_image.size
    if width > height:
        new_width = target_size
        new_height = int((new_width / width) * height)
    else:
        new_height = target_size
        new_width = int((new_height / height) * width)

    pastee = pil_image.resize((new_width, new_height), resample=resample)

    if method == "color": # fill borders with color
        canvas = PilImage.new("RGB", (target_size, target_size), color)
        offset = ((target_size - new_width) // 2, (target_size - new_height) // 2)
        canvas.paste(pastee, offset)
        ret = canvas
    elif method == "noise": # fill borders with RGB noise
        canvas = PilImage.new("RGB", (target_size, target_size))
        for x in range(target_size):
            for y in range(target_size):
                canvas.putpixel((x, y), (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)))
        canvas.paste(pastee, ((target_size - new_width) // 2, (target_size - new_height) // 2))
        ret = canvas
    elif method in ("replicate", "reflect"): # fill borders with color value of the edge
        left_padding = int((target_size - new_width) / 2)
        top_padding = int((target_size - new_height) / 2)
        right_padding = target_size - new_width - left_padding
        bottom_padding = target_size - new_height - top_padding
        opencv_pastee = np.array(pastee)
        borderType = { "replicate": opencv.BORDER_REPLICATE, "reflect": opencv.BORDER_REFLECT }[method]
        opencv_ret = opencv.copyMakeBorder(opencv_pastee, top_padding, bottom_padding, left_padding, right_padding, borderType=borderType)
        ret = PilImage.fromarray(opencv_ret)
    else:
        raise ValueError(f"Invalid method='{method}'")

    return ret
