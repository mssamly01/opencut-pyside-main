from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class WordTiming:
    start_seconds: float
    end_seconds: float
    text: str
