from __future__ import annotations

from collections.abc import Iterable

from app.domain.selection import SelectionState
from PySide6.QtCore import QObject, Signal


class SelectionController(QObject):
    selection_changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = SelectionState()

    # --- Single-select API (legacy) -----------------------------------
    def selected_clip_id(self) -> str | None:
        return self._state.selected_clip_id

    def select_clip(self, clip_id: str) -> None:
        if self._state.selected_clip_ids == [clip_id]:
            return
        self._state.selected_clip_ids = [clip_id]
        self.selection_changed.emit()

    def clear_selection(self) -> None:
        if not self._state.selected_clip_ids:
            return
        self._state.selected_clip_ids = []
        self.selection_changed.emit()

    # --- Multi-select API ---------------------------------------------
    def selected_clip_ids(self) -> list[str]:
        return list(self._state.selected_clip_ids)

    def is_selected(self, clip_id: str) -> bool:
        return clip_id in self._state.selected_clip_ids

    def set_selection(self, clip_ids: Iterable[str]) -> None:
        deduped: list[str] = []
        for clip_id in clip_ids:
            if clip_id and clip_id not in deduped:
                deduped.append(clip_id)
        if deduped == self._state.selected_clip_ids:
            return
        self._state.selected_clip_ids = deduped
        self.selection_changed.emit()

    def toggle_selection(self, clip_id: str) -> None:
        if clip_id in self._state.selected_clip_ids:
            self._state.selected_clip_ids.remove(clip_id)
        else:
            self._state.selected_clip_ids.append(clip_id)
        self.selection_changed.emit()

    def add_to_selection(self, clip_id: str) -> None:
        if clip_id in self._state.selected_clip_ids:
            return
        self._state.selected_clip_ids.append(clip_id)
        self.selection_changed.emit()
