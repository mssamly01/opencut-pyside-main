"""Unit tests for snapping and command-based timeline editing."""

from __future__ import annotations

import pytest
from app.controllers.project_controller import ProjectController
from app.controllers.selection_controller import SelectionController
from app.controllers.timeline_controller import TimelineController
from app.domain.commands import CommandManager, DeleteClipCommand, MoveClipCommand
from app.domain.project import build_demo_project


@pytest.fixture
def project():
    return build_demo_project()


def test_command_manager_undo_redo_roundtrip(project) -> None:
    timeline = project.timeline
    target_clip = timeline.tracks[1].clips[0]
    original_start = target_clip.timeline_start

    manager = CommandManager()
    manager.execute(MoveClipCommand(timeline=timeline, clip_id=target_clip.clip_id, new_timeline_start=42.0))
    assert target_clip.timeline_start == 42.0

    assert manager.undo()
    assert target_clip.timeline_start == pytest.approx(original_start)

    assert manager.redo()
    assert target_clip.timeline_start == 42.0


def test_delete_clip_command_restores_on_undo(project) -> None:
    timeline = project.timeline
    original_count = sum(len(track.clips) for track in timeline.tracks)
    target_clip = timeline.tracks[1].clips[0]
    target_clip_id = target_clip.clip_id

    manager = CommandManager()
    manager.execute(DeleteClipCommand(timeline=timeline, clip_id=target_clip_id))
    remaining_ids = {clip.clip_id for track in timeline.tracks for clip in track.clips}
    assert target_clip_id not in remaining_ids

    assert manager.undo()
    restored_ids = {clip.clip_id for track in timeline.tracks for clip in track.clips}
    assert target_clip_id in restored_ids
    assert sum(len(track.clips) for track in timeline.tracks) == original_count


def test_timeline_controller_move_clip_uses_command_manager(project) -> None:
    project_controller = ProjectController()
    project_controller.set_active_project(project)
    selection_controller = SelectionController()
    timeline_controller = TimelineController(
        project_controller=project_controller,
        selection_controller=selection_controller,
    )

    clip = project.timeline.tracks[1].clips[0]
    original_start = clip.timeline_start
    moved = timeline_controller.move_clip(clip.clip_id, original_start + 2.0)
    assert moved is True
    assert clip.timeline_start == pytest.approx(original_start + 2.0)

    assert timeline_controller.undo()
    assert clip.timeline_start == pytest.approx(original_start)


def test_snap_engine_snaps_to_nearby_marker(project) -> None:
    project_controller = ProjectController()
    project_controller.set_active_project(project)
    selection_controller = SelectionController()
    timeline_controller = TimelineController(
        project_controller=project_controller,
        selection_controller=selection_controller,
    )
    timeline_controller.configure_timeline_metrics(
        pixels_per_second=90.0,
        snap_threshold_pixels=10.0,
        playhead_seconds=0.0,
        minimum_clip_duration_seconds=0.2,
    )

    first_clip = project.timeline.tracks[1].clips[0]
    neighbour_clip = project.timeline.tracks[1].clips[1]
    proposed_start = neighbour_clip.timeline_start + 0.02
    snapped_start, snapped_duration, snap_target = timeline_controller.get_snap_position(
        first_clip.clip_id,
        proposed_start,
        first_clip.duration,
        "move",
    )

    assert snap_target is not None
    assert snapped_start == pytest.approx(neighbour_clip.timeline_start, abs=0.1) or \
           snapped_start == pytest.approx(neighbour_clip.timeline_end, abs=0.1)
    assert snapped_duration == pytest.approx(first_clip.duration)
