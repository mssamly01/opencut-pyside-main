"""Sprint 16-C1: Effects/Transitions split + clip color sliders (eq/hue)."""

from __future__ import annotations

from app.bootstrap import build_app_context, build_main_window, create_application
from app.domain.clips.image_clip import ImageClip
from app.domain.clips.video_clip import VideoClip
from app.services.export_service import ExportService
from app.ui.sidebar.effects_panel import EffectsPanel
from app.ui.sidebar.transitions_panel import TransitionsPanel


def _make_video_clip(**overrides: object) -> VideoClip:
    return VideoClip(
        clip_id=str(overrides.pop("clip_id", "v1")),
        name=str(overrides.pop("name", "v1")),
        track_id=str(overrides.pop("track_id", "t1")),
        timeline_start=float(overrides.pop("timeline_start", 0.0)),
        duration=float(overrides.pop("duration", 1.0)),
        **overrides,  # type: ignore[arg-type]
    )


def _make_image_clip(**overrides: object) -> ImageClip:
    return ImageClip(
        clip_id=str(overrides.pop("clip_id", "i1")),
        name=str(overrides.pop("name", "i1")),
        track_id=str(overrides.pop("track_id", "t1")),
        timeline_start=float(overrides.pop("timeline_start", 0.0)),
        duration=float(overrides.pop("duration", 1.0)),
        **overrides,  # type: ignore[arg-type]
    )


def test_video_clip_defaults_color_fields() -> None:
    clip = _make_video_clip()
    assert clip.brightness == 0.0
    assert clip.contrast == 1.0
    assert clip.saturation == 1.0
    assert clip.hue == 0.0


def test_image_clip_defaults_color_fields() -> None:
    clip = _make_image_clip()
    assert clip.brightness == 0.0
    assert clip.contrast == 1.0
    assert clip.saturation == 1.0
    assert clip.hue == 0.0


def test_color_adjust_filters_empty_at_defaults() -> None:
    assert ExportService._color_adjust_filters_for_clip(_make_video_clip()) == []
    assert ExportService._color_adjust_filters_for_clip(_make_image_clip()) == []


def test_color_adjust_filters_emit_eq_when_changed() -> None:
    clip = _make_video_clip(brightness=0.25, contrast=1.5, saturation=0.7, hue=0.0)
    filters = ExportService._color_adjust_filters_for_clip(clip)
    assert len(filters) == 1
    eq_filter = filters[0]
    assert eq_filter.startswith("eq=")
    assert "brightness=0.250000" in eq_filter
    assert "contrast=1.500000" in eq_filter
    assert "saturation=0.700000" in eq_filter


def test_color_adjust_filters_emit_hue_separately() -> None:
    clip = _make_video_clip(hue=45.0)
    filters = ExportService._color_adjust_filters_for_clip(clip)
    assert filters == ["hue=h=45.000000"]


def test_color_adjust_filters_emit_eq_and_hue_together() -> None:
    clip = _make_video_clip(brightness=-0.1, hue=-30.0)
    filters = ExportService._color_adjust_filters_for_clip(clip)
    assert filters == ["eq=brightness=-0.100000", "hue=h=-30.000000"]


def test_left_sidebar_stack_transitions_panel_uses_separate_class() -> None:
    create_application(["pytest"])
    window = build_main_window()
    try:
        sidebar = window._app_shell.left_sidebar_stack
        assert isinstance(sidebar.transitions_panel, TransitionsPanel)
        assert isinstance(sidebar.effects_panel, EffectsPanel)
        # Critical: the two panels must not be the same class anymore.
        assert type(sidebar.transitions_panel) is not type(sidebar.effects_panel)
    finally:
        window.close()


def test_effects_panel_has_four_color_sliders() -> None:
    create_application(["pytest"])
    context = build_app_context()
    panel = EffectsPanel(context.app_controller)
    try:
        for name in ("brightness", "contrast", "saturation", "hue"):
            slider = panel.slider_for(name)
            assert slider is not None
        # Disabled when no clip is selected.
        assert not panel.slider_for("brightness").isEnabled()
    finally:
        panel.deleteLater()


def test_effects_panel_disabled_for_audio_or_no_selection() -> None:
    create_application(["pytest"])
    context = build_app_context()
    panel = EffectsPanel(context.app_controller)
    try:
        # No selection -> disabled.
        assert not panel.slider_for("brightness").isEnabled()
        # Selecting a non-existent clip -> still disabled.
        context.app_controller.selection_controller.select_clip("does-not-exist")
        assert not panel.slider_for("brightness").isEnabled()
    finally:
        panel.deleteLater()


def test_effects_panel_slider_release_executes_undoable_command() -> None:
    create_application(["pytest"])
    context = build_app_context()
    app_controller = context.app_controller
    project = app_controller.project_controller.active_project()
    assert project is not None
    timeline = project.timeline
    track = timeline.tracks[0]
    clip = _make_video_clip(clip_id="c-color", track_id=track.track_id, duration=2.0)
    track.clips.append(clip)
    app_controller.timeline_controller.timeline_changed.emit()
    app_controller.selection_controller.select_clip(clip.clip_id)

    panel = EffectsPanel(app_controller)
    try:
        slider = panel.slider_for("brightness")
        assert slider.isEnabled()
        # Simulate a drag: press, move slider to value, release.
        panel._on_slider_pressed("brightness")
        slider.setValue(40)  # -> attr 0.4
        # Live preview applied directly.
        assert abs(clip.brightness - 0.4) < 1e-6
        panel._on_slider_released("brightness")
        # After release: clip still at 0.4, command pushed; undo restores 0.0.
        assert abs(clip.brightness - 0.4) < 1e-6
        app_controller.timeline_controller._command_manager.undo()
        assert abs(clip.brightness - 0.0) < 1e-6
        app_controller.timeline_controller._command_manager.redo()
        assert abs(clip.brightness - 0.4) < 1e-6
    finally:
        panel.deleteLater()


def test_effects_panel_reset_button_clears_all_attrs() -> None:
    create_application(["pytest"])
    context = build_app_context()
    app_controller = context.app_controller
    project = app_controller.project_controller.active_project()
    assert project is not None
    track = project.timeline.tracks[0]
    clip = _make_video_clip(
        clip_id="c-reset",
        track_id=track.track_id,
        duration=2.0,
        brightness=0.3,
        contrast=1.4,
        saturation=0.5,
        hue=20.0,
    )
    track.clips.append(clip)
    app_controller.timeline_controller.timeline_changed.emit()
    app_controller.selection_controller.select_clip(clip.clip_id)

    panel = EffectsPanel(app_controller)
    try:
        panel._on_reset_clicked()
        assert clip.brightness == 0.0
        assert clip.contrast == 1.0
        assert clip.saturation == 1.0
        assert clip.hue == 0.0
    finally:
        panel.deleteLater()


def test_project_service_round_trip_preserves_color_fields(tmp_path) -> None:
    from app.domain.project import Project
    from app.domain.timeline import Timeline
    from app.domain.track import Track
    from app.services.project_service import ProjectService

    track = Track(track_id="t1", name="T1", track_type="video", clips=[
        _make_video_clip(
            clip_id="c1",
            track_id="t1",
            brightness=0.2,
            contrast=1.3,
            saturation=0.8,
            hue=15.0,
        ),
        _make_image_clip(
            clip_id="c2",
            track_id="t1",
            brightness=-0.4,
            contrast=0.9,
            saturation=2.0,
            hue=-90.0,
        ),
    ])
    timeline = Timeline(tracks=[track])
    project = Project(
        project_id="p1",
        name="p",
        width=1920,
        height=1080,
        fps=30.0,
        timeline=timeline,
    )

    path = tmp_path / "p.json"
    service = ProjectService()
    service.save_project(project, file_path=str(path))
    loaded = service.load_project(str(path))
    loaded_clips = list(loaded.timeline.tracks[0].clips)
    assert isinstance(loaded_clips[0], VideoClip)
    assert loaded_clips[0].brightness == 0.2
    assert loaded_clips[0].contrast == 1.3
    assert loaded_clips[0].saturation == 0.8
    assert loaded_clips[0].hue == 15.0
    assert isinstance(loaded_clips[1], ImageClip)
    assert loaded_clips[1].brightness == -0.4
    assert loaded_clips[1].contrast == 0.9
    assert loaded_clips[1].saturation == 2.0
    assert loaded_clips[1].hue == -90.0
