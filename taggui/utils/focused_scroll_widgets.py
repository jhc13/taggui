from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox


class UnfocusedScrollIgnorer(QObject):
    """
    Event filter that ignores scroll events on unfocused widgets.
    """

    def __init__(self, parent):
        # A parent is required to avoid garbage collection.
        super().__init__(parent)

    def eventFilter(self, object_: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Wheel and not object_.hasFocus():
            # This is required to let the scroll area scroll.
            event.ignore()
            return True
        return False


class FocusedScrollComboBox(QComboBox):
    def __init__(self):
        super().__init__()
        # Disable focusing on scroll.
        self.setFocusPolicy(Qt.StrongFocus)
        self.installEventFilter(UnfocusedScrollIgnorer(self))


class FocusedScrollDoubleSpinBox(QDoubleSpinBox):
    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
        self.installEventFilter(UnfocusedScrollIgnorer(self))


class FocusedScrollSpinBox(QSpinBox):
    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
        self.installEventFilter(UnfocusedScrollIgnorer(self))
