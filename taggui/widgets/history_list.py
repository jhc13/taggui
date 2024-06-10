import json
from pathlib import Path
from datetime import datetime
from typing import Any, Callable, Dict

from transformers import AutoModel
from PySide6.QtCore import (QAbstractListModel, QModelIndex, Qt)
from PySide6.QtWidgets import (QDockWidget, QListView, QVBoxLayout, QWidget)

from auto_captioning.models import get_model_type
from models.image_list_model import ImageListModel
from utils.enums import CaptionModelType

class HistoryListModel(QAbstractListModel):
    def __init__(self, repo_infos):
        super().__init__()
        self.history_list = []
        self.app_infos = repo_infos
        self.image_directory_path: Path | None = None

    def data(self, index: QModelIndex, role: Qt.ItemDataRole):
        if not index.isValid():
            return None
        item = self.history_list[index.row()]
        if role == Qt.UserRole:
            return item
        if role == Qt.DisplayRole:
            ret = f"{item['date']} '{item['app']['settings']['prompt'][:20]}'"
            return ret

    def rowCount(self, parent: QModelIndex | None=None) -> int:
        return len(self.history_list)

    def load_directory(self, image_directory_path: Path):
        self.beginResetModel()
        self.image_directory_path = image_directory_path
        self.history_list = []
        history_path = image_directory_path / "!0_history.jsonl"
        if history_path.exists():
            with open(history_path) as file:
                for line in file:
                    entry = json.loads(line)
                    self.history_list.append(entry)
        self.endResetModel()

    def append(self, caption_settings: dict, model: AutoModel, image_list_model: ImageListModel, selected_image_indices: list[QModelIndex]) -> None:
        caption_settings = caption_settings.copy()
        model_id = caption_settings["model"]
        model_type = get_model_type(model_id)

        # clean up settings
        del_keys = ["device", "gpu_index"]
        for del_key in del_keys:
            del caption_settings[del_key]
        if model_type == CaptionModelType.WD_TAGGER:
            del caption_settings["generation_parameters"]
        else:
            del caption_settings["wd_tagger_settings"]
            if not caption_settings["generation_parameters"]["do_sample"]:
                del_keys = ["temperature", "top_k", "top_p", "repetition_penalty", "no_repeat_ngram_size"]
                for del_key in del_keys:
                    del caption_settings["generation_parameters"][del_key]

        # app infos
        app = { **self.app_infos, "settings": caption_settings }

        # model infos
        model_config = model.config
        model = {
            "name": model_config.name_or_path,
            #"name": model.pretrained_model_name_or_path,
            #"name": model.model_name_or_path,
            "type": str(model_config.model_type),
            #"revision": model_config.revision,
        }

        # images
        images = []
        if self.image_directory_path != None:
            images = sorted([str(image_list_model.images[i.row()].path.relative_to(self.image_directory_path)) for i in selected_image_indices])

        # collect infos
        entry = {
            "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "history_version": 0,
            "app": app,
            "model": model,
            "images": images,
        }

        # append to internal list
        self.beginInsertRows(QModelIndex(), self.rowCount(), self.rowCount())
        self.history_list.append(entry)
        self.endInsertRows()

        # append to history file
        if self.image_directory_path != None:
            with open(f"{self.image_directory_path}/!0_history.jsonl", "a") as file:
                json_str = json.dumps(entry, separators=(',', ':'))
                file.write(json_str + "\r\n")

class HistoryList(QDockWidget):
    def __init__(self, model: HistoryListModel):
        super().__init__()
        self.set_captions_settings: Callable[[Dict[str, Any]], None] | None = None
        self.setObjectName('history_list')
        self.setWindowTitle('History')
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea
                             | Qt.DockWidgetArea.RightDockWidgetArea)

        container = QWidget()

        self.listView = QListView()
        self.listView.setModel(model)
        self.listView.clicked.connect(self.item_clicked)

        layout = QVBoxLayout(container)
        layout.addWidget(self.listView)

        self.setWidget(container)

    def item_clicked(self, current: QModelIndex):
        if current.isValid():
            index = self.listView.currentIndex()
            entry = self.listView.model().data(index, Qt.UserRole)
            caption_settings = entry['app']['settings']

            if self.set_captions_settings is not None:
                #print(json.dumps(caption_settings))
                self.set_captions_settings(caption_settings)
