"""Sprint 12: FFprobeGateway stream detail extraction."""

from __future__ import annotations

from app.infrastructure.ffprobe_gateway import FFprobeGateway


def test_extract_stream_details_video_and_audio() -> None:
    payload = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30/1",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
            },
        ]
    }
    result = FFprobeGateway._extract_stream_details(payload)
    assert result["width"] == 1920
    assert result["height"] == 1080
    assert result["video_codec"] == "h264"
    assert result["fps"] == 30.0
    assert result["audio_codec"] == "aac"
    assert result["sample_rate"] == 48000


def test_extract_stream_details_handles_missing_fields() -> None:
    payload = {"streams": [{"codec_type": "video"}]}
    result = FFprobeGateway._extract_stream_details(payload)
    assert result["width"] is None
    assert result["height"] is None
    assert result["video_codec"] is None
    assert result["fps"] is None


def test_parse_frame_rate_handles_ntsc_and_invalid() -> None:
    assert FFprobeGateway._parse_frame_rate("30/1") == 30.0
    parsed_ntsc = FFprobeGateway._parse_frame_rate("30000/1001")
    assert parsed_ntsc is not None
    assert abs(parsed_ntsc - 29.97) < 0.01
    assert FFprobeGateway._parse_frame_rate("0/1") is None
    assert FFprobeGateway._parse_frame_rate(None) is None
    assert FFprobeGateway._parse_frame_rate("invalid") is None
