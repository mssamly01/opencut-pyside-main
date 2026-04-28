"""Integration tests for AppController.replace_all_in_subtitle_entry.

Ensures the bulk replace path updates segments, ignores empty-result rows,
emits subtitle_library_changed exactly once and refreshes the inspector
cache via the existing incremental code path.
"""

from __future__ import annotations

from pathlib import Path

from app.bootstrap import create_application
from app.controllers.app_controller import AppController
from app.ui.inspector.details_inspector import DetailsInspector

SAMPLE_SRT = """\
1
00:00:00,000 --> 00:00:01,000
Hello world

2
00:00:01,000 --> 00:00:02,000
WORLD goodbye

3
00:00:02,000 --> 00:00:03,000
no match here
"""


def _build_controller(tmp_path: Path) -> tuple[AppController, str]:
    create_application(["pytest"])
    controller = AppController()
    srt_path = tmp_path / "sample.srt"
    srt_path.write_text(SAMPLE_SRT, encoding="utf-8")
    controller.import_subtitles_from_file(str(srt_path))
    entry = controller.subtitle_library_entries()[0]
    return controller, entry.entry_id


def test_replace_all_case_insensitive_returns_count_and_updates_segments(tmp_path: Path):
    controller, entry_id = _build_controller(tmp_path)

    count = controller.replace_all_in_subtitle_entry(
        entry_id, "world", "Earth", case_sensitive=False
    )

    assert count == 2
    segments = controller.subtitle_library_entries()[0].segments
    assert [text for _s, _e, text in segments] == [
        "Hello Earth",
        "Earth goodbye",
        "no match here",
    ]


def test_replace_all_case_sensitive_only_replaces_exact_case(tmp_path: Path):
    controller, entry_id = _build_controller(tmp_path)

    count = controller.replace_all_in_subtitle_entry(
        entry_id, "world", "Earth", case_sensitive=True
    )

    assert count == 1
    segments = controller.subtitle_library_entries()[0].segments
    assert [text for _s, _e, text in segments] == [
        "Hello Earth",
        "WORLD goodbye",  # untouched because case differs
        "no match here",
    ]


def test_replace_all_returns_zero_when_no_match(tmp_path: Path):
    controller, entry_id = _build_controller(tmp_path)
    count = controller.replace_all_in_subtitle_entry(
        entry_id, "missing", "x", case_sensitive=False
    )
    assert count == 0
    # Segments must not be touched when nothing matched.
    segments = controller.subtitle_library_entries()[0].segments
    assert [text for _s, _e, text in segments] == [
        "Hello world",
        "WORLD goodbye",
        "no match here",
    ]


def test_replace_all_empty_find_text_returns_zero(tmp_path: Path):
    controller, entry_id = _build_controller(tmp_path)
    assert (
        controller.replace_all_in_subtitle_entry(
            entry_id, "", "x", case_sensitive=False
        )
        == 0
    )


def test_replace_all_skips_segments_that_would_become_empty(tmp_path: Path):
    controller, entry_id = _build_controller(tmp_path)
    # Replacing the entire text of segment 2 with "" would leave it empty —
    # the controller should refuse that change but still apply the other
    # segments and report only the kept count.
    count = controller.replace_all_in_subtitle_entry(
        entry_id, "WORLD goodbye", "", case_sensitive=True
    )
    assert count == 0
    segments = controller.subtitle_library_entries()[0].segments
    assert segments[1][2] == "WORLD goodbye"


def test_replace_all_count_excludes_rejected_segment_occurrences(tmp_path: Path):
    """Mixed valid/rejected case must not inflate the user-facing count.

    Setup: build an entry where one segment contains the find-text twice and
    another segment is exactly the find-text (so replacement → empty and is
    rejected). The reported count must be 2, not 3, since only the first
    segment's two occurrences were actually written back.
    """

    create_application(["pytest"])
    controller = AppController()
    srt_path = tmp_path / "mixed.srt"
    srt_path.write_text(
        """\
1
00:00:00,000 --> 00:00:01,000
world world hello

2
00:00:01,000 --> 00:00:02,000
world
""",
        encoding="utf-8",
    )
    controller.import_subtitles_from_file(str(srt_path))
    entry_id = controller.subtitle_library_entries()[0].entry_id

    count = controller.replace_all_in_subtitle_entry(
        entry_id, "world", "", case_sensitive=False
    )

    assert count == 2  # NOT 3 — segment 2's occurrence was rejected
    segments = controller.subtitle_library_entries()[0].segments
    assert segments[0][2] == "  hello"  # both occurrences replaced with ""
    assert segments[1][2] == "world"  # untouched because new_text was empty


def test_replace_all_emits_library_changed_once(tmp_path: Path):
    controller, entry_id = _build_controller(tmp_path)
    received: list[None] = []
    controller.subtitle_library_changed.connect(lambda: received.append(None))

    controller.replace_all_in_subtitle_entry(
        entry_id, "world", "Earth", case_sensitive=False
    )

    assert len(received) == 1


def test_replace_all_refreshes_inspector_text_cache(tmp_path: Path):
    controller, entry_id = _build_controller(tmp_path)
    inspector = DetailsInspector(controller)
    inspector.set_mode(DetailsInspector.MODE_SUBTITLES)
    inspector.resize(400, 600)
    inspector.show()

    controller.replace_all_in_subtitle_entry(
        entry_id, "world", "Earth", case_sensitive=False
    )

    # The lower-cased cache feeds the search filter; it must reflect the new
    # segment texts after the bulk replace.
    assert inspector._subtitle_text_lower_cache[0] == "hello earth"  # noqa: SLF001
    assert inspector._subtitle_text_lower_cache[1] == "earth goodbye"  # noqa: SLF001
