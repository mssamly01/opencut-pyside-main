"""Tests for the MediaService (ffprobe-less behaviour)."""

from __future__ import annotations

from pathlib import Path

from app.infrastructure.ffprobe_gateway import FFprobeGateway, MediaProbeResult
from app.services.media_service import MediaService


class _StubFFprobeGateway(FFprobeGateway):
    def __init__(self, duration: float | None) -> None:  # noqa: D401 - stub constructor
        self._fake_duration = duration
        # Skip parent init – we do not need a real executable.

    def is_available(self) -> bool:  # type: ignore[override]
        return True

    def probe(self, file_path: str):  # type: ignore[override]
        return MediaProbeResult(
            duration_seconds=self._fake_duration,
            has_video_stream=True,
            has_audio_stream=True,
        )


def test_import_populates_duration_when_probe_succeeds(tmp_path: Path) -> None:
    sample_path = tmp_path / "demo.mp4"
    sample_path.write_bytes(b"\x00" * 4)

    service = MediaService(ffprobe_gateway=_StubFFprobeGateway(duration=12.5))
    imported = service.import_files([str(sample_path)])

    assert len(imported) == 1
    asset = imported[0]
    assert asset.media_type == "video"
    assert asset.duration_seconds == 12.5


def test_import_skips_non_existing_files(tmp_path: Path) -> None:
    service = MediaService(ffprobe_gateway=_StubFFprobeGateway(duration=None))
    imported = service.import_files([str(tmp_path / "missing.mp4")])

    assert imported == []


def test_import_deduplicates_identical_paths(tmp_path: Path) -> None:
    sample_path = tmp_path / "song.wav"
    sample_path.write_bytes(b"RIFF")

    service = MediaService(ffprobe_gateway=_StubFFprobeGateway(duration=3.0))
    imported = service.import_files([str(sample_path), str(sample_path)])

    assert len(imported) == 1
    asset = imported[0]
    assert asset.media_type == "audio"
    assert asset.duration_seconds == 3.0


def test_image_import_does_not_attempt_probe(tmp_path: Path) -> None:
    sample_path = tmp_path / "frame.png"
    sample_path.write_bytes(b"\x89PNG")

    class _RaisingProbe(FFprobeGateway):
        def __init__(self) -> None:
            pass

        def is_available(self) -> bool:  # type: ignore[override]
            return True

        def probe(self, file_path: str):  # type: ignore[override]
            raise AssertionError("probe() should not be called for images")

    service = MediaService(ffprobe_gateway=_RaisingProbe())
    imported = service.import_files([str(sample_path)])

    assert len(imported) == 1
    assert imported[0].media_type == "image"
    assert imported[0].duration_seconds is None
