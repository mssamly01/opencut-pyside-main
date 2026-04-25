from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.domain.commands import UpdatePropertyCommand
from PySide6.QtWidgets import QWidget


@contextmanager
def block_signals(*widgets: object) -> Iterator[None]:
    previous_states = [widget.blockSignals(True) for widget in widgets]
    try:
        yield
    finally:
        for widget, previous_state in zip(widgets, previous_states, strict=True):
            widget.blockSignals(previous_state)


class CommandAwareInspector(QWidget):
    def __init__(self, timeline_controller: object, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._timeline_controller = timeline_controller

    def _apply_property_update(self, target: Any, attribute_name: str, value: Any) -> None:
        if getattr(target, attribute_name) == value:
            return

        self._timeline_controller.execute_command(
            UpdatePropertyCommand(target=target, attribute_name=attribute_name, new_value=value)
        )
