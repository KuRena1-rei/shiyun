from PySide6.QtWidgets import QTableWidget, QWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent, QKeyEvent


class FileExplorerTable(QTableWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._click_selected_rows: set[int] = set()
        self._file_manager: "FileManager | None" = None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            index = self.indexAt(event.pos())
            if index.isValid():
                row = index.row()
                modifiers = event.modifiers()
                selected_rows = set(idx.row() for idx in self.selectionModel().selectedRows())
                if modifiers & Qt.ControlModifier:
                    super().mousePressEvent(event)
                elif modifiers & Qt.ShiftModifier:
                    super().mousePressEvent(event)
                else:
                    if row in selected_rows:
                        self.selectionModel().clear()
                        self._click_selected_rows = set()
                    else:
                        super().mousePressEvent(event)
            else:
                super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._file_manager is None:
            super().keyPressEvent(event)
            return
        key = event.key()
        if key == Qt.Key_Delete:
            selected = self._file_manager._get_selected_rows()
            if selected:
                self._file_manager._on_delete_multi(selected)
        else:
            super().keyPressEvent(event)
