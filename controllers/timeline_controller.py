from __future__ import annotations

from copy import deepcopy
from typing import Literal
from uuid import uuid4

from app.controllers.project_controller import ProjectController
from app.controllers.selection_controller import SelectionController
from app.domain.clips.audio_clip import AudioClip
from app.domain.clips.base_clip import BaseClip
from app.domain.clips.image_clip import ImageClip
from app.domain.clips.text_clip import TextClip
from app.domain.clips.video_clip import VideoClip
from app.domain.commands import (
    AddClipCommand,
    AddKeyframeCommand,
    AddTrackCommand,
    AddTransitionCommand,
    ChangeTransitionTypeCommand,
    CommandManager,
    CompositeCommand,
    DeleteClipCommand,
    MoveClipCommand,
    MoveClipToTrackCommand,
    MoveKeyframeCommand,
    RemoveKeyframeCommand,
    RemoveTrackCommand,
    RemoveTransitionCommand,
    SetKeyframeInterpolationCommand,
    SplitClipCommand,
    TrimClipCommand,
    UpdateKeyframeBezierCommand,
    UpdateKeyframeValueCommand,
    UpdatePropertyCommand,
    UpdateTransitionDurationCommand,
)
from app.domain.commands.base_command import BaseCommand
from app.domain.keyframe import Keyframe
from app.domain.media_asset import MediaAsset
from app.domain.project import Project
from app.domain.snap_engine import SnapEngine
from app.domain.timeline import Timeline
from app.domain.track import Track
from app.domain.transition import make_transition
from app.services.transition_service import (
    is_pair_adjacent,
    max_transition_duration,
)
from PySide6.QtCore import QObject, Signal


class TimelineController(QObject):
    timeline_changed = Signal()
    timeline_edited = Signal()

    def __init__(
        self,
        project_controller: ProjectController,
        selection_controller: SelectionController,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._project_controller = project_controller
        self._selection_controller = selection_controller
        self._command_manager = CommandManager()

        self._pixels_per_second = 90.0
        self._snap_threshold_pixels = 10.0
        self._snapping_enabled = True
        self._ripple_edit_enabled = False
        self._playhead_seconds = 3.5
        self._minimum_clip_duration_seconds = 16.0 / self._pixels_per_second
        self._clipboard_clip: BaseClip | None = None
        self._auto_keyframe_enabled = False

        self._min_pps = 10.0
        self._max_pps = 2000.0
        self._zoom_factor = 1.2

        self._project_controller.project_changed.connect(self._on_project_changed)

    @property
    def pixels_per_second(self) -> float:
        return self._pixels_per_second

    def snapping_enabled(self) -> bool:
        return self._snapping_enabled

    def set_snapping_enabled(self, enabled: bool) -> None:
        normalized_enabled = bool(enabled)
        if normalized_enabled == self._snapping_enabled:
            return
        self._snapping_enabled = normalized_enabled
        self.timeline_changed.emit()

    def ripple_edit_enabled(self) -> bool:
        return self._ripple_edit_enabled

    def set_ripple_edit_enabled(self, enabled: bool) -> None:
        normalized_enabled = bool(enabled)
        if normalized_enabled == self._ripple_edit_enabled:
            return
        self._ripple_edit_enabled = normalized_enabled
        self.timeline_changed.emit()

    def auto_keyframe_enabled(self) -> bool:
        return self._auto_keyframe_enabled

    def set_auto_keyframe_enabled(self, enabled: bool) -> None:
        normalized = bool(enabled)
        if normalized == self._auto_keyframe_enabled:
            return
        self._auto_keyframe_enabled = normalized
        self.timeline_changed.emit()

    def set_pixels_per_second(self, pps: float) -> None:
        new_pps = max(self._min_pps, min(pps, self._max_pps))
        if abs(new_pps - self._pixels_per_second) < 1e-6:
            return

        self._pixels_per_second = new_pps
        # Keep 16px minimum width for clips visually
        self._minimum_clip_duration_seconds = 16.0 / self._pixels_per_second
        self.timeline_changed.emit()

    def zoom_in(self) -> None:
        self.set_pixels_per_second(self._pixels_per_second * self._zoom_factor)

    def zoom_out(self) -> None:
        self.set_pixels_per_second(self._pixels_per_second / self._zoom_factor)

    def get_snap_position(
        self,
        clip_id: str,
        proposed_start: float,
        proposed_duration: float,
        drag_mode: Literal["move", "trim_left", "trim_right"],
    ) -> tuple[float, float, float | None]:
        """
        Returns (snapped_start, snapped_duration, snap_target_time).
        snap_target_time is None if no snapping occurred.
        """
        timeline = self.active_timeline()
        if timeline is None:
            return proposed_start, proposed_duration, None
        if not self._snapping_enabled:
            return proposed_start, proposed_duration, None

        clip = self._find_clip(timeline, clip_id)
        threshold_seconds = self._snap_threshold_seconds()
        targets = self._collect_snap_targets(timeline=timeline, exclude_clip_id=clip.clip_id)

        if drag_mode == "move":
            snap_delta = SnapEngine.best_move_delta(
                start=proposed_start,
                duration=proposed_duration,
                targets=targets,
                threshold=threshold_seconds,
            )
            if snap_delta is not None:
                snapped_start = max(0.0, proposed_start + snap_delta)
                snapped_end = snapped_start + proposed_duration
                for target in targets:
                    if abs(snapped_start - target) < 1e-6 or abs(snapped_end - target) < 1e-6:
                        return snapped_start, proposed_duration, target
            return proposed_start, proposed_duration, None

        if drag_mode == "trim_left":
            snapped_start = SnapEngine.snap_value(proposed_start, targets, threshold_seconds)
            if snapped_start is not None:
                right_edge = clip.timeline_end
                max_left = right_edge - self._minimum_clip_duration_seconds
                final_left = min(max(snapped_start, 0.0), max_left)
                return final_left, right_edge - final_left, snapped_start
            return proposed_start, proposed_duration, None

        if drag_mode == "trim_right":
            proposed_right = proposed_start + proposed_duration
            snapped_right = SnapEngine.snap_value(proposed_right, targets, threshold_seconds)
            if snapped_right is not None:
                min_right = clip.timeline_start + self._minimum_clip_duration_seconds
                final_right = max(snapped_right, min_right)
                return clip.timeline_start, final_right - clip.timeline_start, snapped_right
            return proposed_start, proposed_duration, None

        return proposed_start, proposed_duration, None

    def configure_timeline_metrics(
        self,
        pixels_per_second: float,
        snap_threshold_pixels: float,
        playhead_seconds: float,
        minimum_clip_duration_seconds: float,
    ) -> None:
        if pixels_per_second <= 0:
            raise ValueError("pixels_per_second must be > 0")
        if snap_threshold_pixels < 0:
            raise ValueError("snap_threshold_pixels must be >= 0")
        if minimum_clip_duration_seconds <= 0:
            raise ValueError("minimum_clip_duration_seconds must be > 0")

        self._pixels_per_second = pixels_per_second
        self._snap_threshold_pixels = snap_threshold_pixels
        self._playhead_seconds = max(0.0, playhead_seconds)
        self._minimum_clip_duration_seconds = minimum_clip_duration_seconds

    def set_playhead_seconds(self, playhead_seconds: float) -> None:
        self._playhead_seconds = max(0.0, playhead_seconds)

    def active_project(self) -> Project | None:
        return self._project_controller.active_project()

    def active_project_path(self) -> str | None:
        return self._project_controller.active_project_path()

    def active_timeline(self) -> Timeline | None:
        active_project = self.active_project()
        if active_project is None:
            return None
        return active_project.timeline

    def add_clip_from_media(
        self,
        media_id: str,
        timeline_start: float,
        preferred_track_id: str | None = None,
    ) -> str | None:
        project = self.active_project()
        timeline = self.active_timeline()
        if project is None or timeline is None:
            return None

        self._ensure_main_track_layout(timeline)
        media_asset = self._find_media_asset(project, media_id)
        normalized_start = max(0.0, timeline_start)
        target_track = self._select_target_track(timeline, media_asset.media_type, preferred_track_id)
        if target_track is None or target_track.is_locked:
            return None

        clip = self._build_clip_from_media(media_asset, target_track.track_id, normalized_start)
        destination_track = self._find_track_for_non_overlapping_placement(
            timeline=timeline,
            clip=clip,
            proposed_start=normalized_start,
            preferred_track_id=target_track.track_id,
            allow_create_track=True,
        )
        if destination_track is None:
            return None
        clip.track_id = destination_track.track_id

        self.execute_command(
            AddClipCommand(
                timeline=timeline,
                track_id=destination_track.track_id,
                clip=clip,
            )
        )
        return clip.clip_id

    def move_clip(self, clip_id: str, new_timeline_start: float) -> bool:
        timeline = self.active_timeline()
        if timeline is None:
            return False

        self._ensure_main_track_layout(timeline)
        track, clip = self._find_clip_with_track(timeline, clip_id)
        if self._is_clip_locked(track, clip):
            return False
        snapped_start = self._apply_move_snapping(
            timeline=timeline,
            clip=clip,
            proposed_start=max(0.0, new_timeline_start),
        )
        destination_track = self._find_track_for_non_overlapping_placement(
            timeline=timeline,
            clip=clip,
            proposed_start=snapped_start,
            preferred_track_id=track.track_id,
            allow_create_track=True,
            exclude_clip_id=clip_id,
        )
        if destination_track is None:
            return False

        commands: list[BaseCommand] = [
            MoveClipCommand(
                timeline=timeline,
                clip_id=clip_id,
                new_timeline_start=snapped_start,
            )
        ]
        if destination_track.track_id != track.track_id:
            commands.append(
                MoveClipToTrackCommand(
                    timeline=timeline,
                    clip_id=clip_id,
                    target_track_id=destination_track.track_id,
                )
            )

        if len(commands) == 1:
            self.execute_command(commands[0])
        else:
            self.execute_command(CompositeCommand(commands))
        return True

    def trim_clip(
        self,
        clip_id: str,
        new_timeline_start: float,
        new_duration: float,
        trim_side: Literal["left", "right"] | None = None,
    ) -> bool:
        timeline = self.active_timeline()
        if timeline is None:
            return False

        self._ensure_main_track_layout(timeline)
        track, clip = self._find_clip_with_track(timeline, clip_id)
        if self._is_clip_locked(track, clip):
            return False

        snapped_start, snapped_duration = self._apply_trim_snapping(
            timeline=timeline,
            clip=clip,
            proposed_start=max(0.0, new_timeline_start),
            proposed_duration=max(new_duration, self._minimum_clip_duration_seconds),
            trim_side=trim_side,
        )
        destination_track = self._find_track_for_non_overlapping_placement(
            timeline=timeline,
            clip=clip,
            proposed_start=snapped_start,
            preferred_track_id=track.track_id,
            allow_create_track=True,
            exclude_clip_id=clip_id,
            proposed_duration=snapped_duration,
        )
        if destination_track is None:
            return False

        commands: list[BaseCommand] = [
            TrimClipCommand(
                timeline=timeline,
                clip_id=clip_id,
                new_timeline_start=snapped_start,
                new_duration=snapped_duration,
            )
        ]
        if destination_track.track_id != track.track_id:
            commands.append(
                MoveClipToTrackCommand(
                    timeline=timeline,
                    clip_id=clip_id,
                    target_track_id=destination_track.track_id,
                )
            )

        if len(commands) == 1:
            self.execute_command(commands[0])
        else:
            self.execute_command(CompositeCommand(commands))
        return True

    def split_clip(self, clip_id: str, split_timeline_position: float) -> tuple[str, str] | None:
        timeline = self.active_timeline()
        if timeline is None:
            return None

        track, clip = self._find_clip_with_track(timeline, clip_id)
        if self._is_clip_locked(track, clip):
            return None

        command = SplitClipCommand(
            timeline=timeline,
            clip_id=clip_id,
            split_timeline_position=split_timeline_position,
        )
        self._command_manager.execute(command)
        self.timeline_changed.emit()
        self.timeline_edited.emit()
        return (command.left_clip_id, command.right_clip_id)

    def split_selected_clip(self, split_timeline_position: float) -> bool:
        selected_clip_id = self._selection_controller.selected_clip_id()
        if selected_clip_id is None:
            return False

        try:
            split_result = self.split_clip(selected_clip_id, split_timeline_position)
        except ValueError:
            return False

        if split_result is None:
            return False

        _, right_clip_id = split_result
        self._selection_controller.select_clip(right_clip_id)
        return True

    def delete_clip(self, clip_id: str) -> bool:
        timeline = self.active_timeline()
        if timeline is None:
            return False

        try:
            track, clip = self._find_clip_with_track(timeline, clip_id)
        except ValueError:
            return False

        if self._is_clip_locked(track, clip):
            return False

        self._command_manager.execute(DeleteClipCommand(timeline=timeline, clip_id=clip_id))
        if self._selection_controller.is_selected(clip_id):
            remaining = [selected for selected in self._selection_controller.selected_clip_ids() if selected != clip_id]
            self._selection_controller.set_selection(remaining)
        self.timeline_changed.emit()
        self.timeline_edited.emit()
        return True

    def delete_selected_clip(self) -> bool:
        timeline = self.active_timeline()
        if timeline is None:
            return False
        selected_ids = self._selection_controller.selected_clip_ids()
        if not selected_ids:
            return False

        deleted_any = False
        for clip_id in selected_ids:
            try:
                self._command_manager.execute(DeleteClipCommand(timeline=timeline, clip_id=clip_id))
                deleted_any = True
            except ValueError:
                continue

        self._selection_controller.clear_selection()
        if deleted_any:
            self.timeline_changed.emit()
            self.timeline_edited.emit()
        return deleted_any

    def ripple_delete_clip(self, clip_id: str | None = None) -> bool:
        timeline = self.active_timeline()
        if timeline is None:
            return False

        target_clip_id = self._resolve_clip_id_or_selection(clip_id)
        if target_clip_id is None:
            return False

        try:
            track, clip = self._find_clip_with_track(timeline, target_clip_id)
        except ValueError:
            return False

        if self._is_clip_locked(track, clip):
            return False

        deleted_duration = max(0.0, clip.duration)
        clip_end = clip.timeline_end
        shifted_clips = [
            candidate
            for candidate in track.clips
            if candidate.clip_id != clip.clip_id and candidate.timeline_start >= clip_end - 1e-6
        ]
        shifted_clips.sort(key=lambda item: item.timeline_start)

        commands: list[BaseCommand] = [DeleteClipCommand(timeline=timeline, clip_id=target_clip_id)]
        for shifted in shifted_clips:
            if shifted.is_locked:
                continue
            new_start = max(0.0, shifted.timeline_start - deleted_duration)
            if abs(new_start - shifted.timeline_start) < 1e-6:
                continue
            commands.append(
                UpdatePropertyCommand(
                    target=shifted,
                    attribute_name="timeline_start",
                    new_value=new_start,
                )
            )

        self.execute_command(CompositeCommand(commands))
        self._selection_controller.clear_selection()
        return True

    def has_clipboard_clip(self) -> bool:
        return self._clipboard_clip is not None

    def copy_clip_to_clipboard(self, clip_id: str | None = None) -> bool:
        target_clip_id = self._resolve_clip_id_or_selection(clip_id)
        if target_clip_id is None:
            return False

        clip = self._find_clip_by_id(target_clip_id)
        if clip is None:
            return False

        self._clipboard_clip = deepcopy(clip)
        return True

    def cut_clip_to_clipboard(self, clip_id: str | None = None) -> bool:
        target_clip_id = self._resolve_clip_id_or_selection(clip_id)
        if target_clip_id is None:
            return False
        if not self.copy_clip_to_clipboard(target_clip_id):
            return False
        return self.delete_clip(target_clip_id)

    def paste_clipboard_at(
        self,
        timeline_start: float | None = None,
        preferred_track_id: str | None = None,
    ) -> str | None:
        timeline = self.active_timeline()
        source_clip = self._clipboard_clip
        if timeline is None or source_clip is None:
            return None

        self._ensure_main_track_layout(timeline)
        target_start = max(0.0, self._playhead_seconds if timeline_start is None else timeline_start)
        target_track = self._select_target_track_for_clip(timeline, source_clip, preferred_track_id)
        if target_track is None or target_track.is_locked:
            return None

        new_clip = self._duplicate_clip_instance(
            source_clip=source_clip,
            track_id=target_track.track_id,
            timeline_start=target_start,
        )
        destination_track = self._find_track_for_non_overlapping_placement(
            timeline=timeline,
            clip=new_clip,
            proposed_start=target_start,
            preferred_track_id=target_track.track_id,
            allow_create_track=True,
        )
        if destination_track is None:
            return None
        new_clip.track_id = destination_track.track_id

        self.execute_command(
            AddClipCommand(
                timeline=timeline,
                track_id=destination_track.track_id,
                clip=new_clip,
            )
        )
        self._selection_controller.select_clip(new_clip.clip_id)
        return new_clip.clip_id

    def duplicate_clip(self, clip_id: str | None = None) -> str | None:
        timeline = self.active_timeline()
        if timeline is None:
            return None

        self._ensure_main_track_layout(timeline)
        target_clip_id = self._resolve_clip_id_or_selection(clip_id)
        if target_clip_id is None:
            return None

        try:
            track, clip = self._find_clip_with_track(timeline, target_clip_id)
        except ValueError:
            return None
        if self._is_clip_locked(track, clip):
            return None

        duplicate = self._duplicate_clip_instance(
            source_clip=clip,
            track_id=track.track_id,
            timeline_start=clip.timeline_start + clip.duration,
        )
        destination_track = self._find_track_for_non_overlapping_placement(
            timeline=timeline,
            clip=duplicate,
            proposed_start=duplicate.timeline_start,
            preferred_track_id=track.track_id,
            allow_create_track=True,
        )
        if destination_track is None:
            return None
        duplicate.track_id = destination_track.track_id

        self.execute_command(
            AddClipCommand(
                timeline=timeline,
                track_id=destination_track.track_id,
                clip=duplicate,
            )
        )
        self._selection_controller.select_clip(duplicate.clip_id)
        return duplicate.clip_id

    def add_track(self, track_type: str, name: str | None = None) -> str | None:
        timeline = self.active_timeline()
        if timeline is None:
            return None

        self._ensure_main_track_layout(timeline)
        normalized_type = (track_type or "").strip().lower()
        if normalized_type not in {"video", "audio", "text", "mixed", "overlay"}:
            return None

        default_name = self._default_track_name_for_type(normalized_type)
        safe_name = self._build_unique_track_name(timeline, (name or "").strip() or default_name)
        insert_index = self._insert_index_for_new_track(timeline, normalized_type)
        track = Track(
            track_id=f"track_{normalized_type}_{uuid4().hex[:6]}",
            name=safe_name,
            track_type=normalized_type,
        )
        self.execute_command(AddTrackCommand(timeline=timeline, track=track, insert_index=insert_index))
        return track.track_id

    def remove_track(self, track_id: str) -> bool:
        timeline = self.active_timeline()
        if timeline is None or len(timeline.tracks) <= 1:
            return False

        track = self._find_track_by_id(timeline, track_id)
        if track is None or track.is_locked:
            return False

        selected_clip_id = self._selection_controller.selected_clip_id()
        if selected_clip_id and any(clip.clip_id == selected_clip_id for clip in track.clips):
            self._selection_controller.clear_selection()

        try:
            self.execute_command(RemoveTrackCommand(timeline=timeline, track_id=track_id))
        except ValueError:
            return False
        return True

    def rename_track(self, track_id: str, name: str) -> bool:
        timeline = self.active_timeline()
        if timeline is None:
            return False

        track = self._find_track_by_id(timeline, track_id)
        if track is None:
            return False

        new_name = name.strip()
        if not new_name or new_name == track.name:
            return False

        self.execute_command(UpdatePropertyCommand(track, "name", new_name))
        return True

    def set_track_muted(self, track_id: str, is_muted: bool) -> bool:
        return self._set_track_property(track_id, "is_muted", bool(is_muted))

    def set_track_locked(self, track_id: str, is_locked: bool) -> bool:
        return self._set_track_property(track_id, "is_locked", bool(is_locked))

    def set_track_hidden(self, track_id: str, is_hidden: bool) -> bool:
        return self._set_track_property(track_id, "is_hidden", bool(is_hidden))

    def set_track_role(self, track_id: str, role: str) -> bool:
        normalized_role = (role or "").strip().lower()
        if normalized_role not in {"voice", "music", "sfx"}:
            return False

        timeline = self.active_timeline()
        if timeline is None:
            return False

        track = self._find_track_by_id(timeline, track_id)
        if track is None:
            return False
        if track.track_type.lower() not in {"audio", "mixed"}:
            return False
        return self._set_track_property(track_id, "track_role", normalized_role)

    def set_track_height(self, track_id: str, height: float) -> bool:
        clamped_height = max(28.0, min(float(height), 240.0))
        return self._set_track_property(track_id, "height", clamped_height)

    def add_transition(
        self,
        track_id: str,
        from_clip_id: str,
        to_clip_id: str,
        transition_type: str,
        duration_seconds: float | None = None,
    ) -> bool:
        timeline = self.active_timeline()
        if timeline is None:
            return False

        track = self._find_track_by_id(timeline, track_id)
        if track is None or track.is_locked:
            return False
        if not is_pair_adjacent(track, from_clip_id, to_clip_id):
            return False
        if any(
            transition.from_clip_id == from_clip_id and transition.to_clip_id == to_clip_id
            for transition in track.transitions
        ):
            return False

        max_duration = max_transition_duration(track, from_clip_id, to_clip_id)
        if max_duration <= 0.05:
            return False

        requested_duration = 0.5 if duration_seconds is None else float(duration_seconds)
        duration = max(0.05, min(max_duration, requested_duration))
        try:
            transition = make_transition(
                transition_type=transition_type,
                from_clip_id=from_clip_id,
                to_clip_id=to_clip_id,
                duration_seconds=duration,
            )
            self.execute_command(AddTransitionCommand(track, transition))
        except ValueError:
            return False
        return True

    def remove_transition(self, track_id: str, transition_id: str) -> bool:
        timeline = self.active_timeline()
        if timeline is None:
            return False

        track = self._find_track_by_id(timeline, track_id)
        if track is None or track.is_locked:
            return False
        if self._find_transition_index(track, transition_id) is None:
            return False

        self.execute_command(RemoveTransitionCommand(track, transition_id))
        return True

    def update_transition_duration(self, track_id: str, transition_id: str, new_duration: float) -> bool:
        timeline = self.active_timeline()
        if timeline is None:
            return False

        track = self._find_track_by_id(timeline, track_id)
        if track is None or track.is_locked:
            return False

        transition_index = self._find_transition_index(track, transition_id)
        if transition_index is None:
            return False

        transition = track.transitions[transition_index]
        max_duration = max_transition_duration(
            track,
            transition.from_clip_id,
            transition.to_clip_id,
        )
        if max_duration <= 0.05:
            return False

        clamped_duration = max(0.05, min(float(new_duration), max_duration))
        if abs(clamped_duration - float(transition.duration_seconds)) <= 1e-6:
            return False

        self.execute_command(
            UpdateTransitionDurationCommand(track, transition_id, clamped_duration)
        )
        return True

    def change_transition_type(self, track_id: str, transition_id: str, new_type: str) -> bool:
        timeline = self.active_timeline()
        if timeline is None:
            return False

        track = self._find_track_by_id(timeline, track_id)
        if track is None or track.is_locked:
            return False

        transition_index = self._find_transition_index(track, transition_id)
        if transition_index is None:
            return False
        if track.transitions[transition_index].transition_type == new_type:
            return False

        try:
            self.execute_command(ChangeTransitionTypeCommand(track, transition_id, new_type))
        except ValueError:
            return False
        return True

    def set_clip_fade(
        self,
        clip_id: str,
        fade_in_seconds: float | None = None,
        fade_out_seconds: float | None = None,
    ) -> bool:
        clip = self._find_clip_by_id(clip_id)
        if clip is None:
            return False

        timeline = self.active_timeline()
        if timeline is None:
            return False
        track, _ = self._find_clip_with_track(timeline, clip_id)
        if self._is_clip_locked(track, clip):
            return False

        max_total_fade = max(0.0, clip.duration - 0.001)
        new_fade_in = clip.fade_in_seconds if fade_in_seconds is None else max(0.0, float(fade_in_seconds))
        new_fade_out = clip.fade_out_seconds if fade_out_seconds is None else max(0.0, float(fade_out_seconds))
        if new_fade_in + new_fade_out > max_total_fade:
            overflow = (new_fade_in + new_fade_out) - max_total_fade
            if fade_in_seconds is not None and fade_out_seconds is None:
                new_fade_in = max(0.0, new_fade_in - overflow)
            elif fade_out_seconds is not None and fade_in_seconds is None:
                new_fade_out = max(0.0, new_fade_out - overflow)
            else:
                if new_fade_in + new_fade_out > 0:
                    scale = max_total_fade / (new_fade_in + new_fade_out)
                    new_fade_in *= scale
                    new_fade_out *= scale

        commands: list[BaseCommand] = []
        if abs(new_fade_in - clip.fade_in_seconds) > 1e-6:
            commands.append(UpdatePropertyCommand(clip, "fade_in_seconds", new_fade_in))
        if abs(new_fade_out - clip.fade_out_seconds) > 1e-6:
            commands.append(UpdatePropertyCommand(clip, "fade_out_seconds", new_fade_out))
        if not commands:
            return False

        if len(commands) == 1:
            self.execute_command(commands[0])
        else:
            self.execute_command(CompositeCommand(commands))
        return True

    def set_clip_playback_speed(self, clip_id: str, playback_speed: float) -> bool:
        clip = self._find_clip_by_id(clip_id)
        if clip is None or not isinstance(clip, (VideoClip, AudioClip)):
            return False
        timeline = self.active_timeline()
        if timeline is None:
            return False
        track, _ = self._find_clip_with_track(timeline, clip_id)
        if self._is_clip_locked(track, clip):
            return False

        safe_speed = max(0.1, min(float(playback_speed), 8.0))
        if abs(clip.playback_speed - safe_speed) < 1e-6:
            return False

        self.execute_command(UpdatePropertyCommand(clip, "playback_speed", safe_speed))
        return True

    def set_clip_reversed(self, clip_id: str, is_reversed: bool) -> bool:
        clip = self._find_clip_by_id(clip_id)
        if not isinstance(clip, VideoClip):
            return False
        timeline = self.active_timeline()
        if timeline is None:
            return False
        track, _ = self._find_clip_with_track(timeline, clip_id)
        if self._is_clip_locked(track, clip):
            return False
        new_value = bool(is_reversed)
        if clip.is_reversed == new_value:
            return False

        self.execute_command(UpdatePropertyCommand(clip, "is_reversed", new_value))
        return True

    def set_clip_gain_db(self, clip_id: str, gain_db: float) -> bool:
        clip = self._find_clip_by_id(clip_id)
        if not isinstance(clip, AudioClip):
            return False
        timeline = self.active_timeline()
        if timeline is None:
            return False
        track, _ = self._find_clip_with_track(timeline, clip_id)
        if self._is_clip_locked(track, clip):
            return False

        safe_gain = max(-60.0, min(float(gain_db), 12.0))
        if abs(clip.gain_db - safe_gain) < 1e-6:
            return False

        if self._auto_keyframe_enabled:
            time_in_clip = self._time_in_clip(clip, self._playhead_seconds)
            commands: list[BaseCommand] = [
                UpdatePropertyCommand(clip, "gain_db", safe_gain),
                AddKeyframeCommand(
                    clip,
                    "gain_db",
                    Keyframe(time_seconds=time_in_clip, value=safe_gain),
                ),
            ]
            self.execute_command(CompositeCommand(commands))
            return True

        self.execute_command(UpdatePropertyCommand(clip, "gain_db", safe_gain))
        return True

    def set_clip_muted(self, clip_id: str, is_muted: bool) -> bool:
        clip = self._find_clip_by_id(clip_id)
        if clip is None:
            return False
        timeline = self.active_timeline()
        if timeline is None:
            return False
        track, _ = self._find_clip_with_track(timeline, clip_id)
        if self._is_clip_locked(track, clip):
            return False

        new_value = bool(is_muted)
        if clip.is_muted == new_value:
            return False
        self.execute_command(UpdatePropertyCommand(clip, "is_muted", new_value))
        return True

    # --- Transform / adjustment API (Sprint 2) --------------------------
    def set_clip_transform(
        self,
        clip_id: str,
        *,
        position_x: float | None = None,
        position_y: float | None = None,
        scale: float | None = None,
        rotation: float | None = None,
    ) -> bool:
        clip = self._find_clip_by_id(clip_id)
        if clip is None:
            return False
        timeline = self.active_timeline()
        if timeline is None:
            return False
        track, _ = self._find_clip_with_track(timeline, clip_id)
        if self._is_clip_locked(track, clip):
            return False

        updates: list[BaseCommand] = []
        time_in_clip = self._time_in_clip(clip, self._playhead_seconds)
        for attr, value, clamp in (
            ("position_x", position_x, lambda v: max(-2.0, min(3.0, float(v)))),
            ("position_y", position_y, lambda v: max(-2.0, min(3.0, float(v)))),
            ("scale", scale, lambda v: max(0.05, min(8.0, float(v)))),
            ("rotation", rotation, lambda v: ((float(v) + 180.0) % 360.0) - 180.0),
        ):
            if value is None or not hasattr(clip, attr):
                continue
            next_value = clamp(value)
            current_value = getattr(clip, attr)
            if abs(float(current_value) - float(next_value)) <= 1e-6:
                continue
            updates.append(UpdatePropertyCommand(clip, attr, next_value))
            if self._auto_keyframe_enabled:
                updates.append(
                    AddKeyframeCommand(
                        clip,
                        attr,
                        Keyframe(time_seconds=time_in_clip, value=next_value),
                    )
                )

        if not updates:
            return False
        if len(updates) == 1:
            self.execute_command(updates[0])
        else:
            self.execute_command(CompositeCommand(updates))
        return True

    # --- Keyframe API (Sprint 3) ----------------------------------------
    def add_keyframe(
        self,
        clip_id: str,
        property_name: str,
        time_seconds: float,
        value: float,
        interpolation: str = "linear",
    ) -> bool:
        clip = self._find_clip_by_id(clip_id)
        if clip is None:
            return False

        timeline = self.active_timeline()
        if timeline is None:
            return False
        track, _ = self._find_clip_with_track(timeline, clip_id)
        if self._is_clip_locked(track, clip):
            return False

        time_in_clip = max(0.0, min(float(clip.duration), float(time_seconds)))
        try:
            keyframe = Keyframe(
                time_seconds=time_in_clip,
                value=float(value),
                interpolation=interpolation,
            )
            self.execute_command(AddKeyframeCommand(clip, property_name, keyframe))
        except ValueError:
            return False
        return True

    def remove_keyframe(self, clip_id: str, property_name: str, time_seconds: float) -> bool:
        clip = self._find_clip_by_id(clip_id)
        if clip is None:
            return False

        timeline = self.active_timeline()
        if timeline is None:
            return False
        track, _ = self._find_clip_with_track(timeline, clip_id)
        if self._is_clip_locked(track, clip):
            return False

        try:
            self.execute_command(
                RemoveKeyframeCommand(
                    clip,
                    property_name,
                    float(time_seconds),
                )
            )
        except ValueError:
            return False
        return True

    def move_keyframe(
        self,
        clip_id: str,
        property_name: str,
        old_time_seconds: float,
        new_time_seconds: float,
    ) -> bool:
        clip = self._find_clip_by_id(clip_id)
        if clip is None:
            return False

        timeline = self.active_timeline()
        if timeline is None:
            return False
        track, _ = self._find_clip_with_track(timeline, clip_id)
        if self._is_clip_locked(track, clip):
            return False

        clamped_new_time = max(0.0, min(float(new_time_seconds), float(clip.duration)))
        try:
            self.execute_command(
                MoveKeyframeCommand(
                    clip,
                    property_name,
                    float(old_time_seconds),
                    clamped_new_time,
                )
            )
        except ValueError:
            return False
        return True

    def update_keyframe_value(
        self,
        clip_id: str,
        property_name: str,
        time_seconds: float,
        new_value: float,
    ) -> bool:
        clip = self._find_clip_by_id(clip_id)
        if clip is None:
            return False

        timeline = self.active_timeline()
        if timeline is None:
            return False
        track, _ = self._find_clip_with_track(timeline, clip_id)
        if self._is_clip_locked(track, clip):
            return False

        try:
            self.execute_command(
                UpdateKeyframeValueCommand(
                    clip,
                    property_name,
                    float(time_seconds),
                    float(new_value),
                )
            )
        except ValueError:
            return False
        return True

    def set_keyframe_interpolation(
        self,
        clip_id: str,
        property_name: str,
        time_seconds: float,
        interpolation: str,
    ) -> bool:
        clip = self._find_clip_by_id(clip_id)
        if clip is None:
            return False

        timeline = self.active_timeline()
        if timeline is None:
            return False
        track, _ = self._find_clip_with_track(timeline, clip_id)
        if self._is_clip_locked(track, clip):
            return False

        try:
            self.execute_command(
                SetKeyframeInterpolationCommand(
                    clip,
                    property_name,
                    float(time_seconds),
                    interpolation,
                )
            )
        except ValueError:
            return False
        return True

    def update_keyframe_bezier(
        self,
        clip_id: str,
        property_name: str,
        time_seconds: float,
        cp1_dx: float,
        cp1_dy: float,
        cp2_dx: float,
        cp2_dy: float,
    ) -> bool:
        clip = self._find_clip_by_id(clip_id)
        if clip is None:
            return False

        timeline = self.active_timeline()
        if timeline is None:
            return False
        track, _ = self._find_clip_with_track(timeline, clip_id)
        if self._is_clip_locked(track, clip):
            return False

        attr_name = property_name if property_name.endswith("_keyframes") else f"{property_name}_keyframes"
        keyframes = getattr(clip, attr_name, None)
        if not isinstance(keyframes, list):
            return False

        target = next(
            (
                keyframe
                for keyframe in keyframes
                if abs(float(keyframe.time_seconds) - float(time_seconds)) <= 1e-4
            ),
            None,
        )
        if target is None or target.interpolation != "bezier":
            return False

        next_cp1_dx = max(0.0, min(1.0, float(cp1_dx)))
        next_cp1_dy = float(cp1_dy)
        next_cp2_dx = max(0.0, min(1.0, float(cp2_dx)))
        next_cp2_dy = float(cp2_dy)
        if (
            abs(float(target.bezier_cp1_dx) - next_cp1_dx) <= 1e-6
            and abs(float(target.bezier_cp1_dy) - next_cp1_dy) <= 1e-6
            and abs(float(target.bezier_cp2_dx) - next_cp2_dx) <= 1e-6
            and abs(float(target.bezier_cp2_dy) - next_cp2_dy) <= 1e-6
        ):
            return False

        self.execute_command(
            UpdateKeyframeBezierCommand(
                clip=clip,
                property_name=attr_name,
                time_seconds=float(time_seconds),
                cp1_dx=next_cp1_dx,
                cp1_dy=next_cp1_dy,
                cp2_dx=next_cp2_dx,
                cp2_dy=next_cp2_dy,
            )
        )
        return True

    def undo(self) -> bool:
        did_undo = self._command_manager.undo()
        if did_undo:
            self.timeline_changed.emit()
            self.timeline_edited.emit()
        return did_undo

    def redo(self) -> bool:
        did_redo = self._command_manager.redo()
        if did_redo:
            self.timeline_changed.emit()
            self.timeline_edited.emit()
        return did_redo

    def execute_command(self, command: BaseCommand) -> None:
        self._command_manager.execute(command)
        self.timeline_changed.emit()
        self.timeline_edited.emit()

    def _on_project_changed(self) -> None:
        self._command_manager = CommandManager()
        self._clipboard_clip = None
        timeline = self.active_timeline()
        if timeline is not None:
            self._ensure_main_track_layout(timeline)
        self.timeline_changed.emit()

    def _apply_move_snapping(self, timeline: Timeline, clip: BaseClip, proposed_start: float) -> float:
        if not self._snapping_enabled:
            return proposed_start
        threshold_seconds = self._snap_threshold_seconds()
        if threshold_seconds <= 0:
            return proposed_start

        targets = self._collect_snap_targets(timeline=timeline, exclude_clip_id=clip.clip_id)
        snap_delta = SnapEngine.best_move_delta(
            start=proposed_start,
            duration=clip.duration,
            targets=targets,
            threshold=threshold_seconds,
        )
        if snap_delta is None:
            return proposed_start

        return max(0.0, proposed_start + snap_delta)

    def _apply_trim_snapping(
        self,
        timeline: Timeline,
        clip: BaseClip,
        proposed_start: float,
        proposed_duration: float,
        trim_side: Literal["left", "right"] | None,
    ) -> tuple[float, float]:
        if not self._snapping_enabled:
            return proposed_start, proposed_duration
        side = self._resolve_trim_side(clip, proposed_start, proposed_duration, trim_side)
        threshold_seconds = self._snap_threshold_seconds()
        targets = self._collect_snap_targets(timeline=timeline, exclude_clip_id=clip.clip_id)

        if side == "left":
            right_edge = clip.timeline_end
            left_edge = proposed_start
            snapped_left = SnapEngine.snap_value(left_edge, targets, threshold_seconds)
            final_left = left_edge if snapped_left is None else snapped_left
            max_left = right_edge - self._minimum_clip_duration_seconds
            final_left = min(max(final_left, 0.0), max_left)
            return final_left, right_edge - final_left

        right_edge = clip.timeline_start + proposed_duration
        snapped_right = SnapEngine.snap_value(right_edge, targets, threshold_seconds)
        final_right = right_edge if snapped_right is None else snapped_right
        min_right = clip.timeline_start + self._minimum_clip_duration_seconds
        final_right = max(final_right, min_right)
        return clip.timeline_start, final_right - clip.timeline_start

    def _resolve_trim_side(
        self,
        clip: BaseClip,
        proposed_start: float,
        proposed_duration: float,
        explicit_side: Literal["left", "right"] | None,
    ) -> Literal["left", "right"]:
        if explicit_side in ("left", "right"):
            return explicit_side

        proposed_right = proposed_start + proposed_duration
        moved_left_distance = abs(proposed_start - clip.timeline_start)
        moved_right_distance = abs(proposed_right - clip.timeline_end)
        if moved_left_distance > moved_right_distance:
            return "left"
        return "right"

    def _snap_threshold_seconds(self) -> float:
        if self._pixels_per_second <= 0:
            return 0.0
        return self._snap_threshold_pixels / self._pixels_per_second

    def _collect_snap_targets(self, timeline: Timeline, exclude_clip_id: str) -> list[float]:
        targets = [max(0.0, self._playhead_seconds)]
        for track in timeline.tracks:
            if track.is_hidden:
                continue
            for clip in track.clips:
                if clip.clip_id == exclude_clip_id:
                    continue
                targets.append(clip.timeline_start)
                targets.append(clip.timeline_end)
        return targets

    def _find_clip(self, timeline: Timeline, clip_id: str) -> BaseClip:
        for track in timeline.tracks:
            for clip in track.clips:
                if clip.clip_id == clip_id:
                    return clip
        raise ValueError(f"Clip '{clip_id}' not found in timeline")

    def _find_clip_with_track(self, timeline: Timeline, clip_id: str) -> tuple[Track, BaseClip]:
        for track in timeline.tracks:
            for clip in track.clips:
                if clip.clip_id == clip_id:
                    return track, clip
        raise ValueError(f"Clip '{clip_id}' not found in timeline")

    @staticmethod
    def _is_clip_locked(track: Track, clip: BaseClip) -> bool:
        return bool(track.is_locked or clip.is_locked)

    @staticmethod
    def _find_media_asset(project: Project, media_id: str) -> MediaAsset:
        for media_asset in project.media_items:
            if media_asset.media_id == media_id:
                return media_asset
        raise ValueError(f"Media asset '{media_id}' not found in project")

    def _select_target_track(
        self,
        timeline: Timeline,
        media_type: str,
        preferred_track_id: str | None,
    ) -> Track | None:
        preferred_track = self._find_track_by_id(timeline, preferred_track_id) if preferred_track_id else None
        if (
            preferred_track is not None
            and not preferred_track.is_locked
            and self._is_track_compatible(media_type, preferred_track.track_type)
        ):
            return preferred_track

        for track in timeline.tracks:
            if track.is_locked:
                continue
            if self._is_track_compatible(media_type, track.track_type):
                return track

        if preferred_track is not None and self._is_track_compatible(media_type, preferred_track.track_type):
            return preferred_track

        return None

    @staticmethod
    def _is_track_compatible(media_type: str, track_type: str) -> bool:
        normalized_media_type = media_type.lower()
        normalized_track_type = track_type.lower()

        if normalized_track_type == "mixed":
            return True
        if normalized_media_type == "audio":
            return normalized_track_type in {"audio", "mixed"}
        if normalized_media_type == "video":
            return normalized_track_type in {"video", "mixed", "overlay"}
        if normalized_media_type == "image":
            return normalized_track_type in {"video", "overlay", "mixed"}
        return True

    def add_caption_segments(
        self,
        segments: list[tuple[float, float, str]],
        timeline_offset_seconds: float | None = None,
    ) -> int:
        timeline = self.active_timeline()
        if timeline is None or not segments:
            return 0

        self._ensure_main_track_layout(timeline)
        text_track = self._ensure_text_track(timeline)
        if text_track.is_locked:
            return 0

        base_offset = max(0.0, self._playhead_seconds if timeline_offset_seconds is None else timeline_offset_seconds)

        created_clip_ids: list[str] = []
        for segment_start, segment_end, segment_text in segments:
            if not segment_text.strip():
                continue

            start = max(0.0, base_offset + segment_start)
            end = max(start + 0.05, base_offset + segment_end)
            duration = max(0.05, end - start)
            content = segment_text.strip()
            clip_id = f"clip_{uuid4().hex[:10]}"
            clip = TextClip(
                clip_id=clip_id,
                name=(content[:32] or "Caption"),
                track_id=text_track.track_id,
                timeline_start=start,
                duration=duration,
                content=content,
                font_size=46,
                color="#ffffff",
                position_x=0.5,
                position_y=0.86,
                font_family="Arial",
                bold=True,
                alignment="center",
                outline_color="#000000",
                outline_width=3.0,
            )
            destination_track = self._find_track_for_non_overlapping_placement(
                timeline=timeline,
                clip=clip,
                proposed_start=clip.timeline_start,
                preferred_track_id=text_track.track_id,
                allow_create_track=True,
            )
            if destination_track is None:
                continue
            clip.track_id = destination_track.track_id

            self._command_manager.execute(
                AddClipCommand(
                    timeline=timeline,
                    track_id=destination_track.track_id,
                    clip=clip,
                )
            )
            created_clip_ids.append(clip_id)

        if not created_clip_ids:
            return 0

        self._selection_controller.select_clip(created_clip_ids[-1])
        self.timeline_changed.emit()
        self.timeline_edited.emit()
        return len(created_clip_ids)

    def caption_clips(self) -> list[TextClip]:
        timeline = self.active_timeline()
        if timeline is None:
            return []

        captions: list[TextClip] = []
        for track in timeline.tracks:
            if track.track_type.lower() != "text":
                continue
            for clip in track.sorted_clips():
                if isinstance(clip, TextClip):
                    captions.append(clip)
        return captions

    def update_caption_text(self, clip_id: str, new_text: str) -> bool:
        clip = self._find_clip_by_id(clip_id)
        if not isinstance(clip, TextClip):
            return False
        if clip.content == new_text:
            return False

        self.execute_command(
            UpdatePropertyCommand(target=clip, attribute_name="content", new_value=new_text)
        )
        return True

    def duplicate_caption_clip(self, clip_id: str) -> str | None:
        clip = self._find_clip_by_id(clip_id)
        if not isinstance(clip, TextClip):
            return None
        return self.duplicate_clip(clip_id)

    def merge_caption_with_next(self, clip_id: str) -> bool:
        timeline = self.active_timeline()
        if timeline is None:
            return False

        clip = self._find_clip_by_id(clip_id)
        if not isinstance(clip, TextClip):
            return False

        track = next((track for track in timeline.tracks if track.track_id == clip.track_id), None)
        if track is None or track.is_locked:
            return False

        sorted_clips = track.sorted_clips()
        try:
            index = sorted_clips.index(clip)
        except ValueError:
            return False
        if index + 1 >= len(sorted_clips):
            return False

        next_clip = sorted_clips[index + 1]
        if not isinstance(next_clip, TextClip):
            return False

        merged_content = (clip.content or "").rstrip()
        if next_clip.content:
            next_content = next_clip.content.strip()
            merged_content = f"{merged_content}\n{next_content}" if merged_content else next_content

        new_end = max(
            clip.timeline_start + clip.duration,
            next_clip.timeline_start + next_clip.duration,
        )
        new_duration = max(0.05, new_end - clip.timeline_start)

        self._command_manager.execute(
            UpdatePropertyCommand(target=clip, attribute_name="content", new_value=merged_content)
        )
        self._command_manager.execute(
            UpdatePropertyCommand(target=clip, attribute_name="duration", new_value=new_duration)
        )
        self._command_manager.execute(
            DeleteClipCommand(timeline=timeline, clip_id=next_clip.clip_id)
        )
        self.timeline_changed.emit()
        self.timeline_edited.emit()
        return True

    def _find_clip_by_id(self, clip_id: str) -> BaseClip | None:
        timeline = self.active_timeline()
        if timeline is None:
            return None
        for track in timeline.tracks:
            for clip in track.clips:
                if clip.clip_id == clip_id:
                    return clip
        return None

    def _ensure_text_track(self, timeline: Timeline) -> Track:
        for track in timeline.tracks:
            if track.track_type.lower() == "text" and not track.is_locked:
                return track
        track = Track(
            track_id=f"track_text_{uuid4().hex[:6]}",
            name=self._build_unique_track_name(timeline, self._default_track_name_for_type("text")),
            track_type="text",
        )
        insert_index = self._insert_index_for_new_track(timeline, "text")
        self._command_manager.execute(AddTrackCommand(timeline=timeline, track=track, insert_index=insert_index))
        return track

    def _build_clip_from_media(self, media_asset: MediaAsset, track_id: str, timeline_start: float) -> BaseClip:
        media_type = media_asset.media_type.lower()
        clip_id = f"clip_{uuid4().hex[:10]}"
        duration = self._default_duration_for_media(media_asset)
        source_end = media_asset.duration_seconds if media_asset.duration_seconds and media_asset.duration_seconds > 0 else None

        if media_type == "audio":
            return AudioClip(
                clip_id=clip_id,
                name=media_asset.name,
                track_id=track_id,
                media_id=media_asset.media_id,
                timeline_start=timeline_start,
                duration=duration,
                source_start=0.0,
                source_end=source_end,
            )

        if media_type == "image":
            return ImageClip(
                clip_id=clip_id,
                name=media_asset.name,
                track_id=track_id,
                media_id=media_asset.media_id,
                timeline_start=timeline_start,
                duration=duration,
                source_start=0.0,
                source_end=source_end,
            )

        return VideoClip(
            clip_id=clip_id,
            name=media_asset.name,
            track_id=track_id,
            media_id=media_asset.media_id,
            timeline_start=timeline_start,
            duration=duration,
            source_start=0.0,
            source_end=source_end,
        )

    @staticmethod
    def _default_duration_for_media(media_asset: MediaAsset) -> float:
        if media_asset.duration_seconds is not None and media_asset.duration_seconds > 0:
            return media_asset.duration_seconds
        if media_asset.media_type.lower() == "image":
            return 4.0
        return 5.0

    def _set_track_property(self, track_id: str, attribute_name: str, value: object) -> bool:
        timeline = self.active_timeline()
        if timeline is None:
            return False
        track = self._find_track_by_id(timeline, track_id)
        if track is None:
            return False

        if getattr(track, attribute_name) == value:
            return False
        self.execute_command(UpdatePropertyCommand(track, attribute_name, value))
        return True

    @staticmethod
    def _find_track_by_id(timeline: Timeline, track_id: str | None) -> Track | None:
        if track_id is None:
            return None
        for track in timeline.tracks:
            if track.track_id == track_id:
                return track
        return None

    @staticmethod
    def _find_transition_index(track: Track, transition_id: str) -> int | None:
        for index, transition in enumerate(track.transitions):
            if transition.transition_id == transition_id:
                return index
        return None

    def _resolve_clip_id_or_selection(self, clip_id: str | None) -> str | None:
        if clip_id is not None:
            return clip_id
        return self._selection_controller.selected_clip_id()

    @staticmethod
    def _time_in_clip(clip: BaseClip, absolute_time_seconds: float) -> float:
        local = float(absolute_time_seconds) - float(clip.timeline_start)
        return max(0.0, min(float(clip.duration), local))

    def _select_target_track_for_clip(
        self,
        timeline: Timeline,
        clip: BaseClip,
        preferred_track_id: str | None,
    ) -> Track | None:
        preferred = self._find_track_by_id(timeline, preferred_track_id)
        if preferred is not None and not preferred.is_locked and self._track_accepts_clip(preferred, clip):
            return preferred

        original_track = self._find_track_by_id(timeline, clip.track_id)
        if original_track is not None and not original_track.is_locked and self._track_accepts_clip(original_track, clip):
            return original_track

        for track in timeline.tracks:
            if track.is_locked:
                continue
            if self._track_accepts_clip(track, clip):
                return track
        return None

    @staticmethod
    def _track_accepts_clip(track: Track, clip: BaseClip) -> bool:
        normalized_track_type = track.track_type.lower()
        if normalized_track_type == "mixed":
            return True
        if isinstance(clip, AudioClip):
            return normalized_track_type in {"audio", "mixed"}
        if isinstance(clip, TextClip):
            return normalized_track_type in {"text", "overlay", "mixed"}
        if isinstance(clip, (VideoClip, ImageClip)):
            return normalized_track_type in {"video", "overlay", "mixed"}
        return True

    def _find_track_for_non_overlapping_placement(
        self,
        timeline: Timeline,
        clip: BaseClip,
        proposed_start: float,
        preferred_track_id: str | None,
        allow_create_track: bool,
        exclude_clip_id: str | None = None,
        proposed_duration: float | None = None,
    ) -> Track | None:
        duration = max(0.001, clip.duration if proposed_duration is None else proposed_duration)
        candidate_tracks: list[Track] = []

        preferred_track = self._find_track_by_id(timeline, preferred_track_id)
        if preferred_track is not None:
            candidate_tracks.append(preferred_track)

        clip_track = self._find_track_by_id(timeline, clip.track_id)
        if clip_track is not None and clip_track not in candidate_tracks:
            candidate_tracks.append(clip_track)

        for track in timeline.tracks:
            if track not in candidate_tracks:
                candidate_tracks.append(track)

        for candidate in candidate_tracks:
            if candidate.is_locked:
                continue
            if not self._track_accepts_clip(candidate, clip):
                continue
            if self._track_has_overlap(
                track=candidate,
                clip_start=proposed_start,
                clip_duration=duration,
                exclude_clip_id=exclude_clip_id,
            ):
                continue
            return candidate

        if not allow_create_track:
            return None
        return self._create_auto_track_for_clip(timeline, clip)

    def _track_has_overlap(
        self,
        track: Track,
        clip_start: float,
        clip_duration: float,
        exclude_clip_id: str | None = None,
    ) -> bool:
        epsilon = 1e-6
        clip_end = clip_start + max(0.0, clip_duration)
        for existing in track.clips:
            if exclude_clip_id is not None and existing.clip_id == exclude_clip_id:
                continue
            existing_start = existing.timeline_start
            existing_end = existing.timeline_end
            if clip_start < existing_end - epsilon and clip_end > existing_start + epsilon:
                return True
        return False

    def _create_auto_track_for_clip(self, timeline: Timeline, clip: BaseClip) -> Track | None:
        if isinstance(clip, TextClip):
            track_type = "text"
        elif isinstance(clip, AudioClip):
            track_type = "audio"
        elif isinstance(clip, (VideoClip, ImageClip)):
            track_type = "video"
        else:
            return None

        track = Track(
            track_id=f"track_{track_type}_{uuid4().hex[:6]}",
            name=self._build_unique_track_name(timeline, self._default_track_name_for_type(track_type)),
            track_type=track_type,
        )
        insert_index = self._insert_index_for_new_track(timeline, track_type)
        self._command_manager.execute(AddTrackCommand(timeline=timeline, track=track, insert_index=insert_index))
        return track

    def _ensure_main_track_layout(self, timeline: Timeline) -> None:
        text_tracks = [track for track in timeline.tracks if track.track_type.lower() == "text"]
        video_tracks = [track for track in timeline.tracks if track.track_type.lower() in {"video", "overlay"}]
        media_tracks = [track for track in timeline.tracks if track.track_type.lower() in {"audio", "mixed"}]
        other_tracks = [
            track
            for track in timeline.tracks
            if track not in text_tracks and track not in video_tracks and track not in media_tracks
        ]

        if not video_tracks:
            main_track = Track(
                track_id=f"track_video_{uuid4().hex[:6]}",
                name="Main",
                track_type="video",
            )
            timeline.tracks.append(main_track)
            video_tracks = [main_track]

        main_track = next((track for track in video_tracks if track.name.strip().lower() == "main"), video_tracks[0])
        main_track.name = "Main"
        video_tracks = [main_track] + [track for track in video_tracks if track.track_id != main_track.track_id]

        if not text_tracks:
            text_track = Track(
                track_id=f"track_text_{uuid4().hex[:6]}",
                name=self._build_unique_track_name(timeline, self._default_track_name_for_type("text")),
                track_type="text",
            )
            timeline.tracks.append(text_track)
            text_tracks = [text_track]

        if not media_tracks:
            media_track = Track(
                track_id=f"track_audio_{uuid4().hex[:6]}",
                name=self._build_unique_track_name(timeline, self._default_track_name_for_type("audio")),
                track_type="audio",
            )
            timeline.tracks.append(media_track)
            media_tracks = [media_track]

        timeline.tracks = [*text_tracks, *video_tracks, *media_tracks, *other_tracks]

    def _insert_index_for_new_track(self, timeline: Timeline, track_type: str) -> int:
        normalized = track_type.lower()
        if normalized == "text":
            text_indices = [index for index, track in enumerate(timeline.tracks) if track.track_type.lower() == "text"]
            return (max(text_indices) + 1) if text_indices else 0

        if normalized in {"video", "overlay"}:
            text_count = len([track for track in timeline.tracks if track.track_type.lower() == "text"])
            video_indices = [
                index
                for index, track in enumerate(timeline.tracks)
                if track.track_type.lower() in {"video", "overlay"}
            ]
            if video_indices:
                return max(video_indices) + 1
            return text_count

        if normalized in {"audio", "mixed"}:
            media_indices = [
                index
                for index, track in enumerate(timeline.tracks)
                if track.track_type.lower() in {"audio", "mixed"}
            ]
            if media_indices:
                return max(media_indices) + 1
            return len(timeline.tracks)

        return len(timeline.tracks)

    @staticmethod
    def _default_track_name_for_type(track_type: str) -> str:
        normalized = track_type.lower()
        if normalized == "video":
            return "Main"
        if normalized == "overlay":
            return "Overlay"
        if normalized == "text":
            return "Text"
        if normalized in {"audio", "mixed"}:
            return "Media"
        return normalized.title()

    @staticmethod
    def _build_unique_track_name(timeline: Timeline, base_name: str) -> str:
        existing = {track.name for track in timeline.tracks}
        if base_name not in existing:
            return base_name

        index = 2
        while True:
            candidate = f"{base_name} {index}"
            if candidate not in existing:
                return candidate
            index += 1

    @staticmethod
    def _duplicate_clip_instance(source_clip: BaseClip, track_id: str, timeline_start: float) -> BaseClip:
        clip = deepcopy(source_clip)
        clip.clip_id = f"clip_{uuid4().hex[:10]}"
        clip.track_id = track_id
        clip.timeline_start = max(0.0, timeline_start)
        return clip
