from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SelectionState:
    """Selection state for timeline clips.

    `selected_clip_ids` is the source of truth for multi-select.
    `selected_clip_id` remains as a backward-compatible proxy to the first id.
    """

    selected_clip_ids: list[str] = field(default_factory=list)

    @property
    def selected_clip_id(self) -> str | None:
        return self.selected_clip_ids[0] if self.selected_clip_ids else None

    @selected_clip_id.setter
    def selected_clip_id(self, clip_id: str | None) -> None:
        self.selected_clip_ids = [clip_id] if clip_id else []
