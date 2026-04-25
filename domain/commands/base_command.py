from __future__ import annotations

from abc import ABC, abstractmethod


class BaseCommand(ABC):
    @abstractmethod
    def execute(self) -> None:
        """Apply the command mutation."""

    @abstractmethod
    def undo(self) -> None:
        """Revert the command mutation."""
