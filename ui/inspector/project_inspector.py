from __future__ import annotations

from app.domain.project import Project
from app.ui.inspector._inspector_base import CommandAwareInspector, block_signals
from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QLineEdit, QSpinBox


class ProjectInspector(CommandAwareInspector):
    def __init__(self, timeline_controller: object, parent=None) -> None:
        super().__init__(timeline_controller, parent)
        self._project: Project | None = None

        layout = QFormLayout(self)

        self._name_edit = QLineEdit(self)
        self._name_edit.editingFinished.connect(self._commit_name)
        layout.addRow("Project Name", self._name_edit)

        self._width_spin = QSpinBox(self)
        self._width_spin.setRange(1, 16384)
        self._width_spin.setKeyboardTracking(False)
        self._width_spin.editingFinished.connect(self._commit_dimensions)
        layout.addRow("Width", self._width_spin)

        self._height_spin = QSpinBox(self)
        self._height_spin.setRange(1, 16384)
        self._height_spin.setKeyboardTracking(False)
        self._height_spin.editingFinished.connect(self._commit_dimensions)
        layout.addRow("Height", self._height_spin)

        self._fps_spin = QDoubleSpinBox(self)
        self._fps_spin.setRange(1.0, 240.0)
        self._fps_spin.setDecimals(2)
        self._fps_spin.setSingleStep(1.0)
        self._fps_spin.setKeyboardTracking(False)
        self._fps_spin.editingFinished.connect(self._commit_fps)
        layout.addRow("FPS", self._fps_spin)

    def set_project(self, project: Project | None) -> None:
        self._project = project
        self.refresh_from_project()

    def refresh_from_project(self) -> None:
        project = self._project
        with block_signals(self._name_edit, self._width_spin, self._height_spin, self._fps_spin):
            if project is None:
                self.setEnabled(False)
                self._name_edit.setText("")
                self._width_spin.setValue(1)
                self._height_spin.setValue(1)
                self._fps_spin.setValue(30.0)
                return

            self.setEnabled(True)
            self._name_edit.setText(project.name)
            self._width_spin.setValue(project.width)
            self._height_spin.setValue(project.height)
            self._fps_spin.setValue(project.fps)

    def _commit_name(self) -> None:
        project = self._project
        if project is None:
            return

        new_name = self._name_edit.text().strip() or project.name
        self._apply_property_update(project, "name", new_name)

    def _commit_dimensions(self) -> None:
        project = self._project
        if project is None:
            return

        self._apply_property_update(project, "width", int(self._width_spin.value()))
        self._apply_property_update(project, "height", int(self._height_spin.value()))

    def _commit_fps(self) -> None:
        project = self._project
        if project is None:
            return

        self._apply_property_update(project, "fps", float(self._fps_spin.value()))
