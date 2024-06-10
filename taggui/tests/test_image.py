import os

from PIL import Image
from PIL.Image import Resampling

from utils.image import select_preprocess_img_by_str

def test_prepares():
    target_size = 1344
    resampling = Resampling.LANCZOS
    out_dir = "outputs/"

    os.makedirs(out_dir, exist_ok=True)

    for path in ["images/people_landscape.webp", "images/people_portrait.webp"]:
        basename, ext = os.path.splitext(os.path.basename(path))
        img = Image.open(path)
        for method in ["stretch-and-squish", "scale-and-centercrop", "white", "gray", "black", "noise", "replicate", "reflect", "unknown"]:
            ret = select_preprocess_img_by_str(img, target_size, resampling, method)
            ret.save(f"{out_dir}/{basename}_{method}.webp", format='WebP', lossless=True, quality=0)
