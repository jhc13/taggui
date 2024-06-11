from PySide6.QtWidgets import QGridLayout

from utils.settings_widgets import SettingsBigCheckBox
from utils.utils import ConfirmationDialog


class CaptionMultipleImagesDialog(ConfirmationDialog):
    def __init__(self, selected_image_count: int):
        title = 'Generate Captions'
        question = f'Caption {selected_image_count} selected images?'
        super().__init__(title=title, question=question)
        self.show_alert_check_box = SettingsBigCheckBox(
            key='show_alert_when_captioning_finished', default=True,
            text='Show alert when finished')
        self.play_sound_check_box = SettingsBigCheckBox(
            key='play_sound_when_captioning_finished', default=False,
            text='Play sound when finished')
        self.setCheckBox(self.show_alert_check_box)
        layout: QGridLayout = self.layout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        row, column, row_span, column_span = layout.getItemPosition(
            layout.indexOf(self.show_alert_check_box))
        layout.addWidget(self.play_sound_check_box, row + 1, column, row_span,
                         column_span)
