from __future__ import annotations

from pathlib import Path

from app.domain.clips.text_clip import TextClip
from app.domain.clips.video_clip import VideoClip
from app.domain.media_asset import MediaAsset
from app.domain.project import Project
from app.domain.timeline import Timeline
from app.domain.track import Track
from app.infrastructure.ffmpeg_gateway import FFmpegGateway
from app.services.playback_service import PlaybackService


class _StubFFmpegGateway(FFmpegGateway):
    def __init__(self, sequence_payload: list[bytes] | None = None, single_payload: bytes = b"single-frame") -> None:
        self.sequence_payload = sequence_payload if sequence_payload is not None else [b"seq-0", b"seq-1", b"seq-2"]
        self.single_payload = single_payload
        self.sequence_calls: list[tuple[str, float, float, int]] = []
        self.single_calls: list[tuple[str, float]] = []

    def extract_frame_sequence_png(  # type: ignore[override]
        self,
        file_path: str,
        start_time_seconds: float,
        fps: float,
        frame_count: int,
        extra_video_filters: list[str] | None = None,
    ) -> list[bytes]:
        self.sequence_calls.append((file_path, start_time_seconds, fps, frame_count))
        return list(self.sequence_payload)

    def extract_frame_png(  # type: ignore[override]
        self,
        file_path: str,
        time_seconds: float,
        extra_video_filters: list[str] | None = None,
    ) -> bytes | None:
        self.single_calls.append((file_path, time_seconds))
        return self.single_payload


def _build_video_project(media_file: Path, fps: float = 30.0) -> Project:
    clip = VideoClip(
        clip_id="clip_v1",
        name="Video",
        track_id="track_1",
        timeline_start=0.0,
        duration=4.0,
        media_id="media_1",
        source_start=0.0,
    )
    track = Track(track_id="track_1", name="Track 1", track_type="video", clips=[clip])
    media_asset = MediaAsset(
        media_id="media_1",
        name="sample",
        file_path=str(media_file),
        media_type="video",
        duration_seconds=4.0,
    )
    return Project(
        project_id="proj_1",
        name="Demo",
        width=1920,
        height=1080,
        fps=fps,
        timeline=Timeline(tracks=[track]),
        media_items=[media_asset],
    )


def _build_text_project() -> Project:
    clip = TextClip(
        clip_id="clip_t1",
        name="Caption",
        track_id="track_text",
        timeline_start=0.0,
        duration=2.0,
        content="Hello",
        font_size=42,
    )
    track = Track(track_id="track_text", name="Text", track_type="text", clips=[clip])
    return Project(
        project_id="proj_text",
        name="Text Demo",
        width=1280,
        height=720,
        fps=30.0,
        timeline=Timeline(tracks=[track]),
        media_items=[],
    )


def test_prefetch_window_reuses_decoded_frames(tmp_path: Path) -> None:
    media_file = tmp_path / "sample.mp4"
    media_file.write_bytes(b"fake-video")
    gateway = _StubFFmpegGateway(sequence_payload=[b"seq-0", b"seq-1", b"seq-2", b"seq-3"])
    service = PlaybackService(ffmpeg_gateway=gateway)
    project = _build_video_project(media_file)

    first = service.get_preview_frame(project, time_seconds=0.00)
    second = service.get_preview_frame(project, time_seconds=0.04)
    third = service.get_preview_frame(project, time_seconds=0.08)

    assert first.frame_bytes == b"seq-0"
    assert second.frame_bytes == b"seq-1"
    assert third.frame_bytes == b"seq-2"
    assert len(gateway.sequence_calls) == 1
    assert gateway.single_calls == []


def test_falls_back_to_single_frame_decode_when_prefetch_empty(tmp_path: Path) -> None:
    media_file = tmp_path / "sample.mp4"
    media_file.write_bytes(b"fake-video")
    gateway = _StubFFmpegGateway(sequence_payload=[], single_payload=b"fallback-frame")
    service = PlaybackService(ffmpeg_gateway=gateway)
    project = _build_video_project(media_file)

    result = service.get_preview_frame(project, time_seconds=0.10)

    assert result.frame_bytes == b"fallback-frame"
    assert len(gateway.sequence_calls) == 1
    assert len(gateway.single_calls) == 1


def test_text_clip_preview_renders_png_bytes() -> None:
    service = PlaybackService(ffmpeg_gateway=_StubFFmpegGateway())
    project = _build_text_project()

    result = service.get_preview_frame(project, time_seconds=0.5)

    assert result.frame_bytes is not None
    assert bytes(result.frame_bytes).startswith(b"\x89PNG\r\n\x1a\n")
