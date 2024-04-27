from typing import Callable

from PySide6.QtCore import QEvent, QObject, Qt


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


class FocusedScrollMixin:
    setFocusPolicy: Callable[[Qt.FocusPolicy], None]
    installEventFilter: Callable[[QObject], None]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.installEventFilter(UnfocusedScrollIgnorer(self))
