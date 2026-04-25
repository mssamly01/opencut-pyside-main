from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.track import Track


@dataclass(slots=True)
class Timeline:
    tracks: list[Track] = field(default_factory=list)

    def total_duration(self) -> float:
        max_end = 0.0
        for track in self.tracks:
            for clip in track.clips:
                max_end = max(max_end, clip.timeline_end)
        return max_end
