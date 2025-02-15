from math import sqrt
import re

from utils.settings import DEFAULT_SETTINGS, get_settings

# singleton data store
_preferred_sizes : list[tuple[int, int]] | None = None

def prepare(aspect_ratios : list[tuple[int, int, int]] | None = None) -> list[tuple[int, int, int]] | None:
    """
    Prepare by parsing the user supplied preferred sizes.

    Parameters
    ----------
    aspect_ratios : list(tuple[int, int, int]) | None
        A list of typical aspect ratios to take care of

    Return
    ------
        The same list of aspect ratios (when supplied) but extrended by the real
        aspect ratios of the preferred sizes.
    """
    global _preferred_sizes
    _preferred_sizes = []
    for res_str in re.split(r'\s*,\s*', get_settings().value('export_preferred_sizes') or ''):
        try:
            if res_str == '':
                continue
            size_str = res_str.split(':')
            width = max(int(size_str[0]), int(size_str[1]))
            height = min(int(size_str[0]), int(size_str[1]))
            _preferred_sizes.append((width, height))
            if not width == height:
                _preferred_sizes.append((height, width))
            if aspect_ratios != None:
                # add exact aspect ratio of the preferred size to label it
                # similar to the perfect one
                aspect_ratio = width / height
                for ar in aspect_ratios:
                    if abs(ar[2] - aspect_ratio) < 0.15:
                        aspect_ratios.append((ar[0], ar[1], aspect_ratio))
                    break
        except ValueError:
            # Handle cases where the resolution string is not in the correct format
            print(f'Warning: Invalid resolution format: {res_str}. Skipping.',
                    file=sys.stderr)
            continue # Skip to the next resolution if there's an error
    return aspect_ratios

def get(dimensions: tuple[int, int]):
    """
    Determine the dimensions of an image it should have when it is exported.

    Note: this gives the optimal answer and thus can be slower than the Kohya
    bucket algorithm.

    Parameters
    ----------
    dimensions : tuple[int, int]
        The width and height of the image
    """
    global _preferred_sizes
    width, height = dimensions
    # The target resolution of the AI model. The target image pixels
    # will not exceed the square of this number
    resolution = get_settings().value('export_resolution', defaultValue=DEFAULT_SETTINGS['export_resolution'], type=int)
    # Is upscaling of images allowed?
    upscaling = get_settings().value('export_upscaling', defaultValue=DEFAULT_SETTINGS['export_upscaling'], type=bool)
    # The resolution of the buckets
    bucket_res = get_settings().value('export_bucket_res_size', defaultValue=DEFAULT_SETTINGS['export_bucket_res_size'], type=int)

    if not _preferred_sizes:
        prepare()

    if resolution == 0:
        # no rescale in this case, only cropping
        return ((width // bucket_res)*bucket_res, (height // bucket_res)*bucket_res)

    if width < bucket_res or height < bucket_res:
        # it doesn't make sense to use such a small image. But we shouldn't
        # patronize the user
        return dimensions

    preferred_sizes_bonus = 0.4 # reduce the loss by this factor

    max_pixels = resolution * resolution
    opt_width = resolution * sqrt(width/height)
    opt_height = resolution * sqrt(height/width)
    if not upscaling:
        opt_width = min(width, opt_width)
        opt_height = min(height, opt_height)

    # test 1, guaranteed to find a solution: shrink and crop
    # 1.1: exact width
    candidate_width = (opt_width // bucket_res) * bucket_res
    candidate_height = ((height * candidate_width / width) // bucket_res) * bucket_res
    loss = ((height * candidate_width / width) - candidate_height) * candidate_width
    if (candidate_width, candidate_height) in _preferred_sizes:
        loss *= preferred_sizes_bonus
    # 1.2: exact height
    test_height = (opt_height // bucket_res) * bucket_res
    test_width = ((width * test_height / height) // bucket_res) * bucket_res
    test_loss = ((width * test_height / height) - test_width) * test_height
    if (test_height, test_width) in _preferred_sizes:
        test_loss *= preferred_sizes_bonus
    if test_loss < loss:
        candidate_width = test_width
        candidate_height = test_height
        loss = test_loss

    # test 2, going bigger might still fit in the size budget due to cropping
    # 2.1: exact width
    for delta in range(1, 10):
        test_width = (opt_width // bucket_res + delta) * bucket_res
        test_height = ((height * test_width / width) // bucket_res) * bucket_res
        if test_width * test_height > max_pixels:
            break
        if (test_width > width or test_height > height) and not upscaling:
            break
        test_loss = ((height * test_width / width) - test_height) * test_width
        if (test_height, test_width) in _preferred_sizes:
            test_loss *= preferred_sizes_bonus
            if test_loss < loss:
                candidate_width = test_width
                candidate_height = test_height
                loss = test_loss
    # 2.2: exact height
    for delta in range(1, 10):
        test_height = (opt_height // bucket_res + delta) * bucket_res
        test_width = ((width * test_height / height) // bucket_res) * bucket_res
        if test_width * test_height > max_pixels:
            break
        if (test_width > width or test_height > height) and not upscaling:
            break
        test_loss = ((width * test_height / height) - test_width) * test_height
        if (test_height, test_width) in _preferred_sizes:
            test_loss *= preferred_sizes_bonus
        if test_loss < loss:
            candidate_width = test_width
            candidate_height = test_height
            loss = test_loss

    return int(candidate_width), int(candidate_height)
