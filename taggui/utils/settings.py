from PySide6.QtCore import QSettings

# Defaults for settings that are accessed from multiple places.
DEFAULT_SETTINGS = {
    'font_size': 16,
    # Common image formats that are supported in PySide6.
    'image_list_file_formats': 'bmp, gif, jpg, jpeg, png, tif, tiff, webp',
    'image_list_image_width': 200,
    'tag_separator': ',',
    'insert_space_after_tag_separator': True,
    'autocomplete_tags': True,
    'models_directory_path': '',
    'export_preset': 'SDXL, SD3, Flux',
    'export_resolution': 1024,
    'export_bucket_res_size': 64,
    'export_preferred_sizes' : '1024:1024, 1408:704, 1216:832, 1152:896, 1344:768, 1536:640',
    'export_upscaling': False,
    'export_bucket_strategy': 'crop',
    'export_format': '.jpg - JPEG',
    'export_quality': 75,
    'export_color_space': 'sRGB',
    'export_directory_path': '',
    'export_keep_dir_structure': False
}


def get_settings() -> QSettings:
    settings = QSettings('taggui', 'taggui')
    return settings


def get_tag_separator() -> str:
    settings = get_settings()
    tag_separator = settings.value(
        'tag_separator', defaultValue=DEFAULT_SETTINGS['tag_separator'],
        type=str)
    insert_space_after_tag_separator = settings.value(
        'insert_space_after_tag_separator',
        defaultValue=DEFAULT_SETTINGS['insert_space_after_tag_separator'],
        type=bool)
    if insert_space_after_tag_separator:
        tag_separator += ' '
    return tag_separator
