from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QWidget


class KeyPressForwarder(QObject):
    """Event filter that forwards key presses to a target widget."""

    def __init__(self, parent, target: QWidget,
                 keys_to_forward: tuple[Qt.Key, ...]):
        # A parent is required to avoid garbage collection.
        super().__init__(parent)
        self.target = target
        self.keys_to_forward = keys_to_forward

    def eventFilter(self, _, event: QEvent) -> bool:
        if event.type() != QEvent.KeyPress:
            return False
        if event.key() in self.keys_to_forward:
            self.target.keyPressEvent(event)
            return True
        return False
