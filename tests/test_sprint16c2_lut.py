"""Sprint 16-C2: LUT preset registry, .cube validation, export injection, UI."""

from __future__ import annotations

from pathlib import Path

from app.bootstrap import build_app_context, create_application
from app.domain.clips.video_clip import VideoClip
from app.domain.project import Project
from app.domain.timeline import Timeline
from app.domain.track import Track
from app.services.export_service import ExportService, _PreparedClip
from app.services.lut_service import (
    PRESET_ID_PREFIX,
    PRESETS,
    assets_root,
    display_label_for_path,
    is_valid_cube_file,
    resolve_lut_path,
)
from app.services.project_service import ProjectService
from app.ui.sidebar.effects_panel import EffectsPanel


def _make_video_clip(**overrides: object) -> VideoClip:
    return VideoClip(
        clip_id=str(overrides.pop("clip_id", "c1")),
        name=str(overrides.pop("name", "clip")),
        track_id=str(overrides.pop("track_id", "t1")),
        timeline_start=float(overrides.pop("timeline_start", 0.0)),
        duration=float(overrides.pop("duration", 1.0)),
        media_id=overrides.pop("media_id", None),
        source_start=float(overrides.pop("source_start", 0.0)),
        is_muted=bool(overrides.pop("is_muted", False)),
        fade_in_seconds=float(overrides.pop("fade_in_seconds", 0.0)),
        fade_out_seconds=float(overrides.pop("fade_out_seconds", 0.0)),
        opacity=float(overrides.pop("opacity", 1.0)),
        **overrides,  # type: ignore[arg-type]
    )


# --- lut_service ----------------------------------------------------------


def test_bundled_presets_resolve_to_existing_files() -> None:
    """All shipped presets must point at real .cube files in assets/luts/."""
    assert PRESETS, "expected at least one bundled preset"
    for preset in PRESETS:
        path = assets_root() / preset.filename
        assert path.is_file(), f"missing preset file: {path}"
        assert is_valid_cube_file(path), f"preset is not a valid .cube file: {path}"


def test_resolve_preset_id_returns_absolute_path() -> None:
    preset = PRESETS[0]
    resolved = resolve_lut_path(preset.preset_id)
    assert resolved is not None
    assert resolved.is_absolute()
    assert resolved.suffix == ".cube"


def test_resolve_unknown_preset_returns_none() -> None:
    assert resolve_lut_path("preset:does_not_exist") is None


def test_resolve_empty_lut_path_returns_none() -> None:
    assert resolve_lut_path("") is None


def test_resolve_relative_path_returns_none() -> None:
    """Stored lut_path must be either a preset id or an absolute path."""
    assert resolve_lut_path("luts/cinematic.cube") is None


def test_is_valid_cube_file_rejects_non_cube(tmp_path: Path) -> None:
    bad = tmp_path / "fake.cube"
    bad.write_text("not a real lut file\n", encoding="utf-8")
    assert is_valid_cube_file(bad) is False


def test_is_valid_cube_file_accepts_minimal_header(tmp_path: Path) -> None:
    good = tmp_path / "tiny.cube"
    good.write_text(
        "TITLE \"tiny\"\nLUT_3D_SIZE 2\n0 0 0\n1 0 0\n0 1 0\n1 1 0\n0 0 1\n1 0 1\n0 1 1\n1 1 1\n",
        encoding="utf-8",
    )
    assert is_valid_cube_file(good) is True


def test_display_label_for_preset_uses_display_name() -> None:
    preset = PRESETS[0]
    assert display_label_for_path(preset.preset_id) == preset.display_name


def test_display_label_for_custom_path_uses_basename(tmp_path: Path) -> None:
    p = tmp_path / "Custom Look.cube"
    p.write_text("LUT_3D_SIZE 2\n", encoding="utf-8")
    assert display_label_for_path(str(p)) == "Custom Look.cube"


# --- export injection -----------------------------------------------------


def test_export_filters_inject_lut3d_when_lut_path_set() -> None:
    preset = PRESETS[0]
    clip = _make_video_clip(clip_id="c-lut", track_id="t-lut", duration=2.0, lut_path=preset.preset_id)
    filters = ExportService._color_adjust_filters_for_clip(clip)
    lut_filters = [f for f in filters if f.startswith("lut3d=")]
    assert len(lut_filters) == 1, f"expected exactly one lut3d filter, got {filters}"
    assert ":interp=tetrahedral" in lut_filters[0]
    assert preset.filename in lut_filters[0]


def test_export_filters_omit_lut3d_when_lut_path_empty() -> None:
    clip = _make_video_clip(clip_id="c-no-lut", track_id="t", duration=2.0, lut_path="")
    filters = ExportService._color_adjust_filters_for_clip(clip)
    assert all(not f.startswith("lut3d=") for f in filters)


def test_export_filters_skip_lut3d_when_path_invalid() -> None:
    clip = _make_video_clip(clip_id="c-bad-lut", track_id="t", duration=2.0, lut_path="/nonexistent/foo.cube")
    filters = ExportService._color_adjust_filters_for_clip(clip)
    assert all(not f.startswith("lut3d=") for f in filters)


def test_export_lut3d_runs_before_opacity_in_full_chain() -> None:
    """lut3d, like eq/hue, must precede colorchannelmixer to preserve alpha."""
    preset = PRESETS[0]
    clip = _make_video_clip(
        clip_id="c-order",
        track_id="t-order",
        duration=2.0,
        lut_path=preset.preset_id,
        opacity=0.5,
    )
    track = Track(track_id="t-order", name="t", track_type="video", clips=[clip])
    project = Project(
        project_id="p1",
        name="p",
        width=640,
        height=360,
        fps=30.0,
        timeline=Timeline(tracks=[track]),
    )
    prepared = _PreparedClip(
        clip=clip,
        input_index=0,
        placeholder=False,
        source_start=0.0,
        source_end=2.0,
    )
    service = ExportService()
    filters = service._video_filters_for_clip(prepared, project, fps=30.0, source_end=2.0)
    lut_index = next(i for i, f in enumerate(filters) if f.startswith("lut3d="))
    opacity_index = next(i for i, f in enumerate(filters) if f.startswith("colorchannelmixer=aa="))
    assert lut_index < opacity_index, f"lut3d must precede opacity; got: {filters}"


# --- persistence ----------------------------------------------------------


def test_project_service_round_trip_preserves_lut_path(tmp_path: Path) -> None:
    preset = PRESETS[0]
    clip = _make_video_clip(
        clip_id="cv1",
        track_id="t1",
        duration=2.0,
        brightness=0.2,
        lut_path=preset.preset_id,
    )
    track = Track(track_id="t1", name="t", track_type="video", clips=[clip])
    project = Project(
        project_id="p1",
        name="p",
        width=1920,
        height=1080,
        fps=30.0,
        timeline=Timeline(tracks=[track]),
    )
    service = ProjectService()
    out = service.save_project(project, file_path=str(tmp_path / "p.json"))
    loaded = service.load_project(out)
    loaded_clip = loaded.timeline.tracks[0].clips[0]
    assert isinstance(loaded_clip, VideoClip)
    assert loaded_clip.lut_path == preset.preset_id
    assert abs(loaded_clip.brightness - 0.2) < 1e-9


# --- UI -------------------------------------------------------------------


def test_effects_panel_lut_combo_lists_no_lut_presets_and_custom() -> None:
    create_application(["pytest"])
    context = build_app_context()
    panel = EffectsPanel(context.app_controller)
    try:
        combo = panel.lut_combo()
        # 1 "no LUT" + N presets + 1 custom sentinel
        assert combo.count() == 1 + len(PRESETS) + 1
        assert combo.itemData(0) == ""
        for i, preset in enumerate(PRESETS, start=1):
            assert combo.itemData(i) == preset.preset_id
        assert combo.itemData(combo.count() - 1) == "__custom__"
    finally:
        panel.deleteLater()


def test_effects_panel_apply_preset_pushes_undoable_command() -> None:
    create_application(["pytest"])
    context = build_app_context()
    app_controller = context.app_controller
    project = app_controller.project_controller.active_project()
    assert project is not None
    track = project.timeline.tracks[0]
    clip = _make_video_clip(clip_id="c-lut", track_id=track.track_id, duration=2.0)
    track.clips.append(clip)
    app_controller.timeline_controller.timeline_changed.emit()
    app_controller.selection_controller.select_clip(clip.clip_id)

    panel = EffectsPanel(app_controller)
    try:
        preset = PRESETS[0]
        # Programmatically pick the preset entry (index 1 = first preset).
        combo = panel.lut_combo()
        preset_index = next(i for i in range(combo.count()) if combo.itemData(i) == preset.preset_id)
        combo.setCurrentIndex(preset_index)
        panel._on_lut_combo_activated(preset_index)
        assert clip.lut_path == preset.preset_id
        # Undo restores the empty path.
        app_controller.timeline_controller._command_manager.undo()
        assert clip.lut_path == ""
        # Redo reapplies it.
        app_controller.timeline_controller._command_manager.redo()
        assert clip.lut_path == preset.preset_id
    finally:
        panel.deleteLater()


def test_effects_panel_reset_also_clears_lut() -> None:
    """Reset button must include lut_path in its single CompositeCommand."""
    create_application(["pytest"])
    context = build_app_context()
    app_controller = context.app_controller
    project = app_controller.project_controller.active_project()
    assert project is not None
    track = project.timeline.tracks[0]
    preset = PRESETS[0]
    clip = _make_video_clip(
        clip_id="c-reset",
        track_id=track.track_id,
        duration=2.0,
        brightness=0.4,
        lut_path=preset.preset_id,
    )
    track.clips.append(clip)
    app_controller.timeline_controller.timeline_changed.emit()
    app_controller.selection_controller.select_clip(clip.clip_id)

    panel = EffectsPanel(app_controller)
    try:
        panel._on_reset_clicked()
        assert clip.brightness == 0.0
        assert clip.lut_path == ""
        # Single undo restores both.
        app_controller.timeline_controller._command_manager.undo()
        assert abs(clip.brightness - 0.4) < 1e-9
        assert clip.lut_path == preset.preset_id
    finally:
        panel.deleteLater()


def test_effects_panel_lut_combo_resyncs_to_clip_on_selection() -> None:
    create_application(["pytest"])
    context = build_app_context()
    app_controller = context.app_controller
    project = app_controller.project_controller.active_project()
    assert project is not None
    track = project.timeline.tracks[0]
    preset = PRESETS[1]
    clip = _make_video_clip(
        clip_id="c-resync",
        track_id=track.track_id,
        duration=2.0,
        lut_path=preset.preset_id,
    )
    track.clips.append(clip)
    app_controller.timeline_controller.timeline_changed.emit()
    app_controller.selection_controller.select_clip(clip.clip_id)

    panel = EffectsPanel(app_controller)
    try:
        combo = panel.lut_combo()
        assert combo.currentData() == preset.preset_id
    finally:
        panel.deleteLater()


# Sanity: PRESET_ID_PREFIX is a stable contract.
def test_preset_id_prefix_constant_unchanged() -> None:
    assert PRESET_ID_PREFIX == "preset:"
    assert all(p.preset_id.startswith(PRESET_ID_PREFIX) for p in PRESETS)
