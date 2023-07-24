from PySide6.QtCore import QSettings

default_settings = {
    'font_size': 18,
    'image_list_image_width': 200,
    'tag_separator': ',',
    'insert_space_after_tag_separator': True,
}


def set_default_settings(settings: QSettings):
    for key, value in default_settings.items():
        if not settings.contains(key):
            settings.setValue(key, value)


def get_settings() -> QSettings:
    settings = QSettings('image-tagging-gui', 'image-tagging-gui')
    set_default_settings(settings)
    return settings


def get_separator(settings: QSettings) -> str:
    separator = settings.value('tag_separator')
    # The value is initially a Boolean, but becomes a string when saved and
    # loaded.
    insert_space_after_separator = settings.value(
        'insert_space_after_tag_separator') in (True, 'true')
    if insert_space_after_separator:
        separator += ' '
    return separator
