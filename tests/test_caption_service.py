from __future__ import annotations

from pathlib import Path

import pytest
from app.services.caption_service import CaptionSegment, CaptionService


def test_parse_srt_file_returns_segments(tmp_path: Path) -> None:
    srt_path = tmp_path / "captions.srt"
    srt_path.write_text(
        "1\n00:00:01,000 --> 00:00:02,500\nHello world\n\n"
        "2\n00:00:03,000 --> 00:00:04,200\nSecond line\n",
        encoding="utf-8",
    )

    service = CaptionService()
    segments = service.parse_file(str(srt_path))

    assert len(segments) == 2
    assert segments[0].start_seconds == pytest.approx(1.0)
    assert segments[0].end_seconds == pytest.approx(2.5)
    assert segments[0].text == "Hello world"
    assert segments[1].text == "Second line"


def test_parse_vtt_file_with_identifier_and_settings(tmp_path: Path) -> None:
    vtt_path = tmp_path / "captions.vtt"
    vtt_path.write_text(
        "WEBVTT\n\n"
        "cue-1\n00:00:00.500 --> 00:00:01.900 align:start position:10%\nLine A\n\n"
        "00:00:02.000 --> 00:00:03.000\nLine B\n",
        encoding="utf-8",
    )

    service = CaptionService()
    segments = service.parse_file(str(vtt_path))

    assert len(segments) == 2
    assert segments[0].start_seconds == pytest.approx(0.5)
    assert segments[0].end_seconds == pytest.approx(1.9)
    assert segments[0].text == "Line A"
    assert segments[1].text == "Line B"


def test_parse_file_raises_for_unknown_extension(tmp_path: Path) -> None:
    txt_path = tmp_path / "captions.txt"
    txt_path.write_text("anything", encoding="utf-8")

    service = CaptionService()
    with pytest.raises(ValueError):
        service.parse_file(str(txt_path))


def test_serialize_srt_roundtrip(tmp_path: Path) -> None:
    service = CaptionService()
    segments = [
        CaptionSegment(start_seconds=1.0, end_seconds=2.5, text="Hello world"),
        CaptionSegment(start_seconds=3.0, end_seconds=4.2, text="Second line"),
    ]

    srt_path = tmp_path / "out.srt"
    written = service.write_srt(str(srt_path), segments)
    assert written == 2

    content = srt_path.read_text(encoding="utf-8")
    assert "00:00:01,000 --> 00:00:02,500" in content
    assert "Hello world" in content
    assert "00:00:03,000 --> 00:00:04,200" in content

    parsed = service.parse_file(str(srt_path))
    assert len(parsed) == 2
    assert parsed[0].start_seconds == pytest.approx(1.0)
    assert parsed[0].end_seconds == pytest.approx(2.5)
    assert parsed[0].text == "Hello world"
    assert parsed[1].text == "Second line"


def test_serialize_srt_skips_empty_and_invalid_segments() -> None:
    service = CaptionService()
    segments = [
        CaptionSegment(start_seconds=0.0, end_seconds=1.0, text="Keep me"),
        CaptionSegment(start_seconds=1.0, end_seconds=1.0, text="Zero duration"),
        CaptionSegment(start_seconds=2.0, end_seconds=3.0, text="   "),
    ]

    content = service.serialize_srt(segments)
    assert "Keep me" in content
    assert "Zero duration" not in content
    assert content.count("-->") == 1


def _write_bytes(path: Path, text: str, encoding: str) -> None:
    path.write_bytes(text.encode(encoding))


def test_parse_file_decodes_utf8_with_bom(tmp_path: Path) -> None:
    """SRT exported from Notepad with BOM (utf-8-sig) must be readable."""

    srt_path = tmp_path / "bom.srt"
    _write_bytes(
        srt_path,
        "1\n00:00:01,000 --> 00:00:02,000\nHello\n",
        "utf-8-sig",
    )

    segments = CaptionService().parse_file(str(srt_path))

    assert len(segments) == 1
    assert segments[0].text == "Hello"


def test_parse_file_decodes_cp1252(tmp_path: Path) -> None:
    """Western Windows default encoding for legacy SRT files."""

    srt_path = tmp_path / "windows.srt"
    _write_bytes(
        srt_path,
        "1\n00:00:01,000 --> 00:00:02,000\nNaïve café résumé\n",
        "cp1252",
    )

    segments = CaptionService().parse_file(str(srt_path))

    assert len(segments) == 1
    assert segments[0].text == "Naïve café résumé"


def test_parse_file_decodes_gbk(tmp_path: Path) -> None:
    """Chinese Windows default encoding — frequent for SRT files in CN."""

    srt_path = tmp_path / "gbk.srt"
    _write_bytes(
        srt_path,
        "1\n00:00:01,000 --> 00:00:02,000\n你好世界\n",
        "gbk",
    )

    segments = CaptionService().parse_file(str(srt_path))

    assert len(segments) == 1
    assert segments[0].text == "你好世界"


def test_parse_file_falls_back_to_latin1_for_undecodable_bytes(tmp_path: Path) -> None:
    """latin-1 accepts every byte so import must never raise on bad data —
    user gets a recognizable file even if some characters are wrong, which
    is preferable to a hard failure with no segments."""

    srt_path = tmp_path / "weird.srt"
    # Bytes that aren't valid utf-8 / utf-8-sig; cp1252 happens to accept
    # them (it accepts most byte sequences) — that's fine, the contract is
    # just "must not raise and must return segments".
    srt_path.write_bytes(
        b"1\n00:00:01,000 --> 00:00:02,000\nHello\xff\xfe weird\n"
    )

    segments = CaptionService().parse_file(str(srt_path))

    assert len(segments) == 1
    assert segments[0].text.startswith("Hello")
