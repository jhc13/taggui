from PySide6.QtCore import QModelIndex, QThread, Signal, Qt

from ultralytics import YOLO

from models.image_list_model import ImageListModel
from utils.image import Image
from utils.ModelThread import ModelThread


class MarkingThread(ModelThread):
    # The image index, the caption, and the tags with the caption added. The
    # third parameter must be declared as `list` instead of `list[str]` for it
    # to work.
    marking_generated = Signal(QModelIndex, list)

    def __init__(self, parent, image_list_model: ImageListModel,
                 selected_image_indices: list[QModelIndex],
                 marking_settings: dict):
        super().__init__(parent, image_list_model, selected_image_indices)
        self.marking_settings = marking_settings
        self.model: YOLO | None = None
        self.text = {
            'Generating': 'Marking',
            'generating': 'marking'
        }

    def load_model(self):
        if not self.model:
            self.error_message = 'Model not preloaded.'
            self.is_error = True
        pass

    def preload_model(self):
        if self.marking_settings['model_path'] is None:
            self.error_message = 'Model path not set'
            self.is_error = True
            self.model = None
            return
        self.model = YOLO(self.marking_settings['model_path'])

    def get_model_inputs(self, image: Image):
        return '', {}

    def generate_output(self, image_index, image: Image, image_prompt, model_inputs) -> str:
        if len(self.marking_settings['classes']) == 0:
            return 'No classes to mark selected.'
        classes = list(self.marking_settings['classes'].keys())
        results = self.model.predict(source=image.path,
                                     conf=self.marking_settings['conf'],
                                     iou=self.marking_settings['iou'],
                                     max_det=self.marking_settings['max_det'],
                                     classes=classes,
                                     retina_masks=True)
        markings = []
        for r in results:
            for box, class_id, confidence in zip(r.boxes.xyxy.to('cpu').tolist(),
                                                 r.boxes.cls.to('cpu').tolist(),
                                                 r.boxes.conf.to('cpu').tolist()):
                marking = self.marking_settings['classes'].get(class_id)
                if marking is not None:
                    markings.append({'box': box,
                                     'label': marking[0],
                                     'type': marking[1],
                                     'confidence': round(confidence, 3)})
        self.marking_generated.emit(image_index, markings)
        return f'Found {len(markings)} marking(s).'
