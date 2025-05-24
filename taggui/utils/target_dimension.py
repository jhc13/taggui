import sys
from math import floor, sqrt
import re

from PySide6.QtCore import QSize

from utils.settings import DEFAULT_SETTINGS, settings

# singleton data store
_preferred_sizes : list[QSize] = []
notable_aspect_ratios = [
    (1, 1, 1),
    (2, 1, 2/1),
    (3, 2, 3/2),
    (4, 3, 4/3),
    (16, 9, 16/9),
    (21, 9, 21/9),
]
aspect_ratios = notable_aspect_ratios.copy()

settings.change.connect(lambda: _preferred_sizes.clear())

def get_preferred_sizes():
    global _preferred_sizes
    if not _preferred_sizes:
        prepare()
    return _preferred_sizes


def prepare() -> list[tuple[int, int, float]] | None:
    """
    Prepare by parsing the user supplied preferred sizes.

    Return
    ------
        The same list of aspect ratios (when supplied) but extrended by the real
        aspect ratios of the preferred sizes.
    """
    global _preferred_sizes
    global aspect_ratios
    _preferred_sizes = []
    aspect_ratios = notable_aspect_ratios.copy()
    for res_str in re.split(r'\s*,\s*',
                            settings.value('export_preferred_sizes', type=str) or ''):
        try:
            if res_str == '':
                continue
            size_str = res_str.split(':')
            width = max(int(size_str[0]), int(size_str[1]))
            height = min(int(size_str[0]), int(size_str[1]))
            _preferred_sizes.append((width, height))
            if not width == height:
                _preferred_sizes.append((height, width))
            if aspect_ratios is not None:
                # add exact aspect ratio of the preferred size to label it
                # similar to the perfect one
                aspect_ratio = width / height
                for ar in aspect_ratios:
                    ar_delta = abs(ar[2] - aspect_ratio)
                    if ar_delta < 1e-4:
                        # already included
                        break
                    if ar_delta < 0.15:
                        aspect_ratios.append((ar[0], ar[1], aspect_ratio))
                        break
        except ValueError:
            # Handle cases where the resolution string is not in the correct format
            print(f'Warning: Invalid resolution format: {res_str}. Skipping.',
                    file=sys.stderr)
            continue # Skip to the next resolution if there's an error
    return aspect_ratios

def calculate_cropped_area(width: int, height: int, test_width: int, test_height: int) -> int:
    original_aspect_ratio = width / height
    target_aspect_ratio = test_width / test_height

    if original_aspect_ratio > target_aspect_ratio:
        # Crop horizontally
        cropped_area = height * (width - (height * test_width) / test_height)
    else:
        # Crop vertically
        cropped_area = width * (height - (width * test_height) / test_width)
    return int(cropped_area)

def get(dimensions: QSize) -> QSize:
    """
    Determine the dimensions of an image it should have when it is exported.

    Note: this gives the optimal answer and thus can be slower than the Kohya
    bucket algorithm.

    Parameters
    ----------
    dimensions: QSize
        The width and height of the image
    """
    global _preferred_sizes
    width, height = dimensions.toTuple()
    # The target resolution of the AI model. The target image pixels
    # will not exceed the square of this number
    resolution = settings.value('export_resolution', defaultValue=DEFAULT_SETTINGS['export_resolution'], type=int)
    # Is upscaling of images allowed?
    upscaling = settings.value('export_upscaling', defaultValue=DEFAULT_SETTINGS['export_upscaling'], type=bool)
    # The resolution of the buckets
    bucket_res = settings.value('export_bucket_res_size', defaultValue=DEFAULT_SETTINGS['export_bucket_res_size'], type=int)

    if not _preferred_sizes:
        prepare()

    if resolution == 0:
        # no rescale in this case, only cropping
        return QSize((width // bucket_res) * bucket_res,
                     (height // bucket_res) * bucket_res)

    if width < bucket_res or height < bucket_res:
        # It doesn't make sense to use such a small image.
        # But we shouldn't patronize the user.
        return dimensions

    preferred_sizes_bonus = 0.4 # reduce the loss by this factor

    max_pixels = resolution * resolution
    opt_width = floor(resolution * sqrt(width/height))
    opt_height = floor(resolution * sqrt(height/width))

    loss = 1e10
    for dx, dy in [(0,0), (0,1), (1,0), (1,1)]:
        opt_width += dx
        opt_height += dy

        if not upscaling:
            opt_width = min(width, opt_width)
            opt_height = min(height, opt_height)

        # test 1, guaranteed to find a solution: shrink and crop
        # 1.1: exact width
        test_width = max(opt_width // bucket_res, 1) * bucket_res
        test_height = max((height * test_width / width) // bucket_res, 1) * bucket_res
        test_loss = calculate_cropped_area(width, height, test_width, test_height)
        if (test_width, test_height) in _preferred_sizes:
            test_loss *= preferred_sizes_bonus
        if test_loss < loss or (test_loss == loss and
                                (candidate_width < test_width or candidate_height < test_height)):
            candidate_width = test_width
            candidate_height = test_height
            loss = test_loss
        # 1.2: exact height
        test_height = max(opt_height // bucket_res, 1) * bucket_res
        test_width = max((width * test_height / height) // bucket_res, 1) * bucket_res
        test_loss = calculate_cropped_area(width, height, test_width, test_height)
        if (test_height, test_width) in _preferred_sizes:
            test_loss *= preferred_sizes_bonus
        if test_loss < loss or (test_loss == loss and
                                (candidate_width < test_width or candidate_height < test_height)):
            candidate_width = test_width
            candidate_height = test_height
            loss = test_loss

        # test 2, going bigger might still fit in the size budget due to cropping
        # 2.1: exact width
        for delta in range(1, 10):
            test_width = max(opt_width // bucket_res + delta, 1) * bucket_res
            test_height = max((height * test_width / width) // bucket_res, 1) * bucket_res
            if test_width * test_height > max_pixels:
                break
            if (test_width > width or test_height > height) and not upscaling:
                break
            test_loss = calculate_cropped_area(width, height, test_width, test_height)
            if (test_height, test_width) in _preferred_sizes:
                test_loss *= preferred_sizes_bonus
                if test_loss < loss or (test_loss == loss and
                                        (candidate_width < test_width or candidate_height < test_height)):
                    candidate_width = test_width
                    candidate_height = test_height
                    loss = test_loss
        # 2.2: exact height
        for delta in range(1, 10):
            test_height = max(opt_height // bucket_res + delta, 1) * bucket_res
            test_width = max((width * test_height / height) // bucket_res, 1) * bucket_res
            if test_width * test_height > max_pixels:
                break
            if (test_width > width or test_height > height) and not upscaling:
                break
            test_loss = calculate_cropped_area(width, height, test_width, test_height)
            if (test_height, test_width) in _preferred_sizes:
                test_loss *= preferred_sizes_bonus
            if test_loss < loss or (test_loss == loss and
                                    (candidate_width < test_width or candidate_height < test_height)):
                candidate_width = test_width
                candidate_height = test_height
                loss = test_loss

    return QSize(candidate_width, candidate_height)

def get_noteable_aspect_ratio(width: float|int, height: float|int) -> tuple[int, int, bool] | None:
    """Test whether the aspect_ratio is noteable and return it."""
    aspect_ratio = width / height if height > 0 else 100
    for ar in aspect_ratios:
        if abs(ar[2] - aspect_ratio) < 1e-3:
            return ar[0], ar[1], (width, height) in _preferred_sizes
        elif abs(1/ar[2] - aspect_ratio) < 1e-3:
            return ar[1], ar[0], (width, height) in _preferred_sizes
    return None
