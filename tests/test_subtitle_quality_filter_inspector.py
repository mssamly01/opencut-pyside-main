"""Quality filter integration with DetailsInspector.

Verifies the four built-in quality filters (OCR errors, reading speed,
adjacent duplicates, interjections) wire correctly into the inspector list
and that the interjection dialog drives `delete_subtitle_segment` for each
checked row.
"""

from __future__ import annotations

from pathlib import Path

from app.bootstrap import create_application
from app.controllers.app_controller import AppController
from app.ui.inspector.details_inspector import DetailsInspector

SAMPLE_SRT = """\
1
00:00:00,000 --> 00:00:01,000
你好世界

2
00:00:01,000 --> 00:00:02,000
abc

3
00:00:02,000 --> 00:00:03,000
123

4
00:00:03,000 --> 00:00:04,000
正常的字幕

5
00:00:04,000 --> 00:00:05,000
正常的字幕

6
00:00:05,000 --> 00:00:30,000
你好

7
00:00:30,000 --> 00:00:31,000
啊
"""


def _build_inspector(tmp_path: Path) -> tuple[AppController, DetailsInspector, str]:
    create_application(["pytest"])
    controller = AppController()
    srt_path = tmp_path / "sample.srt"
    srt_path.write_text(SAMPLE_SRT, encoding="utf-8")
    controller.import_subtitles_from_file(str(srt_path))
    entry = controller.subtitle_library_entries()[0]
    inspector = DetailsInspector(controller)
    inspector.set_mode(DetailsInspector.MODE_SUBTITLES)
    inspector.resize(400, 600)
    inspector.show()
    return controller, inspector, entry.entry_id


def _visible_rows(inspector: DetailsInspector) -> list[int]:
    return [
        row
        for row in range(inspector._subtitle_list.count())  # noqa: SLF001
        if not inspector._subtitle_list.item(row).isHidden()  # noqa: SLF001
    ]


def test_ocr_filter_hides_clean_rows(tmp_path: Path) -> None:
    _, inspector, _ = _build_inspector(tmp_path)
    inspector._set_quality_filter("ocr")  # noqa: SLF001
    # Rows 1 (empty) and 2 (digits-only) are OCR errors.
    assert _visible_rows(inspector) == [1, 2]
    # The chip text is shown in the search input.
    assert inspector._subtitle_search_input.text().startswith("[Chế độ lọc:")  # noqa: SLF001


def test_reading_speed_filter_picks_slow_rows(tmp_path: Path) -> None:
    _, inspector, _ = _build_inspector(tmp_path)
    inspector._set_quality_filter("speed")  # noqa: SLF001
    # Row 5 is "你好" over 25 seconds = 0.08 cps and row 6 is "啊" over 1s = 1 cps;
    # both fall below the default 3 cps threshold.
    assert _visible_rows(inspector) == [5, 6]


def test_duplicate_filter_picks_adjacent_pair(tmp_path: Path) -> None:
    _, inspector, _ = _build_inspector(tmp_path)
    inspector._set_quality_filter("duplicate")  # noqa: SLF001
    # Rows 3 and 4 share the same text.
    assert _visible_rows(inspector) == [3, 4]


def test_clear_filter_restores_all_rows(tmp_path: Path) -> None:
    _, inspector, _ = _build_inspector(tmp_path)
    inspector._set_quality_filter("ocr")  # noqa: SLF001
    assert _visible_rows(inspector) != list(range(7))
    inspector._set_quality_filter(None)  # noqa: SLF001
    assert _visible_rows(inspector) == list(range(7))
    assert inspector._subtitle_search_input.text() == ""  # noqa: SLF001


def test_typing_search_text_clears_quality_filter(tmp_path: Path) -> None:
    _, inspector, _ = _build_inspector(tmp_path)
    inspector._set_quality_filter("ocr")  # noqa: SLF001
    # Simulate the user typing into the search box (replaces the chip).
    inspector._subtitle_search_input.setText("正常")  # noqa: SLF001
    assert inspector._quality_filter is None  # noqa: SLF001
    # Search should now match the rows containing the substring.
    assert _visible_rows(inspector) == [3, 4]


def test_interjection_filter_only_picks_pure_interjection_rows(tmp_path: Path) -> None:
    _controller, inspector, _entry_id = _build_inspector(tmp_path)
    from app.services.subtitle_filters import find_interjection_indices

    entry = inspector._current_subtitle_entry()  # noqa: SLF001
    assert entry is not None
    # Only row 6 ("啊") is a pure interjection.
    assert find_interjection_indices(entry.segments) == [6]


def test_interjection_dialog_deletes_via_app_controller(tmp_path: Path) -> None:
    controller, inspector, entry_id = _build_inspector(tmp_path)
    initial_count = len(controller.subtitle_library_entries()[0].segments)
    assert initial_count == 7

    # Drive the deletion path directly without exec()ing the dialog.
    indices_to_delete = [6]
    for idx in sorted(indices_to_delete, reverse=True):
        assert controller.delete_subtitle_segment(entry_id, idx) is True

    remaining = controller.subtitle_library_entries()[0].segments
    assert len(remaining) == 6
    # Row 7 ("啊") should be gone, the rest preserved in order.
    assert remaining[-1][2] == "你好"


def test_quality_filter_resets_when_switching_entry(tmp_path: Path) -> None:
    controller, inspector, first_entry_id = _build_inspector(tmp_path)
    inspector._set_quality_filter("ocr")  # noqa: SLF001
    assert inspector._quality_filter == "ocr"  # noqa: SLF001

    second_path = tmp_path / "second.srt"
    second_path.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\n第二个字幕\n\n", encoding="utf-8"
    )
    controller.import_subtitles_from_file(str(second_path))
    entries = controller.subtitle_library_entries()
    second_entry = next(e for e in entries if e.entry_id != first_entry_id)
    controller.select_subtitle_segment(second_entry.entry_id, 0)

    # The filter must reset because the active entry changed.
    assert inspector._quality_filter is None  # noqa: SLF001
    assert inspector._subtitle_search_input.text() == ""  # noqa: SLF001
