from __future__ import annotations

import pytest
from app.controllers.app_controller import AppController
from app.domain.clips.video_clip import VideoClip
from app.domain.commands import (
    AddTransitionCommand,
    ChangeTransitionTypeCommand,
    CommandManager,
    RemoveTransitionCommand,
    UpdateTransitionDurationCommand,
)
from app.domain.keyframe import AnimatedProperty, Keyframe, _cubic_bezier
from app.domain.project import build_demo_project
from app.domain.track import Track
from app.domain.transition import (
    DEFAULT_TRANSITION_DURATION,
    MAX_TRANSITION_DURATION,
    Transition,
    make_transition,
)
from app.services.keyframe_evaluator import ffmpeg_piecewise_expression
from app.services.project_service import ProjectService
from app.services.transition_service import (
    find_transition,
    is_pair_adjacent,
    max_transition_duration,
    transition_for_clip_pair,
)
from PySide6.QtWidgets import QApplication


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _transition_ready_track() -> Track:
    return Track(
        track_id="tr1",
        name="Main",
        track_type="video",
        clips=[
            VideoClip(
                clip_id="a",
                name="A",
                track_id="tr1",
                timeline_start=0.0,
                duration=2.0,
            ),
            VideoClip(
                clip_id="b",
                name="B",
                track_id="tr1",
                timeline_start=2.0,
                duration=3.0,
            ),
        ],
    )


def test_transition_validates_type() -> None:
    with pytest.raises(ValueError):
        Transition(
            transition_id="t1",
            transition_type="bogus",
            duration_seconds=0.5,
            from_clip_id="a",
            to_clip_id="b",
        )


def test_transition_clamps_duration() -> None:
    transition = make_transition("cross_dissolve", "a", "b", duration_seconds=10.0)
    assert transition.duration_seconds == MAX_TRANSITION_DURATION


def test_make_transition_default_duration() -> None:
    transition = make_transition("fade_to_black", "a", "b")
    assert transition.duration_seconds == DEFAULT_TRANSITION_DURATION


def test_add_transition_command_undo_redo() -> None:
    track = _transition_ready_track()
    transition = make_transition("cross_dissolve", "a", "b")
    manager = CommandManager()
    manager.execute(AddTransitionCommand(track, transition))
    assert len(track.transitions) == 1
    manager.undo()
    assert track.transitions == []
    manager.redo()
    assert len(track.transitions) == 1


def test_remove_transition_command_undo() -> None:
    track = _transition_ready_track()
    transition = make_transition("cross_dissolve", "a", "b")
    track.transitions.append(transition)
    manager = CommandManager()
    manager.execute(RemoveTransitionCommand(track, transition.transition_id))
    assert track.transitions == []
    manager.undo()
    assert len(track.transitions) == 1


def test_update_transition_duration_command() -> None:
    track = _transition_ready_track()
    transition = make_transition("cross_dissolve", "a", "b", duration_seconds=0.5)
    track.transitions.append(transition)
    manager = CommandManager()
    manager.execute(UpdateTransitionDurationCommand(track, transition.transition_id, 1.0))
    assert transition.duration_seconds == pytest.approx(1.0)
    manager.undo()
    assert transition.duration_seconds == pytest.approx(0.5)


def test_change_transition_type_command() -> None:
    track = _transition_ready_track()
    transition = make_transition("cross_dissolve", "a", "b")
    track.transitions.append(transition)
    manager = CommandManager()
    manager.execute(ChangeTransitionTypeCommand(track, transition.transition_id, "slide_left"))
    assert transition.transition_type == "slide_left"
    manager.undo()
    assert transition.transition_type == "cross_dissolve"


def test_transition_service_helpers() -> None:
    track = _transition_ready_track()
    assert is_pair_adjacent(track, "a", "b") is True
    assert max_transition_duration(track, "a", "b") == pytest.approx(1.0)

    transition = make_transition("slide_left", "a", "b")
    track.transitions.append(transition)
    assert transition_for_clip_pair(track, "a", "b") is transition
    assert transition_for_clip_pair(track, "b", "a") is None
    assert find_transition(track, transition.transition_id) is transition


def test_cubic_bezier_endpoints() -> None:
    assert _cubic_bezier(0.0, 0.42, 0.0, 0.58, 1.0) == pytest.approx(0.0, abs=1e-3)
    assert _cubic_bezier(1.0, 0.42, 0.0, 0.58, 1.0) == pytest.approx(1.0, abs=1e-3)


def test_animated_property_bezier_monotonic() -> None:
    prop = AnimatedProperty(
        [
            Keyframe(0.0, 0.0, interpolation="bezier"),
            Keyframe(1.0, 10.0),
        ]
    )
    samples = [prop.value_at(t / 10.0, 0.0) for t in range(11)]
    assert samples[0] == pytest.approx(0.0, abs=1e-2)
    assert samples[-1] == pytest.approx(10.0, abs=1e-2)
    for prev, nxt in zip(samples, samples[1:], strict=False):
        assert nxt >= prev - 1e-3


def test_ffmpeg_piecewise_expression_handles_bezier() -> None:
    keyframes = [
        Keyframe(0.0, 0.0, interpolation="bezier"),
        Keyframe(2.0, 4.0),
    ]
    expression = ffmpeg_piecewise_expression(
        keyframes,
        default_value=0.0,
        clip_duration=2.0,
    )
    assert expression.count("if(lt(t\\,") >= 8


def test_project_service_roundtrips_transitions_and_bezier(tmp_path) -> None:
    project = build_demo_project()
    video_track = next(track for track in project.timeline.tracks if track.track_type == "video")
    a, b = video_track.sorted_clips()[0], video_track.sorted_clips()[1]
    video_track.transitions.append(
        make_transition("cross_dissolve", a.clip_id, b.clip_id, 0.7)
    )
    a.scale_keyframes.append(
        Keyframe(
            time_seconds=0.3,
            value=1.4,
            interpolation="bezier",
            bezier_cp1_dx=0.2,
            bezier_cp1_dy=0.1,
            bezier_cp2_dx=0.8,
            bezier_cp2_dy=1.1,
        )
    )
    a.scale_keyframes.append(Keyframe(time_seconds=1.2, value=0.8))

    service = ProjectService()
    save_path = tmp_path / "demo_with_transition.json"
    service.save_project(project, str(save_path))
    loaded = service.load_project(str(save_path))

    loaded_track = next(track for track in loaded.timeline.tracks if track.track_type == "video")
    assert len(loaded_track.transitions) == 1
    assert loaded_track.transitions[0].transition_type == "cross_dissolve"
    assert loaded_track.transitions[0].duration_seconds == pytest.approx(0.7)

    loaded_clip = next(clip for clip in loaded_track.clips if clip.clip_id == a.clip_id)
    assert len(loaded_clip.scale_keyframes) == 2
    first = loaded_clip.scale_keyframes[0]
    assert first.interpolation == "bezier"
    assert first.bezier_cp1_dx == pytest.approx(0.2)
    assert first.bezier_cp2_dy == pytest.approx(1.1)


def test_timeline_controller_add_transition_and_undo(qapp: QApplication) -> None:
    _ = qapp
    controller = AppController()
    controller.project_controller.load_demo_project()
    timeline = controller.project_controller.active_project().timeline
    video_track = next(track for track in timeline.tracks if track.track_type == "video")
    a, b = video_track.sorted_clips()[0], video_track.sorted_clips()[1]

    ok = controller.timeline_controller.add_transition(
        video_track.track_id,
        a.clip_id,
        b.clip_id,
        "fade_to_black",
        duration_seconds=0.5,
    )
    assert ok is True
    assert len(video_track.transitions) == 1

    controller.timeline_controller.undo()
    assert len(video_track.transitions) == 0
