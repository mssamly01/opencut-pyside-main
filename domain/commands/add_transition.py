from __future__ import annotations

from app.domain.commands.base_command import BaseCommand
from app.domain.track import Track
from app.domain.transition import Transition
from app.services.transition_service import (
    is_pair_adjacent,
    transition_for_clip_pair,
)


class AddTransitionCommand(BaseCommand):
    def __init__(self, track: Track, transition: Transition) -> None:
        self._track = track
        self._transition = transition
        self._insert_index: int | None = None

    def execute(self) -> None:
        if self._insert_index is None:
            self._validate()
            self._insert_index = len(self._track.transitions)

        if transition_for_clip_pair(
            self._track,
            self._transition.from_clip_id,
            self._transition.to_clip_id,
        ) is not None:
            # Redo after undo is fine; duplicate add without undo is not.
            if not any(
                item.transition_id == self._transition.transition_id
                for item in self._track.transitions
            ):
                raise ValueError("A transition already exists for this clip pair")
            return

        insert_index = min(self._insert_index, len(self._track.transitions))
        self._track.transitions.insert(insert_index, self._transition)

    def undo(self) -> None:
        if self._insert_index is None:
            raise RuntimeError("Cannot undo before command execution")
        for index, transition in enumerate(self._track.transitions):
            if transition.transition_id == self._transition.transition_id:
                del self._track.transitions[index]
                return
        raise RuntimeError(
            f"Transition '{self._transition.transition_id}' was not found on undo"
        )

    def _validate(self) -> None:
        if not is_pair_adjacent(
            self._track,
            self._transition.from_clip_id,
            self._transition.to_clip_id,
        ):
            raise ValueError("Transition clips must be adjacent on the same track")
        existing = transition_for_clip_pair(
            self._track,
            self._transition.from_clip_id,
            self._transition.to_clip_id,
        )
        if existing is not None:
            raise ValueError("A transition already exists for this clip pair")
