from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.controllers.app_controller import AppController
from app.infrastructure.logging_config import default_log_directory
from app.ui.app_shell import AppShell
from app.ui.dialogs.export_dialog import ExportDialog
from app.ui.shared.icons import build_icon
from app.ui.top_bar import TopBar
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    def __init__(self, app_controller: AppController) -> None:
        super().__init__()
        self._app_controller = app_controller
        self._export_action: QAction | None = None
        self._dirty_label: QLabel | None = None
        self._timecode_label: QLabel | None = None
        self._project_info_label: QLabel | None = None
        self._top_bar: TopBar | None = None

        self.setWindowTitle("OpenCut PySide")
        self.resize(1440, 860)

        self._top_bar = TopBar(self)
        self._top_bar.export_requested.connect(self._on_export_project_triggered)
        self._app_shell = AppShell(app_controller=self._app_controller)
        central = QWidget(self)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self._top_bar)
        central_layout.addWidget(self._app_shell, 1)
        self.setCentralWidget(central)

        self.menuBar().hide()
        self._build_top_bar_menu()
        self._build_main_toolbar()
        self._build_status_bar()

        self._app_controller.project_controller.project_changed.connect(self._refresh_window_title)
        self._app_controller.project_controller.project_changed.connect(self._refresh_status_bar)
        self._app_controller.dirty_state_changed.connect(self._refresh_window_title)
        self._app_controller.dirty_state_changed.connect(self._refresh_dirty_indicator)
        self._app_controller.timeline_controller.timeline_edited.connect(self._refresh_window_title)
        self._app_controller.timeline_controller.timeline_edited.connect(self._refresh_status_bar)
        self._app_controller.playback_controller.current_time_changed.connect(self._refresh_timecode)
        self._app_controller.export_controller.export_started.connect(self._on_export_started)
        self._app_controller.export_controller.export_progress_changed.connect(self._on_export_progress_changed)
        self._app_controller.export_controller.export_finished.connect(self._on_export_finished)
        self._app_controller.export_controller.export_failed.connect(self._on_export_failed)
        self._app_controller.export_controller.export_in_progress_changed.connect(self._on_export_in_progress_changed)
        self._app_controller.autosave_failed.connect(self._on_autosave_failed)

        self._refresh_window_title()
        self._refresh_status_bar()
        self._refresh_dirty_indicator()
        self._refresh_timecode(0.0)
        QTimer.singleShot(0, self._offer_autosave_recovery_on_startup)

    def _make_action(
        self,
        icon_name: str,
        text: str,
        callback: Callable[..., None],
        *,
        shortcut: QKeySequence | str | None = None,
        tooltip: str | None = None,
        checkable: bool = False,
    ) -> QAction:
        action = QAction(build_icon(icon_name), text, self)
        if shortcut is not None:
            action.setShortcut(shortcut if isinstance(shortcut, QKeySequence) else QKeySequence(shortcut))
        action.setToolTip(tooltip or text)
        action.setCheckable(checkable)
        if checkable:
            action.toggled.connect(callback)
        else:
            action.triggered.connect(lambda _checked=False: callback())
        return action

    def _build_top_bar_menu(self) -> None:
        if self._top_bar is None:
            return

        self._top_bar.clear_menu()

        self._export_action = self._make_action(
            "export",
            "Export MP4...",
            self._on_export_project_triggered,
            shortcut=QKeySequence("Ctrl+Shift+E"),
        )

        file_actions = [
            self._make_action(
                "new-file",
                "New Project",
                self._on_new_project_triggered,
                shortcut=QKeySequence.StandardKey.New,
            ),
            self._make_action(
                "file-open",
                "Open Project...",
                self._on_load_project_triggered,
                shortcut=QKeySequence.StandardKey.Open,
            ),
            self._make_action(
                "file-open",
                "Load Demo Project",
                self._on_load_demo_project_triggered,
                shortcut=QKeySequence("Ctrl+Shift+D"),
            ),
            self._make_action(
                "save",
                "Save",
                self._on_save_project_triggered,
                shortcut=QKeySequence.StandardKey.Save,
            ),
            self._make_action(
                "save-as",
                "Save As...",
                self._on_save_project_as_triggered,
                shortcut=QKeySequence("Ctrl+Shift+S"),
            ),
            self._make_action(
                "import-media",
                "Import Media...",
                self._on_import_media_triggered,
                shortcut=QKeySequence("Ctrl+I"),
            ),
            self._make_action(
                "import-subtitle",
                "Import Subtitle...",
                self._on_import_subtitle_triggered,
                shortcut=QKeySequence("Ctrl+Shift+I"),
            ),
            self._make_action(
                "export-subtitle",
                "Export Subtitle...",
                self._on_export_subtitle_triggered,
                shortcut=QKeySequence("Ctrl+Shift+U"),
            ),
            self._export_action,
            self._make_action("logs", "Open Logs Folder", self._on_open_logs_triggered),
            self._make_action(
                "delete",
                "Quit",
                self.close,
                shortcut=QKeySequence.StandardKey.Quit,
            ),
        ]

        edit_actions = [
            self._make_action(
                "undo",
                "Undo",
                self._on_undo_triggered,
                shortcut=QKeySequence.StandardKey.Undo,
            ),
            self._make_action(
                "redo",
                "Redo",
                self._on_redo_triggered,
                shortcut=QKeySequence.StandardKey.Redo,
            ),
            self._make_action(
                "cut",
                "Cut",
                self._on_cut_triggered,
                shortcut=QKeySequence.StandardKey.Cut,
            ),
            self._make_action(
                "copy",
                "Copy",
                self._on_copy_triggered,
                shortcut=QKeySequence.StandardKey.Copy,
            ),
            self._make_action(
                "paste",
                "Paste at Playhead",
                self._on_paste_triggered,
                shortcut=QKeySequence.StandardKey.Paste,
            ),
            self._make_action("split", "Split at Playhead", self._on_split_triggered, shortcut="S"),
            self._make_action(
                "duplicate",
                "Duplicate",
                self._on_duplicate_triggered,
                shortcut="Ctrl+D",
            ),
            self._make_action(
                "delete",
                "Delete",
                self._on_delete_triggered,
                shortcut="Delete",
            ),
        ]

        view_actions = [
            self._make_action(
                "zoom-in",
                "Zoom In Timeline",
                self._app_shell.timeline_view.zoom_in,
                shortcut="Ctrl+=",
            ),
            self._make_action(
                "zoom-out",
                "Zoom Out Timeline",
                self._app_shell.timeline_view.zoom_out,
                shortcut="Ctrl+-",
            ),
            self._make_action(
                "fit",
                "Fit Timeline",
                self._app_shell.timeline_view.fit_timeline,
                shortcut="Ctrl+0",
            ),
        ]

        for action in [*file_actions, *edit_actions, *view_actions]:
            self.addAction(action)

        self._top_bar.add_menu_section("File", file_actions)
        self._top_bar.add_menu_section("Edit", edit_actions)
        self._top_bar.add_menu_section("View", view_actions)

    def _build_main_toolbar(self) -> None:
        # Keep transport shortcuts available, but don't show the icon cluster on the main toolbar.
        self.addAction(
            self._make_action(
                "skip-back",
                "Start",
                self._on_playhead_start_triggered,
                shortcut="Ctrl+Home",
                tooltip="Go to Start (Ctrl+Home)",
            )
        )
        self.addAction(
            self._make_action(
                "step-back",
                "Prev Frame",
                self._on_prev_frame_triggered,
                shortcut="Alt+Left",
                tooltip="Previous Frame (Alt+Left)",
            )
        )
        self.addAction(
            self._make_action(
                "play",
                "Play/Pause",
                self._on_play_pause_toggled,
                shortcut="Space",
                tooltip="Play/Pause (Space)",
            )
        )
        self.addAction(
            self._make_action(
                "stop",
                "Stop",
                self._on_stop_triggered,
                shortcut="Shift+Space",
                tooltip="Stop (Shift+Space)",
            )
        )
        self.addAction(
            self._make_action(
                "step-forward",
                "Next Frame",
                self._on_next_frame_triggered,
                shortcut="Alt+Right",
                tooltip="Next Frame (Alt+Right)",
            )
        )

    def _build_status_bar(self) -> None:
        status_bar: QStatusBar = self.statusBar()
        status_bar.setObjectName("MainStatusBar")

        self._dirty_label = QLabel("", self)
        self._dirty_label.setObjectName("dirty_indicator")
        self._dirty_label.setMinimumWidth(14)

        self._project_info_label = QLabel("", self)

        self._timecode_label = QLabel("00:00:00.000", self)
        self._timecode_label.setObjectName("timecode_label")
        self._timecode_label.setMinimumWidth(120)

        status_bar.addWidget(self._dirty_label)
        status_bar.addWidget(self._project_info_label, 1)
        status_bar.addPermanentWidget(self._timecode_label)

    def _on_undo_triggered(self) -> None:
        self._app_controller.timeline_controller.undo()

    def _on_redo_triggered(self) -> None:
        self._app_controller.timeline_controller.redo()

    def _on_play_pause_toggled(self) -> None:
        self._app_controller.playback_controller.toggle_play_pause()

    def _on_stop_triggered(self) -> None:
        self._app_controller.playback_controller.stop()

    def _on_playhead_start_triggered(self) -> None:
        self._app_controller.playback_controller.seek_to_start()

    def _on_prev_frame_triggered(self) -> None:
        self._app_controller.playback_controller.nudge_frames(-1)

    def _on_next_frame_triggered(self) -> None:
        self._app_controller.playback_controller.nudge_frames(1)

    def _on_new_project_triggered(self) -> None:
        if not self._confirm_discard_unsaved_changes("create a new project"):
            return
        self._app_controller.load_empty_project()
        self._app_controller.playback_controller.stop()
        self.statusBar().showMessage("New project created.", 2500)

    def _on_load_demo_project_triggered(self) -> None:
        if not self._confirm_discard_unsaved_changes("load the demo project"):
            return
        self._app_controller.load_demo_project()
        self._app_controller.playback_controller.stop()
        self.statusBar().showMessage("Demo project loaded.", 2500)

    def _on_import_media_triggered(self) -> None:
        self._app_shell.media_panel.open_import_dialog()

    def _on_split_triggered(self) -> None:
        split_position = self._app_controller.playback_controller.current_time()
        self._app_controller.timeline_controller.split_selected_clip(round(split_position, 3))

    def _on_duplicate_triggered(self) -> None:
        self._app_controller.timeline_controller.duplicate_clip()

    def _on_delete_triggered(self) -> None:
        self._app_controller.timeline_controller.delete_selected_clip()

    def _on_copy_triggered(self) -> None:
        self._app_controller.timeline_controller.copy_clip_to_clipboard()

    def _on_cut_triggered(self) -> None:
        self._app_controller.timeline_controller.cut_clip_to_clipboard()

    def _on_paste_triggered(self) -> None:
        playhead = self._app_controller.playback_controller.current_time()
        self._app_controller.timeline_controller.paste_clipboard_at(float(playhead))

    def _on_open_logs_triggered(self) -> None:
        log_dir = default_log_directory()
        log_dir.mkdir(parents=True, exist_ok=True)
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir)))
        if not opened:
            QMessageBox.warning(self, "Open Logs", f"Could not open log folder:\n{log_dir}")

    def _on_import_subtitle_triggered(self) -> None:
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Subtitle",
            "",
            "Subtitle Files (*.srt *.vtt);;All Files (*.*)",
        )
        if not selected_path:
            return

        try:
            imported_count = self._app_controller.import_subtitles_from_file(selected_path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Import Subtitle Failed", str(exc))
            return

        if imported_count <= 0:
            QMessageBox.information(self, "Import Subtitle", "No subtitle segment was imported.")
            return

        self.statusBar().showMessage(f"Imported {imported_count} subtitle segment(s).", 4000)

    def _on_export_subtitle_triggered(self) -> None:
        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Subtitle",
            "",
            "SubRip Subtitle (*.srt);;All Files (*.*)",
        )
        if not selected_path:
            return

        if not selected_path.lower().endswith(".srt"):
            selected_path = f"{selected_path}.srt"

        try:
            exported_count = self._app_controller.export_subtitles_to_file(selected_path)
        except OSError as exc:
            QMessageBox.critical(self, "Export Subtitle Failed", str(exc))
            return

        if exported_count <= 0:
            QMessageBox.information(self, "Export Subtitle", "No subtitle clip to export.")
            return

        self.statusBar().showMessage(f"Exported {exported_count} subtitle segment(s).", 4000)

    def _on_load_project_triggered(self) -> None:
        last_project_path = self._app_controller.settings_service.last_opened_project_path()
        initial_directory = ""
        if last_project_path:
            initial_directory = str(Path(last_project_path).parent)

        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Project",
            initial_directory,
            "Project Files (*.json);;All Files (*.*)",
        )
        if not selected_path:
            return

        if not self._confirm_discard_unsaved_changes("load another project"):
            return

        try:
            self._app_controller.load_project_from_file(selected_path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Load Project Failed", str(exc))
            return

        self._app_controller.playback_controller.stop()
        self.statusBar().showMessage(f"Loaded project: {selected_path}", 3000)

    def _on_save_project_triggered(self) -> None:
        saved_path = self._save_current_project()
        if saved_path is None:
            return

        self.statusBar().showMessage(f"Saved project: {saved_path}", 3000)

    def _on_save_project_as_triggered(self) -> None:
        saved_path = self._save_current_project(force_prompt=True)
        if saved_path is None:
            return

        self.statusBar().showMessage(f"Saved project: {saved_path}", 3000)

    def _on_export_project_triggered(self) -> None:
        project = self._app_controller.project_controller.active_project()
        if project is None:
            QMessageBox.warning(self, "Export Project", "No active project to export.")
            return

        project_path = self._app_controller.project_controller.active_project_path()
        last_export_directory = self._app_controller.settings_service.last_export_directory()
        if project_path:
            default_directory = Path(project_path).parent
        elif last_export_directory:
            default_directory = Path(last_export_directory)
        else:
            default_directory = Path.cwd()
        default_name = self._safe_filename(project.name or "export")
        default_path = default_directory / f"{default_name}.mp4"

        dialog = ExportDialog(project=project, suggested_output_path=str(default_path), parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        output_path = dialog.output_path()
        if not output_path:
            return
        normalized_path = Path(output_path)
        if normalized_path.suffix.lower() != ".mp4":
            normalized_path = normalized_path.with_suffix(".mp4")

        try:
            self._app_controller.export_controller.export_active_project(
                str(normalized_path),
                options=dialog.export_options(),
            )
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))
            return

        self._app_controller.settings_service.record_export_output(str(normalized_path))

    def _prompt_save_path(self) -> str | None:
        last_project_path = self._app_controller.settings_service.last_opened_project_path()
        initial_directory = ""
        if last_project_path:
            initial_directory = str(Path(last_project_path).parent)

        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project",
            initial_directory,
            "Project Files (*.json);;All Files (*.*)",
        )
        if not selected_path:
            return None

        normalized_path = Path(selected_path)
        if normalized_path.suffix.lower() != ".json":
            normalized_path = normalized_path.with_suffix(".json")
        return str(normalized_path)

    @staticmethod
    def _safe_filename(name: str) -> str:
        cleaned_name = "".join(character if character not in '<>:"/\\|?*' else "_" for character in name).strip()
        return cleaned_name or "export"

    def _on_export_started(self, output_path: str) -> None:
        self.statusBar().showMessage(f"Exporting: {output_path}", 0)

    def _on_export_progress_changed(self, percent: float, message: str) -> None:
        progress_message = f"Exporting... {max(0.0, min(percent, 100.0)):.0f}%"
        if message:
            progress_message = f"{progress_message} - {message}"
        self.statusBar().showMessage(progress_message, 0)

    def _on_export_finished(self, export_result: object) -> None:
        output_path = getattr(export_result, "output_path", str(export_result))
        warnings = getattr(export_result, "warnings", [])
        if warnings:
            self.statusBar().showMessage(f"Exported: {output_path} ({len(warnings)} warning(s))", 5000)
            return

        self.statusBar().showMessage(f"Exported: {output_path}", 5000)

    def _on_export_failed(self, message: str) -> None:
        self.statusBar().showMessage(f"Export failed: {message}", 5000)
        QMessageBox.critical(self, "Export Failed", message)

    def _on_export_in_progress_changed(self, is_exporting: bool) -> None:
        if self._export_action is not None:
            self._export_action.setEnabled(not is_exporting)
        if self._top_bar is not None:
            self._top_bar.set_export_enabled(not is_exporting)

    def _refresh_status_bar(self, *_args: object) -> None:
        if self._project_info_label is None:
            return
        project = self._app_controller.project_controller.active_project()
        if project is None:
            self._project_info_label.setText("No project")
            return
        resolution = f"{project.width}x{project.height}"
        fps = f"{project.fps:g} fps"
        total_clips = sum(len(track.clips) for track in project.timeline.tracks)
        self._project_info_label.setText(
            f"{project.name or 'Untitled'}   |   {resolution}   |   {fps}   |   {total_clips} clip(s)"
        )

    def _refresh_dirty_indicator(self, *_args: object) -> None:
        if self._dirty_label is None:
            return
        if self._app_controller.has_unsaved_changes():
            self._dirty_label.setText("*")
            self._dirty_label.setToolTip("Unsaved changes")
        else:
            self._dirty_label.setText(" ")
            self._dirty_label.setToolTip("All changes saved")

    def _refresh_timecode(self, time_seconds: float) -> None:
        if self._timecode_label is None:
            return
        clamped = max(0.0, float(time_seconds))
        hours = int(clamped // 3600)
        minutes = int((clamped % 3600) // 60)
        seconds = int(clamped % 60)
        millis = int(round((clamped - int(clamped)) * 1000))
        if millis >= 1000:
            millis = 999
        self._timecode_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}")

    def _refresh_window_title(self, *_args: object) -> None:
        project = self._app_controller.project_controller.active_project()
        project_name = "Untitled"
        if project is not None and project.name:
            project_name = project.name

        is_dirty = self._app_controller.has_unsaved_changes()
        dirty_suffix = " *" if is_dirty else ""
        if self._top_bar is not None:
            self._top_bar.set_project_name(project_name, dirty=is_dirty)

        project_path = self._app_controller.project_controller.active_project_path()
        if project_path:
            self.setWindowTitle(f"OpenCut PySide - {project_name}{dirty_suffix} ({Path(project_path).name})")
            return

        self.setWindowTitle(f"OpenCut PySide - {project_name}{dirty_suffix}")

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._confirm_discard_unsaved_changes("close the app"):
            event.ignore()
            return

        event.accept()

    def _confirm_discard_unsaved_changes(self, action_description: str) -> bool:
        if not self._app_controller.has_unsaved_changes():
            return True

        response = QMessageBox.question(
            self,
            "Unsaved Changes",
            f"The current project has unsaved changes. Do you want to save before you {action_description}?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )

        if response == QMessageBox.StandardButton.Save:
            return self._save_current_project() is not None
        if response == QMessageBox.StandardButton.Discard:
            return True
        return False

    def _save_current_project(self, force_prompt: bool = False) -> str | None:
        project_controller = self._app_controller.project_controller
        target_path = None if force_prompt else project_controller.active_project_path()
        if target_path is None:
            target_path = self._prompt_save_path()
            if target_path is None:
                return None

        try:
            saved_path = self._app_controller.save_active_project(target_path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Save Project Failed", str(exc))
            return None

        if saved_path is None:
            QMessageBox.warning(self, "Save Project", "No active project to save.")
            return None

        return saved_path

    def _offer_autosave_recovery_on_startup(self) -> None:
        app = QApplication.instance()
        if app is not None and app.platformName().lower() == "offscreen":
            return

        if not self._app_controller.has_recoverable_autosave():
            return

        response = QMessageBox.question(
            self,
            "Recover Autosave",
            "A recoverable autosave snapshot was found.\n\n"
            "Would you like to recover it?\n\n"
            f"{self._app_controller.autosave_summary()}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if response == QMessageBox.StandardButton.Yes:
            recovered = self._app_controller.recover_from_autosave()
            if recovered:
                self.statusBar().showMessage("Recovered project from autosave.", 4000)
            else:
                QMessageBox.warning(self, "Recover Autosave", "Unable to recover autosave snapshot.")
            return

        self._app_controller.discard_autosave_snapshot()

    def _on_autosave_failed(self, message: str) -> None:
        self.statusBar().showMessage(f"Autosave failed: {message}", 5000)
