from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.controllers.export_controller import ExportController
from app.controllers.inspector_controller import InspectorController
from app.controllers.playback_controller import PlaybackController
from app.controllers.project_controller import ProjectController
from app.controllers.selection_controller import SelectionController
from app.controllers.timeline_controller import TimelineController
from app.services.autosave_service import AutosaveService
from app.services.caption_service import CaptionService
from app.services.export_service import ExportService
from app.services.media_service import MediaService
from app.services.playback_service import PlaybackService
from app.services.project_service import ProjectService
from app.services.settings_service import SettingsService
from app.services.thumbnail_service import ThumbnailService
from app.services.waveform_loader import WaveformLoader
from app.services.waveform_service import WaveformService
from PySide6.QtCore import QObject, QTimer, Signal


@dataclass(slots=True, frozen=True)
class SubtitleSegmentSelection:
    entry_id: str
    source_name: str
    source_path: str
    segment_index: int
    start_seconds: float
    end_seconds: float
    text: str


@dataclass(slots=True)
class SubtitleLibraryEntry:
    entry_id: str
    source_path: str
    source_name: str
    segments: list[tuple[float, float, str]]


class AppController(QObject):
    """Top-level coordinator between UI and feature controllers."""

    app_ready = Signal()
    autosave_completed = Signal(str)
    autosave_failed = Signal(str)
    dirty_state_changed = Signal(bool)
    subtitle_library_changed = Signal()
    subtitle_selection_changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._has_unsaved_changes = False
        self.media_service = MediaService()
        self.caption_service = CaptionService()
        self.playback_service = PlaybackService()
        self.project_service = ProjectService()
        self.export_service = ExportService()
        self.thumbnail_service = ThumbnailService()
        self.waveform_service = WaveformService()
        self.waveform_loader = WaveformLoader(self.waveform_service, self)
        self.settings_service = SettingsService()
        self.autosave_service = AutosaveService(project_service=self.project_service)
        self._subtitle_library: list[SubtitleLibraryEntry] = []
        self._selected_subtitle: SubtitleSegmentSelection | None = None
        self.project_controller = ProjectController(
            self,
            media_service=self.media_service,
            project_service=self.project_service,
        )
        self.selection_controller = SelectionController(self)
        self.timeline_controller = TimelineController(
            self.project_controller,
            self.selection_controller,
            self,
        )
        self.playback_controller = PlaybackController(
            self.project_controller,
            playback_service=self.playback_service,
            parent=self,
        )

        self._autosave_edit_timer = QTimer(self)
        self._autosave_edit_timer.setSingleShot(True)
        self._autosave_edit_timer.setInterval(1500)
        self._autosave_edit_timer.timeout.connect(self._perform_autosave)

        self._autosave_periodic_timer = QTimer(self)
        self._autosave_periodic_timer.setInterval(120000)
        self._autosave_periodic_timer.timeout.connect(self._on_periodic_autosave_timeout)

        self.inspector_controller = InspectorController(self)
        self.export_controller = ExportController(
            self.project_controller,
            self.export_service,
            self,
        )
        self.project_controller.project_changed.connect(self.selection_controller.clear_selection)
        self.project_controller.project_changed.connect(self._on_project_changed_for_autosave)
        self.project_controller.project_changed.connect(self._on_project_changed_for_subtitles)
        self.project_controller.project_modified.connect(self.mark_dirty)
        self.project_controller.project_modified.connect(self._on_project_modified_for_autosave)
        self.timeline_controller.timeline_edited.connect(self._on_timeline_edited_for_autosave)
        self.timeline_controller.timeline_edited.connect(self.mark_dirty)
        self.selection_controller.selection_changed.connect(self._on_timeline_selection_changed)
        self.timeline_controller.timeline_changed.connect(self.playback_controller.refresh_preview_frame)
        self.load_empty_project()
        self._autosave_periodic_timer.start()

    def has_recoverable_autosave(self) -> bool:
        return self.autosave_service.has_autosave_snapshot()

    def has_unsaved_changes(self) -> bool:
        return self._has_unsaved_changes

    def autosave_summary(self) -> str:
        snapshot_path = self.autosave_service.autosave_path()
        modified_at = self.autosave_service.snapshot_modified_at()
        if modified_at is None:
            return snapshot_path
        formatted_time = modified_at.strftime("%Y-%m-%d %H:%M:%S")
        return f"{snapshot_path}\nLast autosave: {formatted_time}"

    def recover_from_autosave(self) -> bool:
        if not self.autosave_service.has_autosave_snapshot():
            return False

        try:
            recovered_project = self.autosave_service.load_snapshot()
        except (OSError, ValueError) as exc:
            self.autosave_failed.emit(str(exc))
            return False

        self.project_controller.set_active_project(recovered_project, project_path=None)
        self.playback_controller.stop()
        self.autosave_service.discard_snapshot()
        self.mark_clean()
        return True

    def load_empty_project(self) -> None:
        self.project_controller.load_empty_project()
        self.mark_clean()

    def load_demo_project(self) -> None:
        self.project_controller.load_demo_project()
        self.mark_clean()

    def load_project_from_file(self, file_path: str) -> None:
        self.project_controller.load_project_from_file(file_path)
        self.settings_service.record_project_opened(file_path)
        self.autosave_service.discard_snapshot()
        self.mark_clean()

    def save_active_project(self, file_path: str | None = None) -> str | None:
        saved_path = self.project_controller.save_active_project(file_path)
        if saved_path is not None:
            self.settings_service.record_project_saved(saved_path)
            self.note_manual_project_saved()
        return saved_path

    def import_subtitles_from_file(self, file_path: str) -> int:
        caption_segments = self.caption_service.parse_file(file_path)
        if not caption_segments:
            return 0

        normalized_source_path = str(Path(file_path).expanduser().resolve())
        source_name = Path(normalized_source_path).name
        stored_segments = [
            (float(segment.start_seconds), float(segment.end_seconds), (segment.text or "").strip())
            for segment in caption_segments
            if (segment.text or "").strip() and float(segment.end_seconds) > float(segment.start_seconds)
        ]
        if not stored_segments:
            return 0

        existing_entry = next(
            (entry for entry in self._subtitle_library if entry.source_path == normalized_source_path),
            None,
        )
        if existing_entry is not None:
            existing_entry.segments = stored_segments
            existing_entry.source_name = source_name
            entry_id = existing_entry.entry_id
        else:
            entry_id = f"subtitle_{len(self._subtitle_library) + 1:03d}"
            self._subtitle_library.append(
                SubtitleLibraryEntry(
                    entry_id=entry_id,
                    source_path=normalized_source_path,
                    source_name=source_name,
                    segments=stored_segments,
                )
            )
        self.subtitle_library_changed.emit()

        if stored_segments:
            start, end, text = stored_segments[0]
            self._set_selected_subtitle(
                SubtitleSegmentSelection(
                    entry_id=entry_id,
                    source_name=source_name,
                    source_path=normalized_source_path,
                    segment_index=0,
                    start_seconds=start,
                    end_seconds=end,
                    text=text,
                )
            )
        return len(stored_segments)

    def subtitle_library_entries(self) -> tuple[SubtitleLibraryEntry, ...]:
        return tuple(self._subtitle_library)

    def selected_subtitle_segment(self) -> SubtitleSegmentSelection | None:
        return self._selected_subtitle

    def select_subtitle_segment(self, entry_id: str | None, segment_index: int | None = None) -> None:
        if entry_id is None or segment_index is None:
            self._set_selected_subtitle(None)
            return

        entry = next((item for item in self._subtitle_library if item.entry_id == entry_id), None)
        if entry is None:
            self._set_selected_subtitle(None)
            return
        if segment_index < 0 or segment_index >= len(entry.segments):
            self._set_selected_subtitle(None)
            return
        start, end, text = entry.segments[segment_index]
        self._set_selected_subtitle(
            SubtitleSegmentSelection(
                entry_id=entry.entry_id,
                source_name=entry.source_name,
                source_path=entry.source_path,
                segment_index=segment_index,
                start_seconds=start,
                end_seconds=end,
                text=text,
            )
        )

    def load_subtitle_entry_to_timeline(
        self,
        entry_id: str,
        timeline_offset_seconds: float | None = None,
    ) -> int:
        entry = next((item for item in self._subtitle_library if item.entry_id == entry_id), None)
        if entry is None or not entry.segments:
            return 0
        imported_count = self.timeline_controller.add_caption_segments(
            segments=entry.segments,
            timeline_offset_seconds=timeline_offset_seconds,
        )
        if imported_count > 0:
            self._set_selected_subtitle(None)
        return imported_count

    def remove_subtitle_entry(self, entry_id: str) -> bool:
        for index, entry in enumerate(self._subtitle_library):
            if entry.entry_id != entry_id:
                continue
            del self._subtitle_library[index]
            if self._selected_subtitle is not None and self._selected_subtitle.entry_id == entry_id:
                self._set_selected_subtitle(None)
            self.subtitle_library_changed.emit()
            return True
        return False

    def export_subtitles_to_file(self, file_path: str) -> int:
        from app.domain.clips.text_clip import TextClip
        from app.services.caption_service import CaptionSegment

        project = self.project_controller.active_project()
        if project is None:
            return 0

        segments: list[CaptionSegment] = []
        for track in project.timeline.tracks:
            if track.track_type.lower() != "text":
                continue
            for clip in track.sorted_clips():
                if not isinstance(clip, TextClip):
                    continue
                text = (clip.content or "").strip()
                if not text:
                    continue
                start = max(0.0, clip.timeline_start)
                end = start + max(0.001, clip.duration)
                segments.append(
                    CaptionSegment(
                        start_seconds=start,
                        end_seconds=end,
                        text=text,
                    )
                )

        if not segments:
            return 0

        return self.caption_service.write_srt(file_path, segments)

    def discard_autosave_snapshot(self) -> None:
        try:
            self.autosave_service.discard_snapshot()
        except OSError as exc:
            self.autosave_failed.emit(str(exc))

    def note_manual_project_saved(self) -> None:
        self.mark_clean()
        self.discard_autosave_snapshot()

    def mark_dirty(self) -> None:
        if self._has_unsaved_changes:
            return
        self._has_unsaved_changes = True
        self.dirty_state_changed.emit(True)

    def mark_clean(self) -> None:
        if not self._has_unsaved_changes:
            return
        self._has_unsaved_changes = False
        self.dirty_state_changed.emit(False)

    def _on_timeline_edited_for_autosave(self) -> None:
        self._autosave_edit_timer.start()

    def _on_project_changed_for_autosave(self) -> None:
        self._autosave_edit_timer.stop()

    def _on_project_changed_for_subtitles(self) -> None:
        if self._subtitle_library:
            self._subtitle_library = []
            self.subtitle_library_changed.emit()
        self._set_selected_subtitle(None)

    def _on_project_modified_for_autosave(self) -> None:
        self._autosave_edit_timer.start()

    def _on_periodic_autosave_timeout(self) -> None:
        self._perform_autosave()

    def _perform_autosave(self) -> None:
        project = self.project_controller.active_project()
        if project is None:
            return

        try:
            autosave_path = self.autosave_service.save_snapshot(project)
        except (OSError, ValueError) as exc:
            self.autosave_failed.emit(str(exc))
            return
        self.autosave_completed.emit(autosave_path)

    def _on_timeline_selection_changed(self) -> None:
        if self.selection_controller.selected_clip_id() is None:
            return
        self._set_selected_subtitle(None)

    def _set_selected_subtitle(self, selection: SubtitleSegmentSelection | None) -> None:
        if selection == self._selected_subtitle:
            return
        self._selected_subtitle = selection
        self.subtitle_selection_changed.emit()
