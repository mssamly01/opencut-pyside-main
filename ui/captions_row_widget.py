"""Sprint 14: list row widget for CaptionsPanel with inline-editable caption text."""

from __future__ import annotations

from collections.abc import Callable

from app.domain.clips.text_clip import TextClip
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFocusEvent, QKeyEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QWidget


class _CaptionLineEdit(QLineEdit):
    """QLineEdit that emits commit_requested on Enter/focus-out and revert_requested on Escape."""

    commit_requested = Signal(str)
    revert_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._committed = False
        self.editingFinished.connect(self._on_editing_finished)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.revert_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:  # noqa: N802
        super().focusOutEvent(event)
        self._on_editing_finished()

    def reset_committed_flag(self) -> None:
        self._committed = False

    def suppress_commit(self) -> None:
        self._committed = True

    def _on_editing_finished(self) -> None:
        if self._committed:
            return
        self._committed = True
        self.commit_requested.emit(self.text())


class CaptionRowWidget(QWidget):
    """Row composing readonly timestamp prefix + inline-editable text field."""

    def __init__(
        self,
        clip: TextClip,
        timestamp_label: str,
        commit_callback: Callable[[str, str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._clip_id = clip.clip_id
        self._original_text = clip.content or ""
        self._commit_callback = commit_callback
        self._is_editing = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(8)

        self._timestamp_label = QLabel(timestamp_label, self)
        self._timestamp_label.setObjectName("caption_row_timestamp")
        self._timestamp_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._timestamp_label)

        self._text_edit = _CaptionLineEdit(self)
        self._text_edit.setObjectName("caption_row_text")
        self._text_edit.setText(self._original_text)
        self._text_edit.setPlaceholderText("(empty caption)")
        self._text_edit.commit_requested.connect(self._on_commit)
        self._text_edit.revert_requested.connect(self._on_revert)
        layout.addWidget(self._text_edit, 1)

        self._set_editing_state(False)

    def begin_edit(self) -> None:
        """Activate edit mode (focus + select all)."""
        self._set_editing_state(True)
        self._text_edit.reset_committed_flag()
        self._text_edit.setFocus(Qt.FocusReason.OtherFocusReason)
        self._text_edit.selectAll()

    def update_clip_data(self, clip: TextClip, timestamp_label: str) -> None:
        """Refresh display when underlying clip data changes externally."""
        self._timestamp_label.setText(timestamp_label)
        self._original_text = clip.content or ""
        if not self._is_editing:
            self._text_edit.setText(self._original_text)

    def _on_commit(self, new_text: str) -> None:
        if not self._is_editing:
            return
        self._set_editing_state(False)
        if new_text == self._original_text:
            return
        self._original_text = new_text
        self._commit_callback(self._clip_id, new_text)

    def _on_revert(self) -> None:
        if not self._is_editing:
            return
        self._text_edit.suppress_commit()
        self._text_edit.setText(self._original_text)
        self._set_editing_state(False)

    def _set_editing_state(self, is_editing: bool) -> None:
        self._is_editing = is_editing
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not is_editing)
        self._text_edit.setReadOnly(not is_editing)
        if not is_editing:
            self._text_edit.clearFocus()
