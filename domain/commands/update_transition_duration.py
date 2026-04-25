from __future__ import annotations

from app.domain.commands.base_command import BaseCommand
from app.domain.transition import MAX_TRANSITION_DURATION

_UNSET = object()


class UpdateTransitionDurationCommand(BaseCommand):
    def __init__(self, track, transition_id: str, new_duration: float) -> None:
        self._track = track
        self._transition_id = transition_id
        self._new_duration = max(0.05, min(MAX_TRANSITION_DURATION, float(new_duration)))
        self._old_duration: object = _UNSET

    def _find(self):
        for transition in self._track.transitions:
            if transition.transition_id == self._transition_id:
                return transition
        return None

    def execute(self) -> None:
        transition = self._find()
        if transition is None:
            return
        if self._old_duration is _UNSET:
            self._old_duration = transition.duration_seconds
        transition.duration_seconds = self._new_duration

    def undo(self) -> None:
        if self._old_duration is _UNSET:
            return
        transition = self._find()
        if transition is None:
            return
        transition.duration_seconds = float(self._old_duration)
