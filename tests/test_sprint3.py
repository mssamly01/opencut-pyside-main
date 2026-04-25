from __future__ import annotations

import pytest
from app.controllers.playback_controller import PlaybackController
from app.controllers.project_controller import ProjectController
from app.controllers.selection_controller import SelectionController
from app.controllers.timeline_controller import TimelineController
from app.domain.clips.video_clip import VideoClip
from app.domain.commands import (
    AddKeyframeCommand,
    CommandManager,
    MoveKeyframeCommand,
    UpdateKeyframeValueCommand,
)
from app.domain.keyframe import AnimatedProperty, Keyframe
from app.domain.project import build_demo_project
from app.services.keyframe_evaluator import (
    clip_has_keyframes,
    ffmpeg_piecewise_expression,
    resolve_clip_value_at,
)
from app.services.project_service import ProjectService
from app.ui.inspector.animation_inspector import AnimationInspector
from PySide6.QtWidgets import QApplication


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


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


def _sample_video_clip() -> VideoClip:
    return VideoClip(
        clip_id="clip_keyframe",
        name="Sample",
        track_id="track_video",
        timeline_start=0.0,
        duration=4.0,
        media_id=None,
    )


def test_animated_property_empty_returns_default() -> None:
    prop = AnimatedProperty([])
    assert prop.value_at(1.0, default=2.5) == pytest.approx(2.5)


def test_animated_property_linear_interpolation() -> None:
    prop = AnimatedProperty(
        [
            Keyframe(time_seconds=0.0, value=1.0),
            Keyframe(time_seconds=2.0, value=3.0),
        ]
    )
    assert prop.value_at(0.0, default=0.0) == pytest.approx(1.0)
    assert prop.value_at(1.0, default=0.0) == pytest.approx(2.0)
    assert prop.value_at(2.0, default=0.0) == pytest.approx(3.0)


def test_animated_property_hold_interpolation() -> None:
    prop = AnimatedProperty(
        [
            Keyframe(time_seconds=0.0, value=2.0, interpolation="hold"),
            Keyframe(time_seconds=2.0, value=6.0),
        ]
    )
    assert prop.value_at(1.0, default=0.0) == pytest.approx(2.0)
    assert prop.value_at(2.0, default=0.0) == pytest.approx(6.0)


def test_add_keyframe_command_undo_redo() -> None:
    clip = _sample_video_clip()
    manager = CommandManager()
    manager.execute(AddKeyframeCommand(clip, "scale", Keyframe(time_seconds=1.0, value=1.8)))
    assert len(clip.scale_keyframes) == 1
    assert clip.scale_keyframes[0].value == pytest.approx(1.8)

    manager.undo()
    assert clip.scale_keyframes == []

    manager.redo()
    assert len(clip.scale_keyframes) == 1
    assert clip.scale_keyframes[0].value == pytest.approx(1.8)


def test_move_keyframe_command_and_undo() -> None:
    clip = _sample_video_clip()
    manager = CommandManager()
    manager.execute(AddKeyframeCommand(clip, "scale", Keyframe(time_seconds=0.5, value=1.0)))
    manager.execute(AddKeyframeCommand(clip, "scale", Keyframe(time_seconds=2.0, value=2.0)))

    manager.execute(MoveKeyframeCommand(clip, "scale", 0.5, 3.0))
    assert [kf.time_seconds for kf in clip.scale_keyframes] == [2.0, 3.0]

    manager.undo()
    assert [kf.time_seconds for kf in clip.scale_keyframes] == [0.5, 2.0]


def test_update_keyframe_value_command_undo() -> None:
    clip = _sample_video_clip()
    manager = CommandManager()
    manager.execute(AddKeyframeCommand(clip, "scale", Keyframe(time_seconds=1.0, value=1.0)))
    manager.execute(UpdateKeyframeValueCommand(clip, "scale", 1.0, 2.5))
    assert clip.scale_keyframes[0].value == pytest.approx(2.5)

    manager.undo()
    assert clip.scale_keyframes[0].value == pytest.approx(1.0)


def test_keyframe_evaluator_and_expression_helpers() -> None:
    clip = _sample_video_clip()
    clip.scale = 1.25
    assert resolve_clip_value_at(clip, "scale", 1.0, default=1.0) == pytest.approx(1.25)
    assert not clip_has_keyframes(clip, "scale")

    clip.scale_keyframes.append(Keyframe(0.0, 1.0))
    clip.scale_keyframes.append(Keyframe(2.0, 3.0))
    assert clip_has_keyframes(clip, "scale")
    assert resolve_clip_value_at(clip, "scale", 1.0, default=1.0) == pytest.approx(2.0)

    expression = ffmpeg_piecewise_expression(clip.scale_keyframes, default_value=1.0, clip_duration=4.0)
    assert "if(lt(t" in expression
    assert "3.000000" in expression


def test_project_service_roundtrips_keyframes(tmp_path) -> None:
    project = build_demo_project()
    video_clip = next(
        clip
        for track in project.timeline.tracks
        for clip in track.clips
        if isinstance(clip, VideoClip)
    )
    video_clip.scale_keyframes.append(
        Keyframe(time_seconds=0.3, value=1.4, interpolation="ease_in")
    )
    video_clip.scale_keyframes.append(Keyframe(time_seconds=1.2, value=0.8))

    service = ProjectService()
    target = tmp_path / "keyframe_roundtrip.json"
    service.save_project(project, str(target))
    loaded = service.load_project(str(target))

    loaded_clip = next(
        clip
        for track in loaded.timeline.tracks
        for clip in track.clips
        if clip.clip_id == video_clip.clip_id
    )
    assert isinstance(loaded_clip, VideoClip)
    assert len(loaded_clip.scale_keyframes) == 2
    assert loaded_clip.scale_keyframes[0].interpolation == "ease_in"
    assert loaded_clip.scale_keyframes[1].value == pytest.approx(0.8)


def test_timeline_controller_keyframe_api_and_auto_keyframe() -> None:
    timeline_controller, _selection, project_controller = _wired_controllers()
    project = project_controller.active_project()
    assert project is not None
    clip = next(
        clip
        for track in project.timeline.tracks
        for clip in track.clips
        if isinstance(clip, VideoClip)
    )

    added = timeline_controller.add_keyframe(clip.clip_id, "scale", 0.4, 1.6)
    assert added
    assert len(clip.scale_keyframes) == 1

    timeline_controller.set_playhead_seconds(clip.timeline_start + 1.0)
    timeline_controller.set_auto_keyframe_enabled(True)
    changed = timeline_controller.set_clip_transform(clip.clip_id, scale=2.0)
    assert changed
    assert clip.scale == pytest.approx(2.0)
    assert len(clip.scale_keyframes) >= 2
    assert any(abs(kf.time_seconds - 1.0) <= 1e-3 for kf in clip.scale_keyframes)


def test_animation_inspector_smoke(qapp: QApplication) -> None:
    timeline_controller, _selection, project_controller = _wired_controllers()
    playback_controller = PlaybackController(project_controller=project_controller)
    project = project_controller.active_project()
    assert project is not None
    clip = next(
        clip
        for track in project.timeline.tracks
        for clip in track.clips
        if isinstance(clip, VideoClip)
    )

    widget = AnimationInspector(
        timeline_controller=timeline_controller,
        playback_controller=playback_controller,
        clip=clip,
    )
    widget.show()
    qapp.processEvents()

    assert widget is not None
    assert widget.isVisible()
    widget.deleteLater()
