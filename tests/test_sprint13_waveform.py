"""Sprint 13: WaveformService.get_peaks_for_asset works without a clip."""

from __future__ import annotations

from app.domain.media_asset import MediaAsset
from app.services.waveform_service import WaveformService


def test_get_peaks_for_asset_returns_empty_for_image() -> None:
    """Image assets must not produce peaks (audio/video only)."""
    service = WaveformService()
    image_asset = MediaAsset(
        media_id="m1",
        name="pic",
        file_path="/tmp/missing.png",
        media_type="image",
    )
    assert service.get_peaks_for_asset(image_asset) == []


def test_get_peaks_for_asset_returns_empty_for_missing_file() -> None:
    """Missing media files must return [] without raising."""
    service = WaveformService()
    audio_asset = MediaAsset(
        media_id="m2",
        name="ghost",
        file_path="/tmp/does-not-exist.mp3",
        media_type="audio",
    )
    assert service.get_peaks_for_asset(audio_asset) == []
