import os

from PIL import Image
from PIL.Image import Resampling

from utils.image import prepare_img_scale_and_centercrop, prepare_img_scale_and_fill, prepare_img_stretch_and_squish

def test_prepares():
    target_size = 1344
    resampling = Resampling.LANCZOS
    out_dir = "outputs/"

    os.makedirs(out_dir, exist_ok=True)

    for path in ["images/people_landscape.webp", "images/people_portrait.webp"]:
        basename, ext = os.path.splitext(os.path.basename(path))
        img = Image.open(path)
        for name, func in [("stretch_and_squish", prepare_img_stretch_and_squish), ("scale_and_centercrop", prepare_img_scale_and_centercrop), ("scale_and_fill", prepare_img_scale_and_fill)]:
            if name == "scale_and_fill":
                for method in ["white", "gray", "black", "noise", "replicate", "reflect"]:
                    ret = func(img, target_size, resampling, method)
                    ret.save(f"{out_dir}/{basename}_{method}.webp", format='WebP', lossless=True, quality=0)
            else:
                ret = func(img, target_size, resampling)
                ret.save(f"{out_dir}/{basename}_{name}.webp", format='WebP', lossless=True, quality=0)
