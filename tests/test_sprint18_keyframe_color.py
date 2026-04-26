"""Sprint 18: animatable color sliders (keyframes for brightness/contrast/saturation/hue).

Verifies the domain/export/preview/save-load wiring plus the EffectsPanel pin
diamond UX (add/remove keyframe, drag slider with keyframes, reset clears
keyframes too).
"""

from __future__ import annotations

from app.bootstrap import build_app_context, build_main_window, create_application
from app.domain.clips.image_clip import ImageClip
from app.domain.clips.video_clip import VideoClip
from app.domain.keyframe import Keyframe
from app.domain.project import Project
from app.domain.timeline import Timeline
from app.domain.track import Track
from app.services.export_service import ExportService
from app.services.project_service import ProjectService


def _video(**overrides: object) -> VideoClip:
    return VideoClip(
        clip_id=str(overrides.pop("clip_id", "v1")),
        name=str(overrides.pop("name", "v1")),
        track_id=str(overrides.pop("track_id", "t1")),
        timeline_start=float(overrides.pop("timeline_start", 0.0)),
        duration=float(overrides.pop("duration", 4.0)),
        **overrides,  # type: ignore[arg-type]
    )


def _image(**overrides: object) -> ImageClip:
    return ImageClip(
        clip_id=str(overrides.pop("clip_id", "i1")),
        name=str(overrides.pop("name", "i1")),
        track_id=str(overrides.pop("track_id", "t1")),
        timeline_start=float(overrides.pop("timeline_start", 0.0)),
        duration=float(overrides.pop("duration", 2.0)),
        **overrides,  # type: ignore[arg-type]
    )


# --- Domain ---------------------------------------------------------------


def test_video_clip_color_keyframe_lists_default_empty() -> None:
    clip = _video()
    assert clip.brightness_keyframes == []
    assert clip.contrast_keyframes == []
    assert clip.saturation_keyframes == []
    assert clip.hue_keyframes == []


def test_image_clip_color_keyframe_lists_default_empty() -> None:
    clip = _image()
    assert clip.brightness_keyframes == []
    assert clip.contrast_keyframes == []
    assert clip.saturation_keyframes == []
    assert clip.hue_keyframes == []


# --- Export: time-varying expressions -------------------------------------


def test_export_emits_brightness_expression_with_eval_frame() -> None:
    clip = _video(
        brightness=0.0,
        brightness_keyframes=[
            Keyframe(time_seconds=0.0, value=-0.3),
            Keyframe(time_seconds=2.0, value=0.4),
        ],
    )
    filters = ExportService._color_adjust_filters_for_clip(clip)
    assert len(filters) == 1
    eq = filters[0]
    assert eq.startswith("eq=brightness=")
    assert ":eval=frame" in eq
    # The expression must reference ffmpeg's `t` (i.e. is not a constant).
    assert "(t-" in eq


def test_export_mixes_animated_and_static_channels() -> None:
    """One animated channel turns the whole eq into eval=frame mode but keeps
    the static channel as a literal value."""
    clip = _video(
        brightness_keyframes=[
            Keyframe(time_seconds=0.0, value=0.0),
            Keyframe(time_seconds=1.0, value=0.5),
        ],
        contrast=1.5,  # static
    )
    filters = ExportService._color_adjust_filters_for_clip(clip)
    eq = next(f for f in filters if f.startswith("eq="))
    assert "brightness=" in eq
    assert "contrast=1.500000" in eq
    assert ":eval=frame" in eq


def test_export_animated_hue_uses_eval_frame() -> None:
    clip = _video(
        hue_keyframes=[
            Keyframe(time_seconds=0.0, value=-30.0),
            Keyframe(time_seconds=2.0, value=30.0),
        ],
    )
    filters = ExportService._color_adjust_filters_for_clip(clip)
    hue = next(f for f in filters if f.startswith("hue=h="))
    assert ":eval=frame" in hue
    assert "(t-" in hue  # expression, not a constant


def test_export_no_keyframes_keeps_constant_eq() -> None:
    """Sprint 16-C1 behaviour must be unchanged when no keyframes exist."""
    clip = _video(brightness=0.25, contrast=1.5)
    filters = ExportService._color_adjust_filters_for_clip(clip)
    assert filters == ["eq=brightness=0.250000:contrast=1.500000"]


# --- Preview: baked-at-time constants -------------------------------------


def test_preview_bakes_keyframed_brightness_at_given_time() -> None:
    """time_in_clip=0.0 -> -0.3, time_in_clip=2.0 -> 0.4 (linear interp midpoint -> 0.05)."""
    clip = _video(
        brightness_keyframes=[
            Keyframe(time_seconds=0.0, value=-0.3),
            Keyframe(time_seconds=2.0, value=0.4),
        ],
    )
    f0 = ExportService._color_adjust_filters_for_clip(clip, time_in_clip=0.0)
    f1 = ExportService._color_adjust_filters_for_clip(clip, time_in_clip=1.0)
    f2 = ExportService._color_adjust_filters_for_clip(clip, time_in_clip=2.0)
    # No `eval=frame` and no `(t-` expression — preview emits a constant.
    for filters in (f0, f1, f2):
        assert all(":eval=frame" not in f for f in filters)
        assert all("(t-" not in f for f in filters)
    assert "brightness=-0.300000" in f0[0]
    assert "brightness=0.050000" in f1[0]
    assert "brightness=0.400000" in f2[0]


def test_preview_clip_with_no_keyframes_unchanged() -> None:
    clip = _video(brightness=0.25)
    f = ExportService._color_adjust_filters_for_clip(clip, time_in_clip=1.5)
    assert f == ["eq=brightness=0.250000"]


# --- Save / load ----------------------------------------------------------


def test_project_service_round_trip_preserves_color_keyframes(tmp_path) -> None:
    track = Track(
        track_id="t1",
        name="T1",
        track_type="video",
        clips=[
            _video(
                clip_id="c1",
                track_id="t1",
                brightness_keyframes=[
                    Keyframe(time_seconds=0.0, value=-0.2),
                    Keyframe(time_seconds=1.5, value=0.3),
                ],
                hue_keyframes=[Keyframe(time_seconds=1.0, value=45.0)],
            ),
            _image(
                clip_id="c2",
                track_id="t1",
                contrast_keyframes=[
                    Keyframe(time_seconds=0.0, value=0.8),
                    Keyframe(time_seconds=1.0, value=1.4),
                ],
            ),
        ],
    )
    project = Project(
        project_id="p1",
        name="p1",
        width=640,
        height=360,
        fps=30.0,
        timeline=Timeline(tracks=[track]),
    )
    service = ProjectService()
    path = tmp_path / "demo.opencut.json"
    service.save_project(project, str(path))
    loaded = service.load_project(str(path))
    assert loaded is not None
    loaded_video = loaded.timeline.tracks[0].clips[0]
    loaded_image = loaded.timeline.tracks[0].clips[1]
    assert isinstance(loaded_video, VideoClip)
    assert isinstance(loaded_image, ImageClip)
    assert [kf.value for kf in loaded_video.brightness_keyframes] == [-0.2, 0.3]
    assert [kf.time_seconds for kf in loaded_video.brightness_keyframes] == [0.0, 1.5]
    assert [kf.value for kf in loaded_video.hue_keyframes] == [45.0]
    assert [kf.value for kf in loaded_image.contrast_keyframes] == [0.8, 1.4]


# --- UI: pin diamond / slider auto-keyframe -------------------------------


def _setup_panel():
    from app.ui.sidebar.effects_panel import EffectsPanel

    create_application(["pytest"])
    context = build_app_context()
    app_controller = context.app_controller
    project = app_controller.project_controller.active_project()
    assert project is not None
    track = project.timeline.tracks[0]
    clip = _video(clip_id="c-kf", track_id=track.track_id, duration=4.0)
    track.clips.append(clip)
    app_controller.timeline_controller.timeline_changed.emit()
    app_controller.selection_controller.select_clip(clip.clip_id)
    panel = EffectsPanel(app_controller)
    return app_controller, clip, panel


def test_pin_click_adds_keyframe_at_playhead() -> None:
    app_controller, clip, panel = _setup_panel()
    try:
        app_controller.timeline_controller.set_playhead_seconds(1.0)
        panel.slider_for("brightness").setValue(40)  # -> 0.4
        panel._on_pin_clicked("brightness")
        assert len(clip.brightness_keyframes) == 1
        kf = clip.brightness_keyframes[0]
        assert abs(kf.time_seconds - 1.0) < 1e-3
        assert abs(kf.value - 0.4) < 1e-3
        # Undoable.
        app_controller.timeline_controller._command_manager.undo()
        assert clip.brightness_keyframes == []
    finally:
        panel.deleteLater()


def test_pin_click_at_existing_time_removes_keyframe() -> None:
    app_controller, clip, panel = _setup_panel()
    try:
        clip.brightness_keyframes.append(Keyframe(time_seconds=1.0, value=0.5))
        app_controller.timeline_controller.set_playhead_seconds(1.0)
        panel._on_pin_clicked("brightness")
        assert clip.brightness_keyframes == []
        app_controller.timeline_controller._command_manager.undo()
        assert len(clip.brightness_keyframes) == 1
    finally:
        panel.deleteLater()


def test_slider_drag_with_keyframes_upserts_at_playhead() -> None:
    """Existing keyframes mean a slider drag should write a keyframe at the
    playhead time, not silently change the static fallback value."""
    app_controller, clip, panel = _setup_panel()
    try:
        clip.brightness_keyframes.extend([
            Keyframe(time_seconds=0.0, value=0.0),
            Keyframe(time_seconds=2.0, value=0.0),
        ])
        app_controller.timeline_controller.set_playhead_seconds(1.0)
        # Refresh now picks up the keyframes — the slider should still read 0 at t=1.
        panel._refresh_from_selection()
        slider = panel.slider_for("brightness")
        assert slider.value() == 0
        # Drag the slider to a new value.
        panel._on_slider_pressed("brightness")
        slider.setValue(50)  # -> 0.5
        panel._on_slider_released("brightness")
        # The drag must have inserted a third keyframe at t=1.0.
        times = sorted(kf.time_seconds for kf in clip.brightness_keyframes)
        values_at_one = [kf.value for kf in clip.brightness_keyframes if abs(kf.time_seconds - 1.0) < 1e-3]
        assert any(abs(t - 1.0) < 1e-3 for t in times)
        assert values_at_one and abs(values_at_one[0] - 0.5) < 1e-3
    finally:
        panel.deleteLater()


def test_reset_button_clears_color_keyframes() -> None:
    app_controller, clip, panel = _setup_panel()
    try:
        clip.brightness_keyframes.append(Keyframe(time_seconds=0.0, value=0.5))
        clip.hue_keyframes.append(Keyframe(time_seconds=0.0, value=30.0))
        clip.brightness = 0.5
        clip.hue = 30.0
        panel._on_reset_clicked()
        assert clip.brightness_keyframes == []
        assert clip.hue_keyframes == []
        # And the static defaults restored too.
        assert clip.brightness == 0.0
        assert clip.hue == 0.0
        # Reset is one undo step.
        app_controller.timeline_controller._command_manager.undo()
        assert len(clip.brightness_keyframes) == 1
        assert len(clip.hue_keyframes) == 1
    finally:
        panel.deleteLater()


def test_panel_slider_resyncs_to_keyframe_value_as_playhead_moves() -> None:
    """Moving the playhead should re-evaluate the slider position via the
    keyframe interpolator."""
    app_controller, clip, panel = _setup_panel()
    try:
        clip.brightness_keyframes.extend([
            Keyframe(time_seconds=0.0, value=0.0),
            Keyframe(time_seconds=2.0, value=1.0),  # slider max for brightness
        ])
        slider = panel.slider_for("brightness")
        app_controller.timeline_controller.set_playhead_seconds(0.0)
        panel._refresh_from_selection()
        assert slider.value() == 0
        app_controller.timeline_controller.set_playhead_seconds(1.0)
        panel._refresh_from_selection()
        # Linear interp at midpoint = 0.5 -> slider value 50.
        assert slider.value() == 50
        app_controller.timeline_controller.set_playhead_seconds(2.0)
        panel._refresh_from_selection()
        assert slider.value() == 100
    finally:
        panel.deleteLater()


def test_main_window_boots_with_keyframe_pin_buttons() -> None:
    create_application(["pytest"])
    window = build_main_window()
    try:
        sidebar = window._app_shell.left_sidebar_stack
        panel = sidebar.effects_panel
        # Each color slider must have a corresponding pin button.
        for name in ("brightness", "contrast", "saturation", "hue"):
            assert name in panel._pin_buttons
    finally:
        window.close()
