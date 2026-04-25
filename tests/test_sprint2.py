from __future__ import annotations

from pathlib import Path

from app.controllers.project_controller import ProjectController
from app.controllers.selection_controller import SelectionController
from app.controllers.timeline_controller import TimelineController
from app.domain.clips.image_clip import ImageClip
from app.domain.clips.video_clip import VideoClip
from app.domain.project import build_demo_project
from app.dto.export_dto import ExportOptions
from app.services.export_service import ExportService
from app.services.project_service import ProjectService


def _wired_controllers() -> tuple[TimelineController, SelectionController, ProjectController]:
    project_controller = ProjectController()
    project_controller.set_active_project(build_demo_project())
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
    return timeline_controller, selection_controller, project_controller


def test_selection_controller_multi_select_apis() -> None:
    sc = SelectionController()
    sc.set_selection(["a", "b", "c"])
    assert sc.selected_clip_ids() == ["a", "b", "c"]
    assert sc.is_selected("b")
    assert sc.selected_clip_id() == "a"

    sc.toggle_selection("b")
    assert sc.selected_clip_ids() == ["a", "c"]
    sc.toggle_selection("d")
    assert sc.selected_clip_ids() == ["a", "c", "d"]

    sc.add_to_selection("c")
    assert sc.selected_clip_ids() == ["a", "c", "d"]

    sc.clear_selection()
    assert sc.selected_clip_ids() == []
    assert sc.selected_clip_id() is None


def test_set_selection_dedupes_and_unchanged_is_noop() -> None:
    sc = SelectionController()
    events = {"count": 0}
    sc.selection_changed.connect(lambda: events.__setitem__("count", events["count"] + 1))
    sc.set_selection(["x", "x", "y"])
    assert sc.selected_clip_ids() == ["x", "y"]
    assert events["count"] == 1
    sc.set_selection(["x", "y"])
    assert events["count"] == 1


def test_delete_selected_clip_removes_multiple_clips() -> None:
    timeline_controller, selection_controller, project_controller = _wired_controllers()
    project = project_controller.active_project()
    assert project is not None

    track = next(track for track in project.timeline.tracks if len(track.clips) >= 2)
    first = track.clips[0].clip_id
    second = track.clips[1].clip_id
    selection_controller.set_selection([first, second])

    assert timeline_controller.delete_selected_clip()
    remaining_ids = {clip.clip_id for t in project.timeline.tracks for clip in t.clips}
    assert first not in remaining_ids
    assert second not in remaining_ids
    assert selection_controller.selected_clip_ids() == []


def test_set_clip_transform_updates_visual_fields() -> None:
    timeline_controller, _selection_controller, project_controller = _wired_controllers()
    project = project_controller.active_project()
    assert project is not None
    clip = next(
        clip
        for track in project.timeline.tracks
        for clip in track.clips
        if isinstance(clip, (VideoClip, ImageClip))
    )

    assert timeline_controller.set_clip_transform(
        clip.clip_id,
        position_x=0.82,
        position_y=0.18,
        scale=1.8,
        rotation=22.5,
    )
    clip_after = next(
        candidate
        for track in project.timeline.tracks
        for candidate in track.clips
        if candidate.clip_id == clip.clip_id
    )
    assert abs(float(getattr(clip_after, "position_x", 0.0)) - 0.82) < 1e-6
    assert abs(float(getattr(clip_after, "position_y", 0.0)) - 0.18) < 1e-6
    assert abs(float(getattr(clip_after, "scale", 0.0)) - 1.8) < 1e-6


def test_project_service_roundtrip_transform_fields(tmp_path) -> None:
    project = build_demo_project()
    clip = next(
        clip
        for track in project.timeline.tracks
        for clip in track.clips
        if isinstance(clip, VideoClip)
    )
    clip.position_x = 0.77
    clip.position_y = 0.11
    clip.scale = 1.4
    clip.rotation = 14.0

    service = ProjectService()
    target = tmp_path / "roundtrip.json"
    service.save_project(project, str(target))
    loaded = service.load_project(str(target))
    loaded_clip = next(
        candidate
        for track in loaded.timeline.tracks
        for candidate in track.clips
        if candidate.clip_id == clip.clip_id
    )
    assert isinstance(loaded_clip, VideoClip)
    assert loaded_clip.position_x == 0.77
    assert loaded_clip.position_y == 0.11
    assert loaded_clip.scale == 1.4
    assert loaded_clip.rotation == 14.0


def test_export_service_build_command_respects_options() -> None:
    project = build_demo_project()
    service = ExportService(ffmpeg_executable="ffmpeg")
    options = ExportOptions(
        in_point_seconds=1.0,
        out_point_seconds=4.0,
        width_override=1280,
        height_override=720,
        fps_override=30.0,
        codec="libx265",
        preset="fast",
        crf=28,
    )
    patched_project = service._apply_options_to_project(project, options)
    command = service._build_ffmpeg_command(
        patched_project,
        target_path=(Path.cwd() / "dummy.mp4"),
        warnings=[],
        project_root=None,
        options=options,
        in_point=1.0,
        out_point=4.0,
    )
    assert "-c:v" in command
    codec_index = command.index("-c:v") + 1
    assert command[codec_index] == "libx265"
    assert "-preset" in command and "fast" in command
    assert "-crf" in command and "28" in command
    assert "-ss" in command and "1.000000" in command
    assert "-t" in command and "3.000000" in command


def test_project_controller_set_project_resolution() -> None:
    pc = ProjectController()
    project = build_demo_project()
    pc.set_active_project(project)
    assert pc.set_project_resolution(1234, 567)
    assert project.width == 1234
    assert project.height == 567
    assert not pc.set_project_resolution(1234, 567)
