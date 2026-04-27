from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.domain.word_timing import WordTiming

__all__ = ["CaptionSegment", "CaptionService", "WordTiming"]


@dataclass(slots=True)
class CaptionSegment:
    start_seconds: float
    end_seconds: float
    text: str
    word_timings: list[WordTiming] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.end_seconds - self.start_seconds)

    def split_words_evenly(self) -> list[WordTiming]:
        words = (self.text or "").split()
        if not words:
            return []
        total = max(1e-6, self.duration_seconds)
        per_word = total / len(words)
        return [
            WordTiming(
                start_seconds=self.start_seconds + index * per_word,
                end_seconds=self.start_seconds + (index + 1) * per_word,
                text=word,
            )
            for index, word in enumerate(words)
        ]


class CaptionService:
    _TIME_RANGE_MARKER = "-->"
    _TIMESTAMP_RE = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?$")

    # Encodings tried in order when the file isn't valid UTF-8.
    # Order matters:
    # * ``utf-8-sig`` runs before ``utf-8`` so the BOM is stripped instead
    #   of leaking into the decoded string as ``\ufeff`` (plain ``utf-8``
    #   accepts a leading BOM but keeps it as a real character, which then
    #   breaks timestamp parsing if the SRT has no index line).
    # * ``cp1252`` and ``latin-1`` accept almost any byte stream so anything
    #   stricter must run first or CJK content would silently become
    #   mojibake (你好 → ÄãºÃ).
    # * ``gbk`` is stricter than ``cp1252`` (lead-byte 0x81-0xFE must be
    #   followed by a byte ≥ 0x40) so it goes before ``cp1252``.
    # * ``latin-1`` is last and never raises — the loop is therefore
    #   guaranteed to return a string for any existing file.
    _ENCODING_FALLBACKS: tuple[str, ...] = (
        "utf-8-sig",
        "utf-8",
        "gbk",
        "cp1252",
        "latin-1",
    )

    def parse_file(self, file_path: str) -> list[CaptionSegment]:
        source_path = Path(file_path).expanduser().resolve()
        raw_text = self._read_text_with_encoding_fallback(source_path)

        suffix = source_path.suffix.lower()
        if suffix == ".srt":
            return self.parse_srt(raw_text)
        if suffix == ".vtt":
            return self.parse_vtt(raw_text)
        raise ValueError(f"Unsupported subtitle file format: '{source_path.suffix}'")

    @classmethod
    def _read_text_with_encoding_fallback(cls, path: Path) -> str:
        """Decode ``path`` using a small set of common subtitle encodings.

        SRT files in the wild are saved with whatever default the user's OS
        uses (utf-8, utf-8 with BOM, cp1252 on Western Windows, gbk on
        Chinese Windows, …). The loop ends on ``latin-1`` which accepts
        every byte value, so this method always returns a string for any
        existing file.
        """

        data = path.read_bytes()
        for encoding in cls._ENCODING_FALLBACKS:
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        # Unreachable: ``latin-1`` is the last fallback and accepts any
        # byte value, so the loop above always returns. Raise instead of
        # silently returning an empty string if the invariant ever breaks.
        raise AssertionError(
            "_ENCODING_FALLBACKS must end with an encoding that never raises"
        )

    def parse_srt(self, text: str) -> list[CaptionSegment]:
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        blocks = self._split_blocks(lines)
        segments: list[CaptionSegment] = []
        for block in blocks:
            segment = self._segment_from_block(block)
            if segment is not None:
                segments.append(segment)
        return segments

    def serialize_srt(self, segments: list[CaptionSegment]) -> str:
        lines: list[str] = []
        written_index = 1
        for segment in segments:
            text = (segment.text or "").strip()
            if not text:
                continue
            if segment.end_seconds <= segment.start_seconds:
                continue

            lines.append(str(written_index))
            lines.append(
                f"{self._format_srt_timestamp(segment.start_seconds)} --> "
                f"{self._format_srt_timestamp(segment.end_seconds)}"
            )
            lines.append(text)
            lines.append("")
            written_index += 1
        return "\n".join(lines).rstrip() + "\n" if lines else ""

    def write_srt(self, file_path: str, segments: list[CaptionSegment]) -> int:
        content = self.serialize_srt(segments)
        target_path = Path(file_path).expanduser()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
        return sum(
            1
            for segment in segments
            if (segment.text or "").strip() and segment.end_seconds > segment.start_seconds
        )

    @staticmethod
    def _format_srt_timestamp(seconds: float) -> str:
        total_milliseconds = max(0, int(round(float(seconds) * 1000.0)))
        hours, remainder = divmod(total_milliseconds, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        whole_seconds, milliseconds = divmod(remainder, 1_000)
        return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"

    def parse_vtt(self, text: str) -> list[CaptionSegment]:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = normalized.split("\n")
        if lines and lines[0].lstrip("\ufeff").startswith("WEBVTT"):
            lines = lines[1:]
        blocks = self._split_blocks(lines)

        segments: list[CaptionSegment] = []
        for block in blocks:
            if not block:
                continue
            if block[0].strip().upper().startswith("NOTE"):
                continue
            segment = self._segment_from_block(block)
            if segment is not None:
                segments.append(segment)
        return segments

    @staticmethod
    def _split_blocks(lines: list[str]) -> list[list[str]]:
        blocks: list[list[str]] = []
        current: list[str] = []
        for raw_line in lines:
            line = raw_line.rstrip("\n")
            if line.strip():
                current.append(line)
                continue
            if current:
                blocks.append(current)
                current = []
        if current:
            blocks.append(current)
        return blocks

    def _segment_from_block(self, block: list[str]) -> CaptionSegment | None:
        time_line_index = self._time_line_index(block)
        if time_line_index < 0:
            return None

        start_seconds, end_seconds = self._parse_time_range(block[time_line_index])
        if end_seconds <= start_seconds:
            return None

        text_lines = block[time_line_index + 1 :]
        text = self._normalize_caption_text(text_lines)
        if not text:
            return None

        return CaptionSegment(start_seconds=start_seconds, end_seconds=end_seconds, text=text)

    def _time_line_index(self, block: list[str]) -> int:
        if not block:
            return -1
        if self._TIME_RANGE_MARKER in block[0]:
            return 0
        if len(block) > 1 and self._TIME_RANGE_MARKER in block[1]:
            return 1
        return -1

    def _parse_time_range(self, time_line: str) -> tuple[float, float]:
        if self._TIME_RANGE_MARKER not in time_line:
            raise ValueError(f"Invalid subtitle timing line: '{time_line}'")
        start_raw, end_raw = time_line.split(self._TIME_RANGE_MARKER, maxsplit=1)
        start_seconds = self._parse_timestamp(start_raw.strip().split(" ", maxsplit=1)[0])
        end_seconds = self._parse_timestamp(end_raw.strip().split(" ", maxsplit=1)[0])
        return start_seconds, end_seconds

    def _parse_timestamp(self, token: str) -> float:
        match = self._TIMESTAMP_RE.match(token)
        if match is None:
            raise ValueError(f"Invalid subtitle timestamp: '{token}'")

        hours_part, minutes_part, seconds_part, milliseconds_part = match.groups()
        hours = int(hours_part) if hours_part is not None else 0
        minutes = int(minutes_part)
        seconds = int(seconds_part)
        milliseconds = int((milliseconds_part or "0").ljust(3, "0")[:3])
        return (hours * 3600.0) + (minutes * 60.0) + seconds + (milliseconds / 1000.0)

    @staticmethod
    def _normalize_caption_text(lines: list[str]) -> str:
        compact_lines: list[str] = []
        for line in lines:
            cleaned = line.strip()
            if cleaned:
                compact_lines.append(cleaned)
        return "\n".join(compact_lines).strip()
