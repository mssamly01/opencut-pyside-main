"""Quality filters for subtitle segments.

Pure-Python helpers, no Qt imports — safe to call from controllers, services
and tests. Inputs are sequences of ``(start_seconds, end_seconds, text)``
tuples (the shape used by ``SubtitleLibraryEntry.segments``).

Translated from the reference ``editor_app.py``:

- :func:`is_ocr_error` → ``MainWindow._is_ocr_error_text``
- :func:`is_reading_speed_outlier` → ``MainWindow._is_reading_speed_outlier``
- :func:`find_adjacent_duplicate_indices` →
  ``MainWindow._get_adjacent_duplicate_rows``
- :func:`is_chinese_interjection_only` →
  ``MainWindow.filter_and_delete_interjections.is_interjection``
"""

from __future__ import annotations

import re
from collections.abc import Sequence

Segment = tuple[float, float, str]

# --- OCR error detection --------------------------------------------------

OCR_DIGITS_ONLY_REGEX = re.compile(r"[0-9\s]+")
OCR_INVALID_CHAR_REGEX = re.compile(
    r"[^0-9\u4e00-\u9fff\uFF0C\u3002\uFF01\uFF1F\u3001\uFF1A\uFF1B"
    r"\uFF08\uFF09\u300A\u300B\u201C\u201D\u2018\u2019.,!?()\[\]\-]"
)
OCR_MEANINGFUL_CHAR_REGEX = re.compile(
    r"[0-9A-Za-z\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"
)

# --- Reading speed --------------------------------------------------------

_READING_CHAR_REGEX = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaffA-Za-z0-9]"
)
DEFAULT_MIN_READING_CPS = 3.0

# --- Interjection detection ----------------------------------------------

CHINESE_INTERJECTIONS: frozenset[str] = frozenset(
    "啊喔呃呀嘿嘘哼喂哈嘻呢吗哒嗷咕唏咿呐嘀咳"
)


def normalize_whitespace(text: str | None) -> str:
    """Map NBSP / full-width space / tab to ASCII space.

    Mirrors ``editor_app.normalize_whitespace`` so OCR-error and duplicate
    detection treat exotic whitespace consistently.
    """

    if not text:
        return ""
    return text.replace("\xa0", " ").replace("\u3000", " ").replace("\t", " ")


def is_ocr_error(text: str | None) -> bool:
    """Return True if *text* looks like a garbage OCR row.

    A row is considered an OCR error when, after whitespace normalization, it
    is empty, contains only digits/whitespace, contains a character outside
    the allow-list (CJK + Vietnamese punctuation + ASCII punctuation/digits),
    or has no digits/letters at all.
    """

    normalized = normalize_whitespace(text or "").strip()
    if not normalized:
        return True
    if OCR_DIGITS_ONLY_REGEX.fullmatch(normalized):
        return True
    if OCR_INVALID_CHAR_REGEX.search(normalized):
        return True
    return OCR_MEANINGFUL_CHAR_REGEX.search(normalized) is None


def reading_chars_count(text: str | None) -> int:
    """Count CJK + Latin + digit characters in *text*."""

    if not text:
        return 0
    normalized = normalize_whitespace(text).replace("\n", " ")
    return len(_READING_CHAR_REGEX.findall(normalized))


def is_reading_speed_outlier(
    segment: Segment,
    *,
    min_cps: float = DEFAULT_MIN_READING_CPS,
) -> bool:
    """Return True if *segment* reads slower than ``min_cps`` chars/second.

    Empty rows return False (covered by the OCR filter instead). Duration is
    floored at 1ms to avoid divide-by-zero on degenerate cues.
    """

    start, end, text = segment
    char_count = reading_chars_count(text)
    if char_count <= 0:
        return False
    duration = max(float(end) - float(start), 1e-3)
    return (char_count / duration) < min_cps


def _normalize_for_duplicate_compare(text: str | None) -> str:
    normalized = normalize_whitespace(text or "")
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    return normalized


def is_chinese_interjection_only(text: str | None) -> bool:
    """Return True if *text* contains only Chinese interjection characters.

    Whitespace and punctuation are ignored. An empty row returns False (the
    OCR filter already covers those).
    """

    if not text:
        return False
    clean_chars = [c for c in text if c.isalpha() or "\u4e00" <= c <= "\u9fff"]
    if not clean_chars:
        return False
    return all(c in CHINESE_INTERJECTIONS for c in clean_chars)


def find_ocr_error_indices(segments: Sequence[Segment]) -> list[int]:
    return [i for i, (_s, _e, text) in enumerate(segments) if is_ocr_error(text)]


def find_reading_speed_outlier_indices(
    segments: Sequence[Segment],
    *,
    min_cps: float = DEFAULT_MIN_READING_CPS,
) -> list[int]:
    return [
        i
        for i, segment in enumerate(segments)
        if is_reading_speed_outlier(segment, min_cps=min_cps)
    ]


def find_adjacent_duplicate_indices(segments: Sequence[Segment]) -> list[int]:
    """Return indices of segments whose normalized text matches their neighbour."""

    duplicate_rows: set[int] = set()
    prev_text: str | None = None
    prev_idx: int | None = None
    for idx, (_s, _e, text) in enumerate(segments):
        current = _normalize_for_duplicate_compare(text)
        if current and prev_text and current == prev_text and prev_idx is not None:
            duplicate_rows.add(prev_idx)
            duplicate_rows.add(idx)
        prev_text = current
        prev_idx = idx
    return sorted(duplicate_rows)


def find_interjection_indices(segments: Sequence[Segment]) -> list[int]:
    return [
        i
        for i, (_s, _e, text) in enumerate(segments)
        if is_chinese_interjection_only(text)
    ]
