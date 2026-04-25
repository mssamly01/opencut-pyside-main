from __future__ import annotations

from app.domain.commands.base_command import BaseCommand

_UNSET = object()


class UpdatePropertyCommand(BaseCommand):
    def __init__(self, target: object, attribute_name: str, new_value: object) -> None:
        self._target = target
        self._attribute_name = attribute_name
        self._new_value = new_value
        self._old_value: object = _UNSET

    def execute(self) -> None:
        if self._old_value is _UNSET:
            self._old_value = getattr(self._target, self._attribute_name)
        setattr(self._target, self._attribute_name, self._new_value)

    def undo(self) -> None:
        if self._old_value is _UNSET:
            raise RuntimeError("Cannot undo before command execution")
        setattr(self._target, self._attribute_name, self._old_value)
