"""Bulk text-replace operations for subtitle segments.

Pure-Python helper, no Qt imports. Mirrors
``MainWindow.replace_all_subtitles`` in the reference ``editor_app.py``.
Case-insensitive replace preserves the surrounding text untouched and only
swaps the matched range with ``replace_text``.
"""

from __future__ import annotations

from collections.abc import Sequence

Segment = tuple[float, float, str]


def replace_all_in_text(
    text: str,
    find: str,
    replace: str,
    *,
    case_sensitive: bool,
) -> tuple[str, int]:
    """Replace every occurrence of ``find`` in ``text``.

    Returns ``(new_text, count)``. When ``case_sensitive`` is ``False`` the
    match is case-insensitive but the rest of the string keeps its original
    casing (only the matched substring is rewritten).
    """

    if not find:
        return text, 0
    if case_sensitive:
        count = text.count(find)
        if count == 0:
            return text, 0
        return text.replace(find, replace), count

    needle = find.lower()
    haystack = text.lower()
    if needle not in haystack:
        return text, 0

    parts: list[str] = []
    idx = 0
    count = 0
    while idx < len(text):
        pos = haystack.find(needle, idx)
        if pos == -1:
            parts.append(text[idx:])
            break
        parts.append(text[idx:pos])
        parts.append(replace)
        idx = pos + len(find)
        count += 1
    return "".join(parts), count


def replace_all_in_segments(
    segments: Sequence[Segment],
    find: str,
    replace: str,
    *,
    case_sensitive: bool,
) -> tuple[list[tuple[int, str]], int]:
    """Apply :func:`replace_all_in_text` to every segment text.

    Returns ``(changes, total_count)`` where ``changes`` is a list of
    ``(segment_index, new_text)`` tuples covering only segments whose text
    actually changed.
    """

    if not find:
        return [], 0

    changes: list[tuple[int, str]] = []
    total = 0
    for idx, (_start, _end, text) in enumerate(segments):
        new_text, count = replace_all_in_text(
            text, find, replace, case_sensitive=case_sensitive
        )
        if count > 0:
            changes.append((idx, new_text))
            total += count
    return changes, total
