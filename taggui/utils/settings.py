from PySide6.QtCore import QSettings, Signal

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
    'marking_models_directory_path': '',
    'export_filter': 'All images',
    'export_preset': 'SDXL, SD3, Flux',
    'export_resolution': 1024,
    'export_bucket_res_size': 64,
    'export_latent_size': 8,
    'export_quantize_alpha': True,
    'export_masking_strategy': 'remove',
    'export_masked_content': 'blur + noise',
    'export_preferred_sizes' : '1024:1024, 1408:704, 1216:832, 1152:896, 1344:768, 1536:640',
    'export_upscaling': False,
    'export_bucket_strategy': 'crop',
    'export_format': '.png - PNG',
    'export_quality': 100,
    'export_color_space': 'sRGB',
    'export_caption_algorithm': 'tag list (using tag separator)',
    'export_separate_newline': 'Create additional line',
    'export_directory_path': '',
    'export_keep_dir_structure': False,
    'export_filter_hashtag': True
}


class Settings(QSettings):
    # Signal that shows that the setting with the given string was changes
    change = Signal(str, object, name='settingsChanged')

    def __init__(self):
        super().__init__('taggui', 'taggui')

    def setValue(self, key, value):
        super().setValue(key, value)
        self.change.emit(key, value)

# Common shared instance to ensure the Signal is also shared
settings = Settings()


def get_tag_separator() -> str:
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
