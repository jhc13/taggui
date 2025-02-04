from enum import Enum
from collections import defaultdict
from math import floor
import os
import io
from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColorSpace
from PySide6.QtWidgets import (QWidget, QDialog, QFileDialog, QGridLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout,
                               QTableWidget, QTableWidgetItem, QSizePolicy,
                               QMessageBox)
from PIL import Image, ImageFilter, ImageCms

from utils.settings import DEFAULT_SETTINGS, get_settings
from utils.settings_widgets import (SettingsBigCheckBox, SettingsLineEdit,
                                    SettingsSpinBox, SettingsComboBox)
from models.image_list_model import ImageListModel

Presets = {
    'manual': (0, 0),
    'Direct feed through': (0, 1),
    'SD1': (512, 64),
    'SDXL, SD3, Flux': (1024, 64)
}

class ExportFormat(str, Enum):
    JPG = '.jpg - JPEG'
    PNG = '.png - PNG'
    WEBP = '.webp - WEBP'

ExportFormatDict = {
    ExportFormat.JPG: 'jpeg',
    ExportFormat.PNG: 'png',
    ExportFormat.WEBP: 'webp'
}

class IccProfileList(str, Enum):
    SRgb = 'sRGB'
    SRgbLinear = 'sRGB (linear gamma)'
    AdobeRgb = 'AdobeRGB'
    DisplayP3 = 'DisplayP3'
    ProPhotoRgb = 'ProPhotoRGB'
    # since PySide6.8:
    Bt2020 = 'BT.2020'
    Bt2100Pq = 'BT.2100(PQ)'
    Bt2100Hlg = 'BT.2100 (HLG)'

class BucketStrategy(str, Enum):
    CROP = 'crop'
    SCALE = 'scale'
    CROP_SCALE = 'crop and scale'

class ExportDialog(QDialog):
    def __init__(self, parent, image_list_model: ImageListModel):
        super().__init__(parent)
        self.image_list_model = image_list_model
        self.settings = get_settings()
        self.inhibit_statistics_update = True
        self.resolution_cache: dict[tuple, tuple] = {}
        self.setWindowTitle('Export')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        grid_layout = QGridLayout()
        grid_layout.setColumnStretch(0, 0)
        grid_layout.setColumnStretch(1, 1)

        grid_row = 0
        grid_layout.addWidget(QLabel('Preset'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        preset_combo_box = SettingsComboBox(key='export_preset')
        preset_combo_box.addItems(list(Presets))
        preset_combo_box.currentTextChanged.connect(self.apply_preset)
        grid_layout.addWidget(preset_combo_box, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Resolution (px)'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        self.resolution_spin_box = SettingsSpinBox(
            key='export_resolution', default=DEFAULT_SETTINGS['export_resolution'],
            minimum=0, maximum=8192)
        self.resolution_spin_box.setToolTip('Common values:\n'
                                            '0: disable rescaling\n'
                                            '512: SD1.5\n'
                                            '1024: SDXL, SD3, Flux')
        self.resolution_spin_box.textChanged.connect(self.show_megapixels)
        self.resolution_spin_box.textChanged.connect(self.show_statistics)
        grid_layout.addWidget(self.resolution_spin_box, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Image size (megapixel)'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        self.megapixels = QLabel('-')
        grid_layout.addWidget(self.megapixels, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Allow upscaling'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        self.upscaling_check_box = SettingsBigCheckBox(
            key='export_upscaling',
            default=DEFAULT_SETTINGS['export_upscaling'])
        self.upscaling_check_box.setToolTip('Scale too small images to the requested size.\n'
                                    'This should be avoided as it lowers the image quality.')
        self.upscaling_check_box.stateChanged.connect(self.show_statistics)
        grid_layout.addWidget(self.upscaling_check_box, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Bucket resolution size (px)'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        self.bucket_res_size_spin_box = SettingsSpinBox(
            key='export_bucket_res_size', default=DEFAULT_SETTINGS['export_bucket_res_size'],
            minimum=1, maximum=256)
        self.bucket_res_size_spin_box.setToolTip('Ensure that the exported image size is divisable by that number.\n'
                                                 'It should match the setting on the training tool.\n'
                                                 'It might cause minor cropping.')
        self.bucket_res_size_spin_box.textChanged.connect(self.show_statistics)
        grid_layout.addWidget(self.bucket_res_size_spin_box, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Bucket fitting strategy'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        bucket_strategy_combo_box = SettingsComboBox(key='export_bucket_strategy')
        bucket_strategy_combo_box.addItems(list(BucketStrategy))
        bucket_strategy_combo_box.setToolTip('crop: center crop\n'
                                             'scale: assymetric scaling\n'
                                             'crop and scale: use both to minimize each effect')
        grid_layout.addWidget(bucket_strategy_combo_box, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Output format'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        format_widget = QWidget()
        format_layout = QHBoxLayout()
        self.format_combo_box = SettingsComboBox(key='export_format')
        self.format_combo_box.addItems(list(ExportFormat))
        self.format_combo_box.currentTextChanged.connect(self.format_change)
        format_layout.addWidget(self.format_combo_box,
                              Qt.AlignmentFlag.AlignLeft)
        format_layout.addWidget(QLabel('Quality'),
                              Qt.AlignmentFlag.AlignRight)
        self.quality_spin_box = SettingsSpinBox(
            key='export_quality', default=DEFAULT_SETTINGS['export_quality'],
            minimum=0, maximum=100)
        self.quality_spin_box.setToolTip('Only for JPEG and WebP.\n'
                                         '0 is worst and 100 is best.\n'
                                         'For JPEG numbers above 95 should be avoided')
        self.quality_spin_box.textChanged.connect(self.quality_change)
        format_layout.addWidget(self.quality_spin_box,
                              Qt.AlignmentFlag.AlignLeft)
        format_widget.setLayout(format_layout)
        grid_layout.addWidget(format_widget, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Output color space'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        color_space_combo_box = SettingsComboBox(key='export_color_space')
        color_space_combo_box.addItem("feed through (don't touch)")
        color_space_combo_box.addItem('sRGB (implicit, without profile)')
        color_space_combo_box.addItems([IccProfileList[e.name] for e in QColorSpace.NamedColorSpace])
        color_space_combo_box.setToolTip('Color space of the exported images.\n'
                                         'Most likely the trainer expects sRGB!\n'
                                         '\n'
                                         'Use "feed through" to keep the color space as it is.\n'
                                         'Use "sRGB (implicit, without profile)" to save in sRGB but don\'t embed the ICC profile to save 8k file size.')
        grid_layout.addWidget(color_space_combo_box, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Export directory'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        self.export_directory_line_edit = SettingsLineEdit(
            key='export_directory_path',
            default=DEFAULT_SETTINGS['export_directory_path'])
        self.export_directory_line_edit.setMinimumWidth(400)
        self.export_directory_line_edit.setClearButtonEnabled(True)
        grid_layout.addWidget(self.export_directory_line_edit, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        export_directory_button = QPushButton('Select Directory...')
        export_directory_button.clicked.connect(self.set_export_directory_path)
        grid_layout.addWidget(export_directory_button, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Keep input directory structure'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        keep_dir_structure_check_box = SettingsBigCheckBox(
            key='export_keep_dir_structure',
            default=DEFAULT_SETTINGS['export_keep_dir_structure'])
        keep_dir_structure_check_box.setToolTip('Keep the subdirectory structure or export\n'
                                                'all images in the same export directory')
        grid_layout.addWidget(keep_dir_structure_check_box, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Statistics'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        self.statistics_table = QTableWidget(0, 5, self)
        self.statistics_table.setHorizontalHeaderLabels(['Width', 'Height', 'Count', 'Aspect ratio', 'Size utilization'])
        self.statistics_table.setMinimumWidth(400)
        grid_layout.addWidget(self.statistics_table, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        layout.addLayout(grid_layout)
        export_button = QPushButton('Export')
        export_button.clicked.connect(self.do_export)
        layout.addWidget(export_button)

        # update display
        self.apply_preset(preset_combo_box.currentText())
        self.show_megapixels()
        self.inhibit_statistics_update = False
        self.show_statistics()

    @Slot()
    def apply_preset(self, value):
        if value == 'manual':
            self.resolution_spin_box.setEnabled(True)
            self.bucket_res_size_spin_box.setEnabled(True)
        else:
            preset = Presets[value]
            self.inhibit_statistics_update = True
            self.resolution_spin_box.setValue(preset[0])
            self.resolution_spin_box.setEnabled(False)
            self.bucket_res_size_spin_box.setValue(preset[1])
            self.bucket_res_size_spin_box.setEnabled(False)
            self.inhibit_statistics_update = False
            self.show_statistics()

    @Slot()
    def show_megapixels(self):
        resolution = self.resolution_spin_box.value()
        if resolution > 0:
            megapixels = resolution * resolution / 1024 / 1024
            self.megapixels.setText(f"{megapixels:.3f}")
        else:
            self.megapixels.setText('-')

    @Slot()
    def format_change(self, export_format):
        if export_format == ExportFormat.JPG:
            self.quality_spin_box.setValue(75)
            self.quality_spin_box.setEnabled(True)
        elif export_format == ExportFormat.PNG:
            self.quality_spin_box.setValue(100)
            self.quality_spin_box.setEnabled(False)
        elif export_format == ExportFormat.WEBP:
            self.quality_spin_box.setValue(80)
            self.quality_spin_box.setEnabled(True)

    @Slot()
    def quality_change(self, quality):
        if (self.format_combo_box.currentText() == ExportFormat.JPG) and int(quality) > 95:
            self.quality_spin_box.setStyleSheet('background: orange')
        else:
            self.quality_spin_box.setStyleSheet('')

    @Slot()
    def show_statistics(self):
        if self.inhibit_statistics_update:
            return

        self.resolution_cache = {}
        resolution = self.resolution_spin_box.value()
        upscaling = self.upscaling_check_box.isChecked()
        bucket_res = self.bucket_res_size_spin_box.value()

        # notable aspect ratios
        aspect_ratios = [
            (1, 1, 1),
            (2, 1, 2/1),
            (3, 2, 3/2),
            (4, 3, 4/3),
            (16, 9, 16/9),
            (21, 9, 21/9),
        ]

        image_dimensions = defaultdict(int)
        for image_index in range(self.image_list_model.rowCount()):
            this_image = self.image_list_model.index(image_index).data(Qt.ItemDataRole.UserRole)
            this_image.target_dimensions = self.target_dimensions(this_image.dimensions, resolution, upscaling, bucket_res)
            image_dimensions[this_image.target_dimensions] += 1

        sorted_dimensions = sorted(
                image_dimensions.items(),
                key=lambda x: x[0][0] / x[0][1]  # Sort by width/height ratio
            )

        self.statistics_table.setRowCount(0) # clear old data
        for dimensions, count in sorted_dimensions:
            width, height = dimensions
            aspect_ratio = width / height
            rowPosition = self.statistics_table.rowCount()
            notable_aspect_ratio = ''
            for ar in aspect_ratios:
                if abs(ar[2] - aspect_ratio) < 1e-3:
                    notable_aspect_ratio = f" ({ar[0]}:{ar[1]})"
                elif abs(1/ar[2] - aspect_ratio) < 1e-3:
                    notable_aspect_ratio = f" ({ar[1]}:{ar[0]})"
            utilization = (width * height)**0.5 / resolution if resolution > 0 else 1

            self.statistics_table.insertRow(rowPosition)
            self.statistics_table.setItem(rowPosition, 0, QTableWidgetItem(str(width)))
            self.statistics_table.setItem(rowPosition, 1, QTableWidgetItem(str(height)))
            self.statistics_table.setItem(rowPosition, 2, QTableWidgetItem(str(count)))
            self.statistics_table.setItem(rowPosition, 3, QTableWidgetItem(f"{aspect_ratio:.3f}{notable_aspect_ratio}"))
            self.statistics_table.setItem(rowPosition, 4, QTableWidgetItem(f"{100*utilization:.1f}%"))

    def target_dimensions(self, dimensions, resolution, upscaling, bucket_res):
        """
        Given the original width and height, the bucket resolution step size,
        and a maximum allowed area, return new dimensions (width, height)
        where both dimensions are multiples of `bucket_res`, their product
        does not exceed resolution**2, and the new aspect ratio (width/height)
        is as close as possible to the original aspect ratio.

        Note: this gives the optimal answer and thus can be slower than the Kohya bucket
              algorithm
        """
        if resolution == 0:
            # no rescale in this case, only cropping
            return ((dimensions[0] // bucket_res)*bucket_res, (dimensions[1] // bucket_res)*bucket_res)

        if dimensions in self.resolution_cache:
            return self.resolution_cache[dimensions]

        max_area = resolution**2

        # Compute the original aspect ratio.
        target_ratio = dimensions[0] / dimensions[1]

        # The maximum allowed product of multipliers.
        T = max_area // (bucket_res * bucket_res)

        best_candidate = None  # will hold (new_width, new_height, error, area)

        # Loop over possible values for b (the vertical multiplier).
        # We choose b from 1 up to T (although many values will be skipped
        # because the corresponding a then makes a * b > T).
        for b in range(1, T + 1):
            # Choose a so that a / b is as close as possible to target_ratio.
            # (We round the ideal value a = target_ratio * b to the nearest integer.)
            a = round(target_ratio * b)
            if a < 1:
                a = 1  # ensure at least bucket_res pixels

            # Check that the candidate image area (in multiplier units) does not exceed T.
            if a * b > T:
                # If a*b is too big, skip the candidate.
                continue

            candidate_width = a * bucket_res
            candidate_height = b * bucket_res
            candidate_area = candidate_width * candidate_height

            if not upscaling and (candidate_width > dimensions[0] or candidate_height > dimensions[1]):
                continue

            # Compute the aspect ratio error.
            candidate_ratio = a / b
            error = abs(candidate_ratio - target_ratio)
            # compute the mean squared error of ratio and normalized maximum size
            error = (candidate_ratio - target_ratio)**2 + ((max_area-candidate_area)/max_area)**2

            # We choose the candidate with the lowest error. In case of a tie, we choose
            # the one that uses the largest area (i.e. as close as possible to resolution**2).
            if best_candidate is None:
                best_candidate = (candidate_width, candidate_height, error, candidate_area)
            else:
                _, _, best_error, best_area = best_candidate
                if (error < best_error) or (abs(error - best_error) < 1e-9 and candidate_area > best_area):
                    best_candidate = (candidate_width, candidate_height, error, candidate_area)

        # Fallback: if no candidate is found (this shouldn't happen for reasonable values),
        # simply return the smallest possible image.
        if best_candidate is None:
            return bucket_res, bucket_res
        else:
            new_width, new_height, _, _ = best_candidate
            self.resolution_cache[dimensions] = (new_width, new_height)
            return new_width, new_height

    @Slot()
    def set_export_directory_path(self):
        export_directory_path = self.settings.value(
            'export_directory_path',
            defaultValue=DEFAULT_SETTINGS['export_directory_path'], type=str)
        if export_directory_path:
            initial_directory_path = export_directory_path
        elif self.settings.contains('directory_path'):
            initial_directory_path = self.settings.value('directory_path')
        else:
            initial_directory_path = ''
        export_directory_path = QFileDialog.getExistingDirectory(
            parent=self, caption='Select directory for image export',
            dir=initial_directory_path)
        if export_directory_path:
            self.export_directory_line_edit.setText(export_directory_path)

    @Slot()
    def do_export(self):
        directory_path = self.settings.value('directory_path', type=str)
        export_directory_path = Path(self.settings.value('export_directory_path', type=str))
        export_keep_dir_structure = self.settings.value('export_keep_dir_structure', type=bool)
        no_overwrite = True
        if os.path.exists(export_directory_path):
            if os.path.isfile(export_directory_path):
                QMessageBox.critical(
                    self,
                    'Path error',
                    'The export directory path points to a file and not to a directory'
                )
                return
            if os.listdir(export_directory_path):
                msgBox = QMessageBox()
                msgBox.setIcon(QMessageBox.Warning)
                msgBox.setWindowTitle('Path warning')
                msgBox.setText('The export directory path is not empty')
                overwrite_button = msgBox.addButton('Overwrite', QMessageBox.YesRole)
                rename_button = msgBox.addButton('Rename', QMessageBox.NoRole)
                msgBox.addButton(QMessageBox.Cancel)
                msgBox.setDefaultButton(QMessageBox.Cancel)
                button = msgBox.exec_()
                if button == QMessageBox.Cancel:
                    return
                if msgBox.clickedButton() == overwrite_button:
                    no_overwrite = False
        else:
            QMessageBox.critical(
                self,
                'Path error',
                'The export directory path does not exist'
            )
            return

        resolution = self.resolution_spin_box.value()
        upscaling = self.upscaling_check_box.isChecked()
        bucket_res = self.bucket_res_size_spin_box.value()
        export_format = self.format_combo_box.currentText()
        quality = self.quality_spin_box.value()
        color_space = self.settings.value('export_color_space', type=str)
        save_profile = True
        if color_space == 'sRGB (implicit, without profile)':
            color_space = 'sRGB'
            save_profile = False
        bucket_strategy = self.settings.value('export_bucket_strategy', type=str)

        for image_index in range(self.image_list_model.rowCount()):
            image_entry = self.image_list_model.index(image_index).data(Qt.ItemDataRole.UserRole)
            if export_keep_dir_structure:
                relative_path = image_entry.path.relative_to(directory_path)
                export_path = export_directory_path / relative_path
                export_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                export_path = export_directory_path / image_entry.path.name
            export_path = export_path.with_suffix(export_format.split(' ', 1)[0])

            if no_overwrite:
                stem = export_path.stem
                counter = 0
                while export_path.exists():
                    export_path = export_path.parent / f"{stem}_{counter}{export_path.suffix}"
                    counter += 1

            image_file = Image.open(image_entry.path)
            # Preserve alpha if present:
            if image_file.mode in ("RGBA", "LA", "PA") and not export_format == ExportFormat.JPG:  # Check for alpha channels
                image_file = image_file.convert("RGBA")
            else:
                image_file = image_file.convert("RGB")  # Otherwise, convert to RGB

            new_width, new_height = image_entry.target_dimensions
            current_width, current_height = image_file.size
            if bucket_strategy == BucketStrategy.CROP or bucket_strategy == BucketStrategy.CROP_SCALE:
                if current_height * new_width / current_width < new_height: # too wide
                    new_width = floor(current_width * new_height / current_height)
                else: # too high
                    new_height = floor(current_height * new_width / current_width)
            if bucket_strategy == BucketStrategy.CROP_SCALE:
                new_width = floor((image_entry.target_dimensions[0] + new_width)/2)
                new_height = floor((image_entry.target_dimensions[1] + new_height)/2)
            if image_file.size[0] != new_width or image_file.size[1] != new_height:
                # resize with the best method available
                resized_image = image_file.resize((new_width, new_height), Image.LANCZOS)
                # followed by a slight sharpening as it should be done
                sharpend_image = resized_image.filter(ImageFilter.UnsharpMask(radius = 0.5, percent = 100, threshold = 3))
            else:
                sharpend_image = image_file

            # crop to the desired size
            current_width, current_height = sharpend_image.size
            crop_width = floor((current_width - image_entry.target_dimensions[0]) / 2)
            crop_height = floor((current_height - image_entry.target_dimensions[1]) / 2)
            cropped_image = sharpend_image.crop((crop_width, crop_height, current_width - crop_width, current_height - crop_height))

            if color_space == "feed through (don't touch)":
                cropped_image.save(export_path, format=ExportFormatDict[export_format], quality=quality, icc_profile=cropped_image.info.get('icc_profile'))
            else:
                source_profile_raw = image_file.info.get('icc_profile')
                if source_profile_raw is None: # assume sRGB
                    source_profile_raw = QColorSpace(QColorSpace.SRgb).iccProfile()
                source_profile = ImageCms.ImageCmsProfile(io.BytesIO(source_profile_raw))
                target_profile_raw = QColorSpace(getattr(QColorSpace, IccProfileList(color_space).name)).iccProfile()
                target_profile = ImageCms.ImageCmsProfile(io.BytesIO(target_profile_raw))
                final_image = ImageCms.profileToProfile(cropped_image, source_profile, target_profile)
                if save_profile:
                    final_image.save(export_path, format=ExportFormatDict[export_format], quality=quality, icc_profile=target_profile.tobytes())
                else:
                    final_image.save(export_path, format=ExportFormatDict[export_format], quality=quality, icc_profile=None)
        self.close()
