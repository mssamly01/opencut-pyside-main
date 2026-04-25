from __future__ import annotations

import uuid
from dataclasses import dataclass

TRANSITION_TYPES = frozenset(
    {
        "cross_dissolve",
        "fade_to_black",
        "slide_left",
        "slide_right",
        "wipe_left",
        "wipe_right",
    }
)

DEFAULT_TRANSITION_DURATION = 0.5
MAX_TRANSITION_DURATION = 2.0


@dataclass(slots=True)
class Transition:
    transition_id: str
    transition_type: str
    duration_seconds: float
    from_clip_id: str
    to_clip_id: str

    def __post_init__(self) -> None:
        if self.transition_type not in TRANSITION_TYPES:
            raise ValueError(f"Invalid transition type '{self.transition_type}'")
        self.duration_seconds = max(
            0.05,
            min(MAX_TRANSITION_DURATION, float(self.duration_seconds)),
        )


def make_transition(
    transition_type: str,
    from_clip_id: str,
    to_clip_id: str,
    duration_seconds: float | None = None,
) -> Transition:
    return Transition(
        transition_id=f"trans_{uuid.uuid4().hex[:8]}",
        transition_type=transition_type,
        duration_seconds=(
            DEFAULT_TRANSITION_DURATION
            if duration_seconds is None
            else float(duration_seconds)
        ),
        from_clip_id=from_clip_id,
        to_clip_id=to_clip_id,
    )
