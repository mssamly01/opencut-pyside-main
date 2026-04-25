from __future__ import annotations

from app.domain.commands.base_command import BaseCommand
from app.domain.transition import Transition


class RemoveTransitionCommand(BaseCommand):
    def __init__(self, track, transition_id: str) -> None:
        self._track = track
        self._transition_id = transition_id
        self._removed: Transition | None = None
        self._removed_index: int | None = None

    def execute(self) -> None:
        for index, transition in enumerate(self._track.transitions):
            if transition.transition_id == self._transition_id:
                self._removed = transition
                self._removed_index = index
                self._track.transitions.pop(index)
                return

    def undo(self) -> None:
        if self._removed is None or self._removed_index is None:
            return
        self._track.transitions.insert(self._removed_index, self._removed)
