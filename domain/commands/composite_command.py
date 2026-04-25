from __future__ import annotations

from app.domain.commands.base_command import BaseCommand


class CompositeCommand(BaseCommand):
    def __init__(self, commands: list[BaseCommand]) -> None:
        self._commands = list(commands)
        self._executed_count = 0

    def execute(self) -> None:
        if self._executed_count > 0:
            for command in self._commands:
                command.execute()
            self._executed_count = len(self._commands)
            return

        for index, command in enumerate(self._commands):
            command.execute()
            self._executed_count = index + 1

    def undo(self) -> None:
        if self._executed_count <= 0:
            raise RuntimeError("Cannot undo before command execution")
        for command in reversed(self._commands[: self._executed_count]):
            command.undo()

