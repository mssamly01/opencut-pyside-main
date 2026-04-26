from __future__ import annotations

from pathlib import Path

from app.controllers.app_controller import AppController
from app.domain.clips.text_clip import TextClip


def _count_text_clips(controller: AppController) -> int:
    project = controller.project_controller.active_project()
    if project is None:
        return 0
    return sum(
        1
        for track in project.timeline.tracks
        for clip in track.clips
        if isinstance(clip, TextClip)
    )


def test_import_subtitle_adds_library_entry_without_auto_timeline_load(tmp_path: Path) -> None:
    app_controller = AppController()
    subtitle_path = tmp_path / "sample.srt"
    subtitle_path.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nHello world\n\n"
        "2\n00:00:03,500 --> 00:00:04,900\nSecond line\n",
        encoding="utf-8",
    )

    imported_count = app_controller.import_subtitles_from_file(str(subtitle_path))

    assert imported_count == 2
    entries = app_controller.subtitle_library_entries()
    assert len(entries) == 1
    assert entries[0].source_name == "sample.srt"
    assert _count_text_clips(app_controller) == 0


def test_load_subtitle_entry_to_timeline_creates_text_clips(tmp_path: Path) -> None:
    app_controller = AppController()
    subtitle_path = tmp_path / "load_me.srt"
    subtitle_path.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nA\n\n"
        "2\n00:00:01,200 --> 00:00:02,400\nB\n",
        encoding="utf-8",
    )
    app_controller.import_subtitles_from_file(str(subtitle_path))
    entry = app_controller.subtitle_library_entries()[0]

    loaded_count = app_controller.load_subtitle_entry_to_timeline(
        entry_id=entry.entry_id,
        timeline_offset_seconds=0.0,
    )

    assert loaded_count == 2
    assert _count_text_clips(app_controller) == 2
