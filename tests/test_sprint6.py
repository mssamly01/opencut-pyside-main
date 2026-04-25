from __future__ import annotations

from pathlib import Path

from app.domain.clips.audio_clip import AudioClip
from app.domain.clips.text_clip import TextClip
from app.domain.project import Project, build_demo_project
from app.domain.track import Track
from app.domain.word_timing import WordTiming
from app.dto.export_dto import ExportOptions
from app.services.export_service import ExportService


def _build_filter_complex(project: Project) -> str:
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


def test_export_per_word_chain_emits_one_drawtext_per_word_for_single_line() -> None:
    project = build_demo_project()
    clip = TextClip(
        clip_id="t_pw_1",
        name="Hello world",
        track_id="track_text_1",
        timeline_start=1.0,
        duration=2.0,
        content="Hello world",
        word_timings=[
            WordTiming(start_seconds=0.0, end_seconds=1.0, text="Hello"),
            WordTiming(start_seconds=1.0, end_seconds=2.0, text="world"),
        ],
        highlight_color="#ff00aa",
    )

    chain = ExportService._build_text_clip_drawtext_chain(clip, project)
    assert len(chain) == 3
    assert any("text='Hello world'" in option for option in chain[0])

    word_options = ":".join(option for entry in chain[1:] for option in entry)
    assert "text='Hello'" in word_options
    assert "text='world'" in word_options
    assert "fontcolor=#ff00aa" in word_options
    assert "between(t,1.000000,2.000000)" in word_options
    assert "between(t,2.000000,3.000000)" in word_options


def test_export_per_word_chain_skips_for_multiline_text() -> None:
    project = build_demo_project()
    clip = TextClip(
        clip_id="t_pw_2",
        name="multiline",
        track_id="track_text_1",
        timeline_start=0.0,
        duration=2.0,
        content="line1\nline2",
        word_timings=[
            WordTiming(start_seconds=0.0, end_seconds=1.0, text="line1"),
            WordTiming(start_seconds=1.0, end_seconds=2.0, text="line2"),
        ],
    )

    chain = ExportService._build_text_clip_drawtext_chain(clip, project)
    assert len(chain) == 1


def test_export_per_word_chain_skips_when_no_word_timings() -> None:
    project = build_demo_project()
    clip = TextClip(
        clip_id="t_pw_3",
        name="plain",
        track_id="track_text_1",
        timeline_start=0.0,
        duration=2.0,
        content="just text",
        word_timings=[],
    )

    chain = ExportService._build_text_clip_drawtext_chain(clip, project)
    assert len(chain) == 1


def test_export_filter_uses_chained_overlays_with_distinct_labels() -> None:
    project = build_demo_project()
    text_track = next(track for track in project.timeline.tracks if track.track_type == "text")
    text_track.clips = [
        TextClip(
            clip_id="t_pw_4",
            name="ab cd",
            track_id=text_track.track_id,
            timeline_start=0.0,
            duration=1.0,
            content="ab cd",
            word_timings=[
                WordTiming(start_seconds=0.0, end_seconds=0.5, text="ab"),
                WordTiming(start_seconds=0.5, end_seconds=1.0, text="cd"),
            ],
        )
    ]

    filter_complex = _build_filter_complex(project)
    assert "[tov0_0]" in filter_complex
    assert "[tov0_1]" in filter_complex
    assert "[tov0_2]" in filter_complex


def test_export_sfx_track_role_is_not_ducked() -> None:
    project = build_demo_project()
    project.timeline.tracks = []

    voice_track = Track(track_id="track_voice_s6", name="Voice", track_type="audio", track_role="voice")
    music_track = Track(track_id="track_music_s6", name="Music", track_type="audio", track_role="music")
    sfx_track = Track(track_id="track_sfx_s6", name="SFX", track_type="audio", track_role="sfx")

    voice_track.clips.append(
        AudioClip(
            clip_id="clip_voice_s6",
            name="voice",
            track_id=voice_track.track_id,
            timeline_start=0.0,
            duration=2.0,
            media_id="missing_voice",
        )
    )
    music_track.clips.append(
        AudioClip(
            clip_id="clip_music_s6",
            name="music",
            track_id=music_track.track_id,
            timeline_start=0.0,
            duration=2.0,
            media_id="missing_music",
        )
    )
    sfx_track.clips.append(
        AudioClip(
            clip_id="clip_sfx_s6",
            name="sfx",
            track_id=sfx_track.track_id,
            timeline_start=0.0,
            duration=1.0,
            media_id="missing_sfx",
        )
    )
    project.timeline.tracks.extend([voice_track, music_track, sfx_track])

    filter_complex = _build_filter_complex(project)
    assert "sidechaincompress" in filter_complex
    assert "asplit=2[voice_for_sc][voice_for_mix]" in filter_complex

    sidechain_segment = next(
        segment for segment in filter_complex.split(";") if "sidechaincompress" in segment
    )
    assert "[a2]" not in sidechain_segment

    final_amix_segment = next(segment for segment in filter_complex.split(";") if "amix=inputs=" in segment and "[aout]" in segment)
    assert "[a2]" in final_amix_segment


def test_export_sfx_only_without_voice_skips_sidechain() -> None:
    project = build_demo_project()
    project.timeline.tracks = []

    music_track = Track(track_id="track_music_s6_only", name="Music", track_type="audio", track_role="music")
    sfx_track = Track(track_id="track_sfx_s6_only", name="SFX", track_type="audio", track_role="sfx")

    music_track.clips.append(
        AudioClip(
            clip_id="clip_music_s6_only",
            name="music",
            track_id=music_track.track_id,
            timeline_start=0.0,
            duration=2.0,
            media_id="missing_music",
        )
    )
    sfx_track.clips.append(
        AudioClip(
            clip_id="clip_sfx_s6_only",
            name="sfx",
            track_id=sfx_track.track_id,
            timeline_start=0.0,
            duration=1.0,
            media_id="missing_sfx",
        )
    )
    project.timeline.tracks.extend([music_track, sfx_track])

    filter_complex = _build_filter_complex(project)
    assert "sidechaincompress" not in filter_complex
    assert "asplit=2[voice_for_sc][voice_for_mix]" not in filter_complex
