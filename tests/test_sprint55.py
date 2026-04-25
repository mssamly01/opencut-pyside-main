from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.domain.clips.audio_clip import AudioClip
from app.domain.clips.text_clip import TextClip
from app.domain.project import build_demo_project
from app.domain.track import Track
from app.domain.word_timing import WordTiming
from app.dto.export_dto import ExportOptions
from app.services.export_service import ExportService
from app.services.project_service import ProjectService


def _build_filter_complex(project) -> str:
    service = ExportService(ffmpeg_executable="/bin/true")
    command = service._build_ffmpeg_command(
        project=project,
        target_path=Path("out.mp4"),
        warnings=[],
        project_root=None,
        options=ExportOptions(),
        in_point=0.0,
        out_point=None,
    )
    idx = command.index("-filter_complex")
    return command[idx + 1]


def test_sidechain_uses_asplit_when_voice_and_music_present() -> None:
    project = build_demo_project()
    voice_track = Track(
        track_id="track_voice_s55",
        name="Voice",
        track_type="audio",
        track_role="voice",
    )
    voice_track.clips.append(
        AudioClip(
            clip_id="clip_voice_s55",
            name="VO",
            track_id=voice_track.track_id,
            timeline_start=0.0,
            duration=2.0,
            media_id="missing_voice_media",
        )
    )
    project.timeline.tracks.append(voice_track)

    fc = _build_filter_complex(project)
    assert "sidechaincompress" in fc
    assert "asplit=2[voice_for_sc][voice_for_mix]" in fc
    assert "[voice_for_sc]" in fc
    assert "[voice_for_mix]" in fc


def test_sidechain_skipped_when_no_voice_role() -> None:
    project = build_demo_project()
    for track in project.timeline.tracks:
        if track.track_type.lower() in {"audio", "mixed"}:
            track.track_role = "music"

    fc = _build_filter_complex(project)
    assert "sidechaincompress" not in fc
    assert "asplit=2[voice_for_sc][voice_for_mix]" not in fc


def test_text_clip_split_words_evenly_is_clip_relative() -> None:
    clip = TextClip(
        clip_id="text_s55",
        name="Caption",
        track_id="track_text",
        timeline_start=10.0,
        duration=2.0,
        content="hello world",
    )
    words = clip.split_words_evenly()
    assert len(words) == 2
    assert words[0].start_seconds == pytest.approx(0.0)
    assert words[0].end_seconds == pytest.approx(1.0)
    assert words[1].start_seconds == pytest.approx(1.0)
    assert words[1].end_seconds == pytest.approx(2.0)


def test_project_service_migrates_word_timings_from_1_0(tmp_path) -> None:
    project = build_demo_project()
    text_track = next(track for track in project.timeline.tracks if track.track_type == "text")
    text_clip = next(clip for clip in text_track.clips if isinstance(clip, TextClip))
    text_clip.timeline_start = 5.0
    text_clip.duration = 2.0
    text_clip.word_timings = [
        WordTiming(start_seconds=5.0, end_seconds=6.0, text="hello"),
        WordTiming(start_seconds=6.0, end_seconds=7.0, text="world"),
    ]

    service = ProjectService()
    path = tmp_path / "legacy.json"
    service.save_project(project, str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["format_version"] = "1.0"
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = service.load_project(str(path))
    loaded_text_track = next(track for track in loaded.timeline.tracks if track.track_id == text_track.track_id)
    loaded_text = next(clip for clip in loaded_text_track.clips if clip.clip_id == text_clip.clip_id)
    assert isinstance(loaded_text, TextClip)
    assert loaded_text.word_timings[0].start_seconds == pytest.approx(0.0)
    assert loaded_text.word_timings[1].end_seconds == pytest.approx(2.0)


def test_project_service_roundtrip_word_timings_1_1(tmp_path) -> None:
    project = build_demo_project()
    text_track = next(track for track in project.timeline.tracks if track.track_type == "text")
    text_clip = next(clip for clip in text_track.clips if isinstance(clip, TextClip))
    text_clip.word_timings = [
        WordTiming(start_seconds=0.0, end_seconds=0.4, text="OpenCut"),
        WordTiming(start_seconds=0.4, end_seconds=0.8, text="rocks"),
    ]

    service = ProjectService()
    path = tmp_path / "modern.json"
    service.save_project(project, str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["format_version"] == "1.1"

    loaded = service.load_project(str(path))
    loaded_text_track = next(track for track in loaded.timeline.tracks if track.track_id == text_track.track_id)
    loaded_text = next(clip for clip in loaded_text_track.clips if clip.clip_id == text_clip.clip_id)
    assert isinstance(loaded_text, TextClip)
    assert loaded_text.word_timings[0].start_seconds == pytest.approx(0.0)
    assert loaded_text.word_timings[1].end_seconds == pytest.approx(0.8)
