from PySide6 import QtCore
from PySide6 import QtWidgets

from models.ImageCompModel import ImageComparator
from models.image_list_model import ImageListModel, get_file_paths
from models.proxy_image_list_model import ProxyImageListModel
from utils.image import Image
from widgets.image_list import ImageList
from utils.settings import DEFAULT_SETTINGS, get_settings
#from widgets.image_list import ImageListView #tried, but does too many things this doesnt need


class ImageListView(QtWidgets.QListView):
    def __init__(self):
        super().__init__()
        
        return

class CompList(QtWidgets.QDockWidget):
    def __init__(self, proxy_image_list_model: ProxyImageListModel, imagelist: ImageList):
        super().__init__()
        self.imagelistmodel = proxy_image_list_model
        self.imageList = imagelist
        self.setObjectName('comp_images')
        self.setWindowTitle('Similar Images')
        self.setAllowedAreas(QtCore.Qt.RightDockWidgetArea | QtCore.Qt.LeftDockWidgetArea)

        self.list_view = ImageListView()

        self.filter_line_edit = QtWidgets.QLabel()
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        self.label = QtWidgets.QLabel("Similar Images")
        layout.addWidget(self.label)

        self.methodDrop = QtWidgets.QHBoxLayout()
        self.drop = QtWidgets.QComboBox()
        self.drop.addItems(['hash', 'short', 'histogram', 'template matching', 'feature', 'pixel-by-pixel'])
        self.methodDrop.addWidget(self.drop)

        button = QtWidgets.QPushButton('find similar')
        button.clicked.connect(self.load_images)
        self.methodDrop.addWidget(button)

        layout.addLayout(self.methodDrop)

        self.gridLayout = QtWidgets.QGridLayout()
        
        self.settings = get_settings()

        layout.addLayout(self.gridLayout)
        self.setLayout(layout)
        
    @QtCore.Slot()
    def load_images(self, proxy_image_index: QtCore.QModelIndex):
        selected = self.drop.currentText()
        directory = self.settings.value('directory_path')
        Images = []
        file_paths = get_file_paths(directory)
        Images = {path for path in file_paths if path.suffix.lower() in self.settings.value('supportedImageFormats', DEFAULT_SETTINGS['supportedImageFormats'], type=str)}

        self.imageList.image_index_label
        self.image_index = self.imagelistmodel.mapToSource(
            proxy_image_index)
        CI: Image = self.imagelistmodel.data(proxy_image_index, QtCore.Qt.UserRole)
        print(CI)
        print(type(CI))

        imagecomp = ImageComparator(CI)
        for image in Images:
            if selected == 'hash':
                imagecomp.hash_comparison()


            
