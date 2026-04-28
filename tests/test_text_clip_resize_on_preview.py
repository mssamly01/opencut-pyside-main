"""Resize TextClip via TimelineController.set_clip_transform(font_size=...).

Backs the preview-canvas drag-corner gesture: when the user drags a
corner of a selected TextClip on the video preview, the canvas calls
``set_clip_transform(clip_id, font_size=…)`` to grow/shrink the rendered
text. These tests exercise the controller surface directly.
"""

from __future__ import annotations

from app.controllers.project_controller import ProjectController
from app.controllers.selection_controller import SelectionController
from app.controllers.timeline_controller import TimelineController
from app.domain.clips.text_clip import TextClip
from app.domain.project import build_demo_project


def _build() -> tuple[TimelineController, TextClip]:
    project_controller = ProjectController()
    project_controller.set_active_project(build_demo_project())
    selection_controller = SelectionController()
    timeline_controller = TimelineController(
        project_controller=project_controller,
        selection_controller=selection_controller,
    )
    project = project_controller.active_project()
    assert project is not None
    text_clip = next(
        (clip for track in project.timeline.tracks for clip in track.clips if isinstance(clip, TextClip)),
        None,
    )
    assert text_clip is not None, "build_demo_project must contain at least one TextClip"
    return timeline_controller, text_clip


def test_set_clip_transform_updates_text_clip_font_size() -> None:
    timeline_controller, text_clip = _build()
    original = text_clip.font_size

    ok = timeline_controller.set_clip_transform(text_clip.clip_id, font_size=original + 24)

    assert ok is True
    assert text_clip.font_size == original + 24


def test_font_size_clamped_to_min_when_drag_goes_negative() -> None:
    timeline_controller, text_clip = _build()
    timeline_controller.set_clip_transform(text_clip.clip_id, font_size=-10)
    assert text_clip.font_size == 8  # min clamp


def test_font_size_clamped_to_max() -> None:
    timeline_controller, text_clip = _build()
    timeline_controller.set_clip_transform(text_clip.clip_id, font_size=10_000)
    assert text_clip.font_size == 800  # max clamp


def test_font_size_no_op_when_unchanged() -> None:
    timeline_controller, text_clip = _build()
    original = text_clip.font_size
    ok = timeline_controller.set_clip_transform(text_clip.clip_id, font_size=original)
    assert ok is False
    assert text_clip.font_size == original


def test_font_size_change_is_undoable() -> None:
    timeline_controller, text_clip = _build()
    original = text_clip.font_size
    timeline_controller.set_clip_transform(text_clip.clip_id, font_size=original + 30)
    assert text_clip.font_size == original + 30
    timeline_controller.undo()
    assert text_clip.font_size == original
    timeline_controller.redo()
    assert text_clip.font_size == original + 30


def test_position_and_font_size_combined_in_one_command() -> None:
    """A combined drag (move + resize) should batch into one undoable
    command so the user gets a single Ctrl+Z instead of two."""

    timeline_controller, text_clip = _build()
    original_size = text_clip.font_size
    original_x = text_clip.position_x

    timeline_controller.set_clip_transform(
        text_clip.clip_id,
        position_x=original_x + 0.1,
        font_size=original_size + 10,
    )

    assert text_clip.font_size == original_size + 10
    assert text_clip.position_x == original_x + 0.1

    timeline_controller.undo()
    assert text_clip.font_size == original_size
    assert text_clip.position_x == original_x


def test_font_size_skipped_for_non_text_clip() -> None:
    """Non-text clips don't have ``font_size`` and the call must
    silently ignore the parameter, not raise."""

    project_controller = ProjectController()
    project_controller.set_active_project(build_demo_project())
    selection_controller = SelectionController()
    timeline_controller = TimelineController(
        project_controller=project_controller,
        selection_controller=selection_controller,
    )
    project = project_controller.active_project()
    assert project is not None
    video_clip = next(
        (clip for track in project.timeline.tracks for clip in track.clips if not isinstance(clip, TextClip)),
        None,
    )
    assert video_clip is not None

    ok = timeline_controller.set_clip_transform(video_clip.clip_id, font_size=99)

    # No font_size attr → no update applied → returns False.
    assert ok is False
    assert not hasattr(video_clip, "font_size")
