from utils.settings_widgets import SettingsBigCheckBox
from utils.utils import ConfirmationDialog


class CaptionMultipleImagesDialog(ConfirmationDialog):
    def __init__(self, selected_image_count: int, caption_singular = 'Caption',
                 caption_plural = 'Captions'):
        title = f'Generate {caption_plural}'
        question = f'{caption_singular} {selected_image_count} selected images?'
        super().__init__(title=title, question=question)
        self.show_alert_check_box = SettingsBigCheckBox(
            key='show_alert_when_captioning_finished', default=True,
            text='Show alert when finished')
        self.setCheckBox(self.show_alert_check_box)
        layout = self.layout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
