from __future__ import annotations

from pathlib import Path

from app.domain.project import Project
from app.dto.export_dto import ExportOptions
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class ExportDialog(QDialog):
    def __init__(
        self,
        project: Project,
        suggested_output_path: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._project = project
        self.setWindowTitle("Export Video")
        self.setModal(True)
        self.resize(520, 420)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        info = QLabel(
            f"Project: {project.name}  |  Base: {project.width}x{project.height} @ {project.fps:g} fps",
            self,
        )
        info.setWordWrap(True)
        root.addWidget(info)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(8)

        output_row = QHBoxLayout()
        self._output_edit = QLineEdit(suggested_output_path, self)
        browse_button = QPushButton("Browse...", self)
        browse_button.clicked.connect(self._browse_output_path)
        output_row.addWidget(self._output_edit, 1)
        output_row.addWidget(browse_button)
        output_container = QWidget(self)
        output_container.setLayout(output_row)
        form.addRow("Output", output_container)

        self._in_spin = QDoubleSpinBox(self)
        self._in_spin.setRange(0.0, max(0.0, project.timeline.total_duration()))
        self._in_spin.setDecimals(3)
        self._in_spin.setSingleStep(0.1)
        form.addRow("In (s)", self._in_spin)

        self._out_enabled = QCheckBox("Use Out point", self)
        self._out_enabled.toggled.connect(self._sync_out_enabled)
        self._out_spin = QDoubleSpinBox(self)
        self._out_spin.setRange(0.0, max(0.0, project.timeline.total_duration()))
        self._out_spin.setDecimals(3)
        self._out_spin.setSingleStep(0.1)
        self._out_spin.setValue(max(0.0, project.timeline.total_duration()))
        self._out_spin.setEnabled(False)
        out_row = QHBoxLayout()
        out_row.addWidget(self._out_enabled)
        out_row.addWidget(self._out_spin, 1)
        out_container = QWidget(self)
        out_container.setLayout(out_row)
        form.addRow("Out (s)", out_container)

        self._resolution_enabled = QCheckBox("Override resolution", self)
        self._resolution_enabled.toggled.connect(self._sync_resolution_enabled)
        self._width_spin = QSpinBox(self)
        self._width_spin.setRange(16, 16384)
        self._width_spin.setValue(project.width)
        self._width_spin.setEnabled(False)
        self._height_spin = QSpinBox(self)
        self._height_spin.setRange(16, 16384)
        self._height_spin.setValue(project.height)
        self._height_spin.setEnabled(False)
        resolution_row = QHBoxLayout()
        resolution_row.addWidget(self._resolution_enabled)
        resolution_row.addWidget(self._width_spin)
        resolution_row.addWidget(QLabel("x", self))
        resolution_row.addWidget(self._height_spin)
        resolution_container = QWidget(self)
        resolution_container.setLayout(resolution_row)
        form.addRow("Resolution", resolution_container)

        self._fps_enabled = QCheckBox("Override FPS", self)
        self._fps_enabled.toggled.connect(self._sync_fps_enabled)
        self._fps_spin = QDoubleSpinBox(self)
        self._fps_spin.setRange(1.0, 240.0)
        self._fps_spin.setDecimals(2)
        self._fps_spin.setSingleStep(1.0)
        self._fps_spin.setValue(project.fps)
        self._fps_spin.setEnabled(False)
        fps_row = QHBoxLayout()
        fps_row.addWidget(self._fps_enabled)
        fps_row.addWidget(self._fps_spin, 1)
        fps_container = QWidget(self)
        fps_container.setLayout(fps_row)
        form.addRow("FPS", fps_container)

        self._codec_combo = QComboBox(self)
        self._codec_combo.addItem("H.264 (libx264)", "libx264")
        self._codec_combo.addItem("H.265 (libx265)", "libx265")
        self._codec_combo.addItem("VP9 (libvpx-vp9)", "libvpx-vp9")
        form.addRow("Codec", self._codec_combo)

        self._preset_combo = QComboBox(self)
        for preset in ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"):
            self._preset_combo.addItem(preset, preset)
        self._preset_combo.setCurrentText("veryfast")
        form.addRow("Preset", self._preset_combo)

        self._crf_spin = QSpinBox(self)
        self._crf_spin.setRange(0, 63)
        self._crf_spin.setValue(23)
        form.addRow("CRF", self._crf_spin)

        root.addLayout(form)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self._buttons.accepted.connect(self._on_accept)
        self._buttons.rejected.connect(self.reject)
        root.addWidget(self._buttons)

    def output_path(self) -> str:
        output = self._output_edit.text().strip()
        if not output:
            return ""
        normalized = Path(output)
        if normalized.suffix.lower() != ".mp4":
            normalized = normalized.with_suffix(".mp4")
        return str(normalized)

    def export_options(self) -> ExportOptions:
        return ExportOptions(
            in_point_seconds=float(self._in_spin.value()) if self._in_spin.value() > 0.0 else None,
            out_point_seconds=float(self._out_spin.value()) if self._out_enabled.isChecked() else None,
            width_override=int(self._width_spin.value()) if self._resolution_enabled.isChecked() else None,
            height_override=int(self._height_spin.value()) if self._resolution_enabled.isChecked() else None,
            fps_override=float(self._fps_spin.value()) if self._fps_enabled.isChecked() else None,
            codec=str(self._codec_combo.currentData() or "libx264"),
            preset=str(self._preset_combo.currentData() or "veryfast"),
            crf=int(self._crf_spin.value()),
        )

    def _browse_output_path(self) -> None:
        initial = self.output_path() or str(Path.cwd() / "export.mp4")
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Export MP4",
            initial,
            "MP4 Video (*.mp4);;All Files (*.*)",
        )
        if selected:
            self._output_edit.setText(selected)

    def _sync_out_enabled(self, enabled: bool) -> None:
        self._out_spin.setEnabled(enabled)

    def _sync_resolution_enabled(self, enabled: bool) -> None:
        self._width_spin.setEnabled(enabled)
        self._height_spin.setEnabled(enabled)

    def _sync_fps_enabled(self, enabled: bool) -> None:
        self._fps_spin.setEnabled(enabled)

    def _on_accept(self) -> None:
        output = self.output_path()
        if not output:
            QMessageBox.warning(self, "Export", "Please choose an output path.")
            return
        if self._out_enabled.isChecked() and self._out_spin.value() <= self._in_spin.value():
            QMessageBox.warning(self, "Export", "Out point must be greater than In point.")
            return
        self.accept()
