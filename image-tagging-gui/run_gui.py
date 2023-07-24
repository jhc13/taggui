import sys

from PySide6.QtWidgets import QApplication

from widgets.main_window import MainWindow


def run_gui():
    app = QApplication([])
    app.setStyle('Fusion')
    main_window = MainWindow(app)
    main_window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    run_gui()
