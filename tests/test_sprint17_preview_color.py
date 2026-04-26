"""Sprint 17: real-time color/LUT in preview pipeline.

Verifies that the brightness/contrast/saturation/hue/lut_path fields drive
ffmpeg ``-vf`` filters in the *preview* path (FFmpegGateway + VideoDecoder +
PlaybackService), and that the cache invalidates when those fields change.
"""

from __future__ import annotations

from pathlib import Path

from app.domain.clips.video_clip import VideoClip
from app.domain.media_asset import MediaAsset
from app.domain.project import Project
from app.domain.timeline import Timeline
from app.domain.track import Track
from app.infrastructure.ffmpeg_gateway import FFmpegGateway
from app.infrastructure.video_decoder import VideoDecoder, _filter_token
from app.services.lut_service import PRESETS
from app.services.playback_service import PlaybackService

# --- FFmpegGateway: filter chain wiring -----------------------------------


def test_extract_frame_sequence_command_includes_extra_filters() -> None:
    gateway = FFmpegGateway()
    cmd = gateway._build_extract_frame_sequence_command(
        source_path=Path("/tmp/sample.mp4"),
        start_time_seconds=0.5,
        fps=30.0,
        frame_count=10,
        extra_video_filters=["eq=brightness=0.2", "hue=h=15.000000"],
    )
    vf_index = cmd.index("-vf")
    chain = cmd[vf_index + 1]
    parts = chain.split(",")
    assert parts[0].startswith("fps=30.000000")
    assert "eq=brightness=0.2" in parts
    assert "hue=h=15.000000" in parts


def test_extract_frame_sequence_command_omits_filters_when_empty() -> None:
    gateway = FFmpegGateway()
    cmd = gateway._build_extract_frame_sequence_command(
        source_path=Path("/tmp/sample.mp4"),
        start_time_seconds=0.0,
        fps=30.0,
        frame_count=4,
    )
    vf_index = cmd.index("-vf")
    assert cmd[vf_index + 1] == "fps=30.000000"


def test_extract_frame_command_appends_vf_only_when_filters_present() -> None:
    gateway = FFmpegGateway()
    base_cmd = gateway._build_extract_frame_command(
        source_path=Path("/tmp/sample.mp4"),
        time_seconds=1.5,
        seek_before_input=True,
    )
    assert "-vf" not in base_cmd

    with_filters = gateway._build_extract_frame_command(
        source_path=Path("/tmp/sample.mp4"),
        time_seconds=1.5,
        seek_before_input=True,
        extra_video_filters=["eq=contrast=1.1"],
    )
    vf_index = with_filters.index("-vf")
    assert with_filters[vf_index + 1] == "eq=contrast=1.1"


# --- VideoDecoder: cache invalidation by filter chain ---------------------


def test_filter_token_is_stable_and_distinguishes_chains() -> None:
    assert _filter_token(None) == ""
    assert _filter_token([]) == ""
    a = _filter_token(["eq=brightness=0.1"])
    b = _filter_token(["eq=brightness=0.2"])
    assert a and b and a != b
    assert _filter_token(["eq=brightness=0.1"]) == a  # deterministic


def test_video_decoder_cache_segregates_by_filter_chain() -> None:
    decoder = VideoDecoder(ffmpeg_gateway=FFmpegGateway())
    decoder.put_frame("/m.mp4", 30.0, 5, b"baseline")
    decoder.put_frame("/m.mp4", 30.0, 5, b"graded", extra_video_filters=["eq=brightness=0.3"])

    assert decoder.get_frame("/m.mp4", 30.0, 5) == b"baseline"
    assert (
        decoder.get_frame("/m.mp4", 30.0, 5, extra_video_filters=["eq=brightness=0.3"])
        == b"graded"
    )
    # A *different* filter chain must miss, even though path/fps/index match.
    assert (
        decoder.get_frame("/m.mp4", 30.0, 5, extra_video_filters=["eq=brightness=0.5"])
        is None
    )


def test_prefetched_until_segregates_by_filter_chain() -> None:
    decoder = VideoDecoder(ffmpeg_gateway=FFmpegGateway())
    decoder.put_frame("/m.mp4", 30.0, 12, b"baseline")
    assert decoder.has_prefetched_until("/m.mp4", 30.0, 10) is True
    assert decoder.has_prefetched_until(
        "/m.mp4", 30.0, 10, extra_video_filters=["eq=brightness=0.3"]
    ) is False


# --- PlaybackService: filter chain reaches the gateway --------------------


class _RecordingGateway(FFmpegGateway):
    def __init__(self) -> None:
        self.sequence_calls: list[dict] = []
        self.single_calls: list[dict] = []

    def is_available(self) -> bool:  # type: ignore[override]
        return True

    def extract_frame_sequence_png(  # type: ignore[override]
        self,
        file_path: str,
        start_time_seconds: float,
        fps: float,
        frame_count: int,
        extra_video_filters: list[str] | None = None,
    ) -> list[bytes]:
        self.sequence_calls.append(
            {
                "file_path": file_path,
                "start_time": start_time_seconds,
                "fps": fps,
                "count": frame_count,
                "filters": list(extra_video_filters or []),
            }
        )
        return [b"frame-0", b"frame-1", b"frame-2"]

    def extract_frame_png(  # type: ignore[override]
        self,
        file_path: str,
        time_seconds: float,
        extra_video_filters: list[str] | None = None,
    ) -> bytes | None:
        self.single_calls.append(
            {
                "file_path": file_path,
                "time": time_seconds,
                "filters": list(extra_video_filters or []),
            }
        )
        return b"single-frame"


def _build_project(media_file: Path, **clip_overrides: object) -> Project:
    clip = VideoClip(
        clip_id="c1",
        name="Video",
        track_id="t1",
        timeline_start=0.0,
        duration=4.0,
        media_id="m1",
        source_start=0.0,
        **clip_overrides,  # type: ignore[arg-type]
    )
    track = Track(track_id="t1", name="Track 1", track_type="video", clips=[clip])
    asset = MediaAsset(
        media_id="m1",
        name="sample",
        file_path=str(media_file),
        media_type="video",
        duration_seconds=4.0,
    )
    return Project(
        project_id="p1",
        name="Demo",
        width=1920,
        height=1080,
        fps=30.0,
        timeline=Timeline(tracks=[track]),
        media_items=[asset],
    )


def test_preview_passes_color_filters_to_gateway(tmp_path: Path) -> None:
    media_file = tmp_path / "sample.mp4"
    media_file.write_bytes(b"fake-video")
    gateway = _RecordingGateway()
    service = PlaybackService(ffmpeg_gateway=gateway)
    project = _build_project(media_file, brightness=0.25, contrast=1.1)

    service.get_preview_frame(project, time_seconds=0.0)

    assert len(gateway.sequence_calls) == 1
    filters = gateway.sequence_calls[0]["filters"]
    eq_filter = next((f for f in filters if f.startswith("eq=")), None)
    assert eq_filter is not None
    assert "brightness=0.250000" in eq_filter
    assert "contrast=1.100000" in eq_filter


def test_preview_with_no_grading_passes_empty_filters(tmp_path: Path) -> None:
    media_file = tmp_path / "sample.mp4"
    media_file.write_bytes(b"fake-video")
    gateway = _RecordingGateway()
    service = PlaybackService(ffmpeg_gateway=gateway)
    project = _build_project(media_file)  # all defaults -> identity

    service.get_preview_frame(project, time_seconds=0.0)

    assert gateway.sequence_calls[0]["filters"] == []


def test_preview_passes_lut3d_to_gateway(tmp_path: Path) -> None:
    media_file = tmp_path / "sample.mp4"
    media_file.write_bytes(b"fake-video")
    gateway = _RecordingGateway()
    service = PlaybackService(ffmpeg_gateway=gateway)
    preset = PRESETS[0]
    project = _build_project(media_file, lut_path=preset.preset_id)

    service.get_preview_frame(project, time_seconds=0.0)

    filters = gateway.sequence_calls[0]["filters"]
    lut = next((f for f in filters if f.startswith("lut3d=")), None)
    assert lut is not None
    assert preset.filename in lut


def test_preview_changing_brightness_invalidates_cache(tmp_path: Path) -> None:
    """First decode at brightness=0 caches; bumping brightness must re-decode."""
    media_file = tmp_path / "sample.mp4"
    media_file.write_bytes(b"fake-video")
    gateway = _RecordingGateway()
    service = PlaybackService(ffmpeg_gateway=gateway)
    project = _build_project(media_file)
    clip = project.timeline.tracks[0].clips[0]
    assert isinstance(clip, VideoClip)

    # Two preview reads at the same time produce a single decode (cache hit).
    service.get_preview_frame(project, time_seconds=0.0)
    service.get_preview_frame(project, time_seconds=0.0)
    assert len(gateway.sequence_calls) == 1

    # Bump brightness; cache key changes so we expect a new decode.
    clip.brightness = 0.4
    service.get_preview_frame(project, time_seconds=0.0)
    assert len(gateway.sequence_calls) == 2
    second_filters = gateway.sequence_calls[1]["filters"]
    eq = next(f for f in second_filters if f.startswith("eq="))
    assert "brightness=0.400000" in eq

    # Reverting to defaults should hit the original cache entry, not re-decode.
    clip.brightness = 0.0
    service.get_preview_frame(project, time_seconds=0.0)
    assert len(gateway.sequence_calls) == 2
