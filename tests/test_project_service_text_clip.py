from __future__ import annotations

from pathlib import Path

from app.domain.clips.text_clip import TextClip
from app.domain.project import Project, build_demo_project
from app.domain.timeline import Timeline
from app.domain.track import Track
from app.services.project_service import ProjectService


def _project_with_text_clip(text_clip: TextClip) -> Project:
    demo = build_demo_project()
    track = Track(track_id="track_text_test", name="Text", track_type="text")
    track.clips.append(text_clip)
    return Project(
        project_id=demo.project_id,
        name=demo.name,
        width=demo.width,
        height=demo.height,
        fps=demo.fps,
        media_items=list(demo.media_items),
        timeline=Timeline(tracks=[track]),
    )


def test_text_clip_roundtrip_preserves_style_fields(tmp_path: Path) -> None:
    original_clip = TextClip(
        clip_id="clip_caption_1",
        name="Captioned",
        track_id="track_text_test",
        timeline_start=1.25,
        duration=2.5,
        content="Hello\nWorld",
        font_size=52,
        color="#ff00ff",
        position_x=0.4,
        position_y=0.8,
        font_family="DejaVu Sans",
        bold=True,
        italic=True,
        alignment="right",
        outline_color="#112233",
        outline_width=2.5,
        background_color="#445566",
        background_opacity=0.75,
        shadow_color="#778899",
        shadow_offset_x=4.0,
        shadow_offset_y=-2.0,
        fade_in_seconds=0.2,
        fade_out_seconds=0.3,
    )
    project = _project_with_text_clip(original_clip)

    service = ProjectService()
    saved_path = tmp_path / "project.json"
    service.save_project(project, str(saved_path))
    loaded = service.load_project(str(saved_path))

    text_track = next(track for track in loaded.timeline.tracks if track.track_type == "text")
    restored = next(clip for clip in text_track.clips if clip.clip_id == "clip_caption_1")
    assert isinstance(restored, TextClip)
    assert restored.content == "Hello\nWorld"
    assert restored.font_family == "DejaVu Sans"
    assert restored.bold is True
    assert restored.italic is True
    assert restored.alignment == "right"
    assert restored.outline_color == "#112233"
    assert restored.outline_width == 2.5
    assert restored.background_color == "#445566"
    assert restored.background_opacity == 0.75
    assert restored.shadow_color == "#778899"
    assert restored.shadow_offset_x == 4.0
    assert restored.shadow_offset_y == -2.0
    assert restored.fade_in_seconds == 0.2
    assert restored.fade_out_seconds == 0.3


def test_load_legacy_text_clip_applies_defaults(tmp_path: Path) -> None:
    legacy_payload = (
        '{"project_id":"demo","name":"Legacy","width":1920,"height":1080,"fps":30,'
        '"media_items":[],"timeline":{"tracks":[{"track_id":"track_text","name":"Text",'
        '"track_type":"text","clips":[{"clip_type":"text","clip_id":"c1","name":"Legacy",'
        '"track_id":"track_text","timeline_start":0.0,"duration":2.0,"media_id":null,'
        '"source_start":0.0,"source_end":null,"opacity":1.0,"is_locked":false,"is_muted":false,'
        '"content":"Hi","font_size":42,"color":"#ffffff","position_x":0.5,"position_y":0.86}]}]}}'
    )
    saved_path = tmp_path / "legacy.json"
    saved_path.write_text(legacy_payload, encoding="utf-8")

    loaded = ProjectService().load_project(str(saved_path))
    clip = loaded.timeline.tracks[0].clips[0]
    track = loaded.timeline.tracks[0]

    assert isinstance(clip, TextClip)
    assert track.is_muted is False
    assert track.is_locked is False
    assert track.is_hidden is False
    assert track.height == 58.0
    assert clip.font_family == "Arial"
    assert clip.bold is False
    assert clip.italic is False
    assert clip.alignment == "center"
    assert clip.outline_width == 0.0
    assert clip.background_opacity == 0.0
    assert clip.fade_in_seconds == 0.0
    assert clip.fade_out_seconds == 0.0
