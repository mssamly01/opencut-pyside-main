"""Waveform peaks load off the UI thread when a clip is rendered.

Before: ``TimelineScene._draw_track_clips`` called
``WaveformService.get_peaks`` synchronously on the UI thread, which on a
cache miss forks ``ffmpeg`` to extract audio samples (200-2000 ms) and
froze the timeline whenever a fresh clip was first rendered.

After: the scene reads ``peek_cached_peaks`` (memory + disk only,
no ffmpeg fork). On a miss it queues ``WaveformLoader.request_peaks``
and emits ``peaks_loaded`` from a worker thread, which swaps the
peaks into the existing ``ClipItem``.
"""

from __future__ import annotations

import struct
import threading

import pytest
from app.bootstrap import create_application
from app.domain.clips.audio_clip import AudioClip
from app.domain.clips.video_clip import VideoClip
from app.domain.media_asset import MediaAsset
from app.domain.project import build_empty_project
from app.domain.timeline import Timeline
from app.domain.track import Track
from app.services.thumbnail_service import ThumbnailService
from app.services.waveform_service import WaveformService
from app.ui.timeline.timeline_scene import TimelineScene
from PySide6.QtCore import QEventLoop, QTimer


class _StubThumbnailService(ThumbnailService):
    def get_filmstrip_bytes(self, project, clip, project_path=None, frame_count=8) -> list[bytes]:  # type: ignore[override]
        return []

    def get_thumbnail_bytes(self, project, clip, project_path=None) -> bytes | None:  # type: ignore[override]
        return None


def _process_until(predicate, timeout_ms: int = 2000) -> None:
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(10)

    def tick() -> None:
        if predicate():
            loop.quit()

    timer.timeout.connect(tick)
    timer.start()
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    timer.stop()


def _audio_project_with_clip(file_path: str = "/tmp/voice.wav") -> tuple[object, AudioClip]:
    project = build_empty_project()
    asset = MediaAsset(
        media_id="m_audio",
        name="voice.wav",
        file_path=file_path,
        media_type="audio",
        duration_seconds=4.0,
    )
    project.media_items.append(asset)
    clip = AudioClip(
        clip_id="ca",
        name="voice.wav",
        track_id="track_audio_1",
        timeline_start=0.0,
        duration=4.0,
        media_id="m_audio",
        source_start=0.0,
        source_end=4.0,
    )
    track = Track(track_id="track_audio_1", name="Audio", track_type="audio", clips=[clip])
    project.timeline = Timeline(tracks=[track])
    return project, clip


def _video_project_with_clip(file_path: str = "/tmp/clip.mp4") -> tuple[object, VideoClip]:
    project = build_empty_project()
    asset = MediaAsset(
        media_id="m_video",
        name="clip.mp4",
        file_path=file_path,
        media_type="video",
        duration_seconds=4.0,
        width=1920,
        height=1080,
    )
    project.media_items.append(asset)
    clip = VideoClip(
        clip_id="cv",
        name="clip.mp4",
        track_id="track_video_1",
        timeline_start=0.0,
        duration=4.0,
        media_id="m_video",
        source_start=0.0,
        source_end=4.0,
    )
    track = Track(track_id="track_video_1", name="Main", track_type="video", is_main=True, clips=[clip])
    project.timeline = Timeline(tracks=[track])
    return project, clip


class _StubFFmpegGateway:
    """Returns predictable s16le audio samples without forking ffmpeg.

    The ``threading.Event`` gate lets tests assert that ``render_timeline``
    returns BEFORE the audio worker finishes extraction — proving the
    extraction path is off the UI thread.
    """

    def __init__(self) -> None:
        self.gate = threading.Event()
        self.entered = threading.Event()
        self.calls = 0

    def is_available(self) -> bool:
        return True

    def extract_audio_samples_s16le(self, file_path: str, sample_rate: int = 8000) -> bytes | None:
        self.entered.set()
        self.gate.wait(timeout=5.0)
        self.calls += 1
        # 0.5s of synthesized PCM so _build_peaks produces non-trivial data.
        samples = [int(0.6 * 32767)] * (sample_rate // 2)
        return struct.pack(f"<{len(samples)}h", *samples)


def test_peek_cached_peaks_returns_empty_when_uncached(tmp_path) -> None:
    asset = MediaAsset(
        media_id="m_uncached",
        name="x.wav",
        file_path="/tmp/x.wav",
        media_type="audio",
        duration_seconds=1.0,
    )
    service = WaveformService(cache_root=tmp_path / "wfcache")
    assert service.peek_cached_peaks(asset) == []


def test_peek_cached_peaks_does_not_fork_ffmpeg(tmp_path) -> None:
    """``peek_cached_peaks`` MUST never call the ffmpeg gateway."""

    gateway = _StubFFmpegGateway()
    gateway.gate.set()  # would unblock if called
    service = WaveformService(ffmpeg_gateway=gateway, cache_root=tmp_path / "wfcache")
    asset = MediaAsset(
        media_id="m_peek",
        name="x.wav",
        file_path="/tmp/x.wav",
        media_type="audio",
        duration_seconds=1.0,
    )
    assert service.peek_cached_peaks(asset) == []
    assert gateway.calls == 0


def test_peek_cached_peaks_returns_disk_cached(tmp_path) -> None:
    cache_root = tmp_path / "wfcache"
    cache_root.mkdir()
    cache_path = cache_root / "m_disk.peaks"
    peaks = [0.1, 0.2, 0.3, 0.4]
    cache_path.write_bytes(struct.pack(f"<I{len(peaks)}f", len(peaks), *peaks))

    service = WaveformService(cache_root=cache_root)
    asset = MediaAsset(
        media_id="m_disk",
        name="x.wav",
        file_path="/tmp/x.wav",
        media_type="audio",
        duration_seconds=1.0,
    )
    cached = service.peek_cached_peaks(asset)
    assert cached == pytest.approx(peaks)


def test_timeline_scene_render_does_not_block_on_waveform(tmp_path) -> None:
    """Rendering an audio/video clip must not call ffmpeg synchronously."""

    create_application(["pytest"])
    audio_path = tmp_path / "voice.wav"
    audio_path.write_bytes(b"")
    project, clip = _audio_project_with_clip(file_path=str(audio_path))

    gateway = _StubFFmpegGateway()
    waveform_service = WaveformService(ffmpeg_gateway=gateway, cache_root=tmp_path / "wfcache")

    scene = TimelineScene(
        project=project,
        project_path=None,
        thumbnail_service=_StubThumbnailService(),
        waveform_service=waveform_service,
    )

    clip_item = scene._clip_items_by_id.get(clip.clip_id)  # noqa: SLF001
    assert clip_item is not None
    # Render returned even though ffmpeg is still gated inside the worker.
    assert gateway.entered.wait(timeout=2.0)
    assert clip_item._waveform_peaks == []  # noqa: SLF001

    # Let the worker finish, then verify the peaks were swapped in.
    gateway.gate.set()
    _process_until(lambda: bool(clip_item._waveform_peaks))  # noqa: SLF001
    assert len(clip_item._waveform_peaks) > 0  # noqa: SLF001
    assert gateway.calls == 1


def test_timeline_scene_async_waveform_works_for_video_clips(tmp_path) -> None:
    create_application(["pytest"])
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"")
    project, clip = _video_project_with_clip(file_path=str(video_path))

    gateway = _StubFFmpegGateway()
    gateway.gate.set()  # let the worker run to completion immediately
    waveform_service = WaveformService(ffmpeg_gateway=gateway, cache_root=tmp_path / "wfcache")

    scene = TimelineScene(
        project=project,
        project_path=None,
        thumbnail_service=_StubThumbnailService(),
        waveform_service=waveform_service,
    )
    clip_item = scene._clip_items_by_id.get(clip.clip_id)  # noqa: SLF001
    assert clip_item is not None
    _process_until(lambda: bool(clip_item._waveform_peaks))  # noqa: SLF001
    assert len(clip_item._waveform_peaks) > 0  # noqa: SLF001


def test_timeline_scene_dedupes_waveform_requests_per_media(tmp_path) -> None:
    """If two clips share the same media, only one ffmpeg extraction runs."""

    create_application(["pytest"])
    audio_path = tmp_path / "voice.wav"
    audio_path.write_bytes(b"")
    project, clip = _audio_project_with_clip(file_path=str(audio_path))
    # Add a second clip referencing the same media.
    second_clip = AudioClip(
        clip_id="ca2",
        name="voice.wav",
        track_id="track_audio_1",
        timeline_start=4.5,
        duration=4.0,
        media_id="m_audio",
        source_start=0.0,
        source_end=4.0,
    )
    project.timeline.tracks[0].clips.append(second_clip)

    gateway = _StubFFmpegGateway()
    gateway.gate.set()
    waveform_service = WaveformService(ffmpeg_gateway=gateway, cache_root=tmp_path / "wfcache")
    scene = TimelineScene(
        project=project,
        project_path=None,
        thumbnail_service=_StubThumbnailService(),
        waveform_service=waveform_service,
    )

    item_a = scene._clip_items_by_id.get("ca")  # noqa: SLF001
    item_b = scene._clip_items_by_id.get("ca2")  # noqa: SLF001
    assert item_a is not None and item_b is not None
    _process_until(lambda: bool(item_a._waveform_peaks) and bool(item_b._waveform_peaks))  # noqa: SLF001

    assert gateway.calls == 1
    assert item_a._waveform_peaks == item_b._waveform_peaks  # noqa: SLF001
