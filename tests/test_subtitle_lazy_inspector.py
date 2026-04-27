"""Lazy-attach behavior of the subtitle inspector list.

Ensures large subtitle entries don't materialize a custom widget per row up-front,
and that text edits don't rebuild the entire list.
"""

from __future__ import annotations

from pathlib import Path

from app.bootstrap import create_application
from app.controllers.app_controller import AppController
from app.ui.inspector.details_inspector import DetailsInspector


def _write_long_srt(path: Path, count: int) -> None:
    lines: list[str] = []
    for i in range(count):
        start = i * 2
        end = start + 1
        sh, sm, ss = start // 3600, (start % 3600) // 60, start % 60
        eh, em, es = end // 3600, (end % 3600) // 60, end % 60
        lines.append(str(i + 1))
        lines.append(f"{sh:02d}:{sm:02d}:{ss:02d},000 --> {eh:02d}:{em:02d}:{es:02d},000")
        lines.append(f"Line {i + 1}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def test_large_subtitle_entry_attaches_only_visible_widgets(tmp_path: Path) -> None:
    create_application(["pytest"])
    app_controller = AppController()
    subtitle_path = tmp_path / "long.srt"
    _write_long_srt(subtitle_path, 500)
    app_controller.import_subtitles_from_file(str(subtitle_path))

    inspector = DetailsInspector(app_controller)
    inspector.set_mode(DetailsInspector.MODE_SUBTITLES)
    inspector.resize(400, 300)
    inspector.show()

    assert len(inspector._subtitle_rows) == 500  # noqa: SLF001
    # Only a small bounded set of rows should have actual row widgets attached.
    attached = inspector._attached_widget_rows  # noqa: SLF001
    assert len(attached) < 100, f"expected few attached widgets, got {len(attached)}"


def test_text_edit_does_not_rebuild_subtitle_list(tmp_path: Path) -> None:
    create_application(["pytest"])
    app_controller = AppController()
    subtitle_path = tmp_path / "edit.srt"
    _write_long_srt(subtitle_path, 50)
    app_controller.import_subtitles_from_file(str(subtitle_path))
    entry = app_controller.subtitle_library_entries()[0]

    inspector = DetailsInspector(app_controller)
    inspector.set_mode(DetailsInspector.MODE_SUBTITLES)
    inspector.resize(400, 600)
    inspector.show()

    items_before = [inspector._subtitle_list.item(i) for i in range(inspector._subtitle_list.count())]  # noqa: SLF001

    app_controller.update_subtitle_segment_text(entry.entry_id, 3, "Updated line")

    items_after = [inspector._subtitle_list.item(i) for i in range(inspector._subtitle_list.count())]  # noqa: SLF001
    # Same QListWidgetItem instances => list was not rebuilt.
    assert items_before == items_after
    # Cached lower-text reflects the edit so future filter queries are correct.
    assert inspector._subtitle_text_lower_cache[3] == "updated line"  # noqa: SLF001


def test_long_subtitle_row_uses_taller_size_hint(tmp_path: Path) -> None:
    """Multi-line / long-wrapping subtitles get a taller QListWidgetItem."""

    create_application(["pytest"])
    app_controller = AppController()
    srt_path = tmp_path / "mixed.srt"
    short_text = "Hi"
    # Long enough to wrap onto multiple lines at typical inspector widths.
    long_text = (
        "This is a very long subtitle line that definitely needs to wrap across "
        "multiple visual lines inside the narrow inspector panel — it contains "
        "enough words to overflow a single line at 400 px viewport width."
    )
    srt_path.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\n"
        f"{short_text}\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\n"
        f"{long_text}\n\n",
        encoding="utf-8",
    )
    app_controller.import_subtitles_from_file(str(srt_path))

    inspector = DetailsInspector(app_controller)
    inspector.set_mode(DetailsInspector.MODE_SUBTITLES)
    inspector.resize(400, 600)
    inspector.show()

    short_height = inspector._subtitle_list.item(0).sizeHint().height()  # noqa: SLF001
    long_height = inspector._subtitle_list.item(1).sizeHint().height()  # noqa: SLF001
    assert long_height > short_height, (
        f"long row ({long_height}px) should be taller than short row ({short_height}px)"
    )
    # The long row should have at least two lines worth of vertical pixels.
    assert long_height >= short_height * 2 - 8


def test_subtitle_row_preserves_explicit_newlines(tmp_path: Path) -> None:
    """Multi-line SRT segments keep their newline structure in the cache."""

    create_application(["pytest"])
    app_controller = AppController()
    srt_path = tmp_path / "multiline.srt"
    srt_path.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\n"
        "First line\nSecond line\n\n",
        encoding="utf-8",
    )
    app_controller.import_subtitles_from_file(str(srt_path))

    inspector = DetailsInspector(app_controller)
    inspector.set_mode(DetailsInspector.MODE_SUBTITLES)
    inspector.resize(400, 300)
    inspector.show()

    cached = inspector._subtitle_text_cache[0]  # noqa: SLF001
    assert "\n" in cached, f"newline preserved, got: {cached!r}"
    assert cached.startswith("First line")
    assert cached.endswith("Second line")
