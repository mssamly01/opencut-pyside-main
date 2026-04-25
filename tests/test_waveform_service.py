from __future__ import annotations

import struct
from pathlib import Path

from app.domain.clips.audio_clip import AudioClip
from app.domain.clips.text_clip import TextClip
from app.domain.media_asset import MediaAsset
from app.domain.project import Project
from app.domain.timeline import Timeline
from app.domain.track import Track
from app.infrastructure.ffmpeg_gateway import FFmpegGateway
from app.services.waveform_service import WaveformService


class _StubFFmpegGateway(FFmpegGateway):
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.calls: list[tuple[str, int]] = []

    def extract_audio_samples_s16le(self, file_path: str, sample_rate: int = 8000) -> bytes | None:  # type: ignore[override]
        self.calls.append((file_path, sample_rate))
        return self.payload


def _build_audio_project(media_file: Path) -> tuple[Project, AudioClip]:
    clip = AudioClip(
        clip_id="clip_a1",
        name="Audio",
        track_id="track_a",
        timeline_start=0.0,
        duration=2.0,
        media_id="media_a",
        source_start=0.0,
    )
    track = Track(track_id="track_a", name="Audio", track_type="audio", clips=[clip])
    media_asset = MediaAsset(
        media_id="media_a",
        name="audio",
        file_path=str(media_file),
        media_type="audio",
        duration_seconds=2.0,
    )
    project = Project(
        project_id="proj_a",
        name="Audio Demo",
        width=1280,
        height=720,
        fps=30.0,
        timeline=Timeline(tracks=[track]),
        media_items=[media_asset],
    )
    return project, clip


def test_waveform_service_generates_and_caches_peaks(tmp_path: Path) -> None:
    media_file = tmp_path / "sample.wav"
    media_file.write_bytes(b"fake")

    samples = b"".join(struct.pack("<h", value) for value in [0, 1200, -2000, 8000, -5000, 12000, -1000] * 400)
    gateway = _StubFFmpegGateway(samples)
    service = WaveformService(ffmpeg_gateway=gateway, cache_root=tmp_path / "wave-cache")
    project, clip = _build_audio_project(media_file)

    first = service.get_peaks(project, clip)
    second = service.get_peaks(project, clip)

    assert first
    assert second == first
    assert len(gateway.calls) == 1
    assert (tmp_path / "wave-cache" / "media_a.peaks").exists()


def test_waveform_service_ignores_non_audio_clips(tmp_path: Path) -> None:
    media_file = tmp_path / "sample.wav"
    media_file.write_bytes(b"fake")
    project, _audio_clip = _build_audio_project(media_file)
    text_clip = TextClip(
        clip_id="clip_t1",
        name="Text",
        track_id="track_t",
        timeline_start=0.0,
        duration=1.0,
        content="demo",
    )

    service = WaveformService(ffmpeg_gateway=_StubFFmpegGateway(b"\x00\x01"))
    assert service.get_peaks(project, text_clip) == []

