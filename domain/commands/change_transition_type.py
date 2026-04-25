from __future__ import annotations

from app.domain.commands.base_command import BaseCommand
from app.domain.transition import TRANSITION_TYPES

_UNSET = object()


class ChangeTransitionTypeCommand(BaseCommand):
    def __init__(self, track, transition_id: str, new_type: str) -> None:
        if new_type not in TRANSITION_TYPES:
            raise ValueError(f"Invalid transition type '{new_type}'")
        self._track = track
        self._transition_id = transition_id
        self._new_type = new_type
        self._old_type: object = _UNSET

    def _find(self):
        for transition in self._track.transitions:
            if transition.transition_id == self._transition_id:
                return transition
        return None

    def execute(self) -> None:
        transition = self._find()
        if transition is None:
            return
        if self._old_type is _UNSET:
            self._old_type = transition.transition_type
        transition.transition_type = self._new_type

    def undo(self) -> None:
        if self._old_type is _UNSET:
            return
        transition = self._find()
        if transition is None:
            return
        transition.transition_type = str(self._old_type)
