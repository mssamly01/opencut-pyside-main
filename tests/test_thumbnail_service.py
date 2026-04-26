from __future__ import annotations

from pathlib import Path

from app.domain.clips.audio_clip import AudioClip
from app.domain.clips.image_clip import ImageClip
from app.domain.clips.video_clip import VideoClip
from app.domain.media_asset import MediaAsset
from app.domain.project import Project
from app.domain.timeline import Timeline
from app.domain.track import Track
from app.infrastructure.ffmpeg_gateway import FFmpegGateway
from app.services.thumbnail_service import ThumbnailService


class _StubFFmpegGateway(FFmpegGateway):
    def __init__(self, payload: bytes = b"\x89PNG\r\n") -> None:
        self._payload = payload
        self.calls: list[tuple[str, float]] = []

    def extract_frame_png(  # type: ignore[override]
        self,
        file_path: str,
        time_seconds: float,
        extra_video_filters: list[str] | None = None,
    ) -> bytes | None:
        self.calls.append((file_path, time_seconds))
        return self._payload


def _build_project(media_asset: MediaAsset, clip: VideoClip | ImageClip | AudioClip) -> Project:
    track = Track(track_id="track_1", name="Track 1", track_type="mixed", clips=[clip])
    return Project(
        project_id="proj_1",
        name="Demo",
        width=1920,
        height=1080,
        fps=30.0,
        timeline=Timeline(tracks=[track]),
        media_items=[media_asset],
    )


def test_video_thumbnail_uses_memory_and_disk_cache(tmp_path: Path) -> None:
    media_file = tmp_path / "sample.mp4"
    media_file.write_bytes(b"fake video")

    clip = VideoClip(
        clip_id="clip_v1",
        name="Video",
        track_id="track_1",
        timeline_start=0.0,
        duration=4.0,
        media_id="media_1",
        source_start=0.0,
    )
    media_asset = MediaAsset(
        media_id="media_1",
        name="sample",
        file_path=str(media_file),
        media_type="video",
        duration_seconds=10.0,
    )
    project = _build_project(media_asset, clip)

    stub_gateway = _StubFFmpegGateway(payload=b"frame-bytes")
    service = ThumbnailService(ffmpeg_gateway=stub_gateway, cache_root=tmp_path / "cache")

    first = service.get_thumbnail_bytes(project, clip)
    assert first == b"frame-bytes"
    assert len(stub_gateway.calls) == 1

    second = service.get_thumbnail_bytes(project, clip)
    assert second == b"frame-bytes"
    assert len(stub_gateway.calls) == 1

    service.clear_memory_cache()
    third = service.get_thumbnail_bytes(project, clip)
    assert third == b"frame-bytes"
    assert len(stub_gateway.calls) == 1


def test_image_thumbnail_reads_source_without_ffmpeg(tmp_path: Path) -> None:
    image_file = tmp_path / "frame.png"
    image_payload = b"\x89PNG\r\n\x1a\n"
    image_file.write_bytes(image_payload)

    clip = ImageClip(
        clip_id="clip_i1",
        name="Image",
        track_id="track_1",
        timeline_start=0.0,
        duration=2.0,
        media_id="media_img",
    )
    media_asset = MediaAsset(
        media_id="media_img",
        name="frame",
        file_path=str(image_file),
        media_type="image",
        duration_seconds=None,
    )
    project = _build_project(media_asset, clip)

    class _NeverCalledGateway(_StubFFmpegGateway):
        def extract_frame_png(  # type: ignore[override]
            self,
            file_path: str,
            time_seconds: float,
            extra_video_filters: list[str] | None = None,
        ) -> bytes | None:
            raise AssertionError("ffmpeg should not be called for image thumbnails")

    service = ThumbnailService(ffmpeg_gateway=_NeverCalledGateway(), cache_root=tmp_path / "cache")
    assert service.get_thumbnail_bytes(project, clip) == image_payload


def test_video_filmstrip_returns_multiple_frames(tmp_path: Path) -> None:
    media_file = tmp_path / "sample.mp4"
    media_file.write_bytes(b"fake video")

    clip = VideoClip(
        clip_id="clip_v1",
        name="Video",
        track_id="track_1",
        timeline_start=0.0,
        duration=4.0,
        media_id="media_1",
        source_start=0.0,
        source_end=4.0,
    )
    media_asset = MediaAsset(
        media_id="media_1",
        name="sample",
        file_path=str(media_file),
        media_type="video",
        duration_seconds=10.0,
    )
    project = _build_project(media_asset, clip)

    stub_gateway = _StubFFmpegGateway(payload=b"frame-bytes")
    service = ThumbnailService(ffmpeg_gateway=stub_gateway, cache_root=tmp_path / "cache")

    frames = service.get_filmstrip_bytes(project, clip, frame_count=4)
    assert frames == [b"frame-bytes"] * 4
    assert len(stub_gateway.calls) == 4

    frames_again = service.get_filmstrip_bytes(project, clip, frame_count=4)
    assert frames_again == [b"frame-bytes"] * 4
    assert len(stub_gateway.calls) == 4


def test_filmstrip_empty_for_non_video_clip(tmp_path: Path) -> None:
    image_file = tmp_path / "frame.png"
    image_file.write_bytes(b"\x89PNG\r\n")

    clip = ImageClip(
        clip_id="clip_i1",
        name="Image",
        track_id="track_1",
        timeline_start=0.0,
        duration=2.0,
        media_id="media_img",
    )
    media_asset = MediaAsset(
        media_id="media_img",
        name="frame",
        file_path=str(image_file),
        media_type="image",
        duration_seconds=None,
    )
    project = _build_project(media_asset, clip)

    service = ThumbnailService(ffmpeg_gateway=_StubFFmpegGateway(), cache_root=tmp_path / "cache")
    assert service.get_filmstrip_bytes(project, clip, frame_count=6) == []


def test_non_visual_clip_has_no_thumbnail(tmp_path: Path) -> None:
    audio_file = tmp_path / "sound.wav"
    audio_file.write_bytes(b"RIFF")

    clip = AudioClip(
        clip_id="clip_a1",
        name="Audio",
        track_id="track_1",
        timeline_start=0.0,
        duration=2.0,
        media_id="media_a",
    )
    media_asset = MediaAsset(
        media_id="media_a",
        name="sound",
        file_path=str(audio_file),
        media_type="audio",
        duration_seconds=2.0,
    )
    project = _build_project(media_asset, clip)

    service = ThumbnailService(ffmpeg_gateway=_StubFFmpegGateway(), cache_root=tmp_path / "cache")
    assert service.get_thumbnail_bytes(project, clip) is None
