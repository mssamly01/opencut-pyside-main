from __future__ import annotations

from app.domain.commands.base_command import BaseCommand


class CommandManager:
    def __init__(self) -> None:
        self._undo_stack: list[BaseCommand] = []
        self._redo_stack: list[BaseCommand] = []

    def execute(self, command: BaseCommand) -> None:
        command.execute()
        self._undo_stack.append(command)
        self._redo_stack.clear()

    def undo(self) -> bool:
        if not self._undo_stack:
            return False

        command = self._undo_stack.pop()
        command.undo()
        self._redo_stack.append(command)
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False

        command = self._redo_stack.pop()
        command.execute()
        self._undo_stack.append(command)
        return True
