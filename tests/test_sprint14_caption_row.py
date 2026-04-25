"""Sprint 14: CaptionRowWidget commits on Enter and reverts on Escape."""

from __future__ import annotations

from app.bootstrap import create_application
from app.domain.clips.text_clip import TextClip
from app.ui.captions_row_widget import CaptionRowWidget
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest


def _make_text_clip(content: str = "Hello") -> TextClip:
    return TextClip(
        clip_id="cap1",
        name="caption",
        track_id="t1",
        timeline_start=0.0,
        duration=2.0,
        media_id=None,
        content=content,
    )


def test_caption_row_commits_on_enter() -> None:
    create_application(["pytest"])
    clip = _make_text_clip("Hello")
    captured: list[tuple[str, str]] = []

    row = CaptionRowWidget(
        clip=clip,
        timestamp_label="[00:00.000 - 00:02.000]",
        commit_callback=lambda clip_id, text: captured.append((clip_id, text)),
    )
    row.show()
    row.begin_edit()

    row._text_edit.setText("World")
    QTest.keyClick(row._text_edit, Qt.Key.Key_Return)

    assert captured == [("cap1", "World")]


def test_caption_row_reverts_on_escape() -> None:
    create_application(["pytest"])
    clip = _make_text_clip("Hello")
    captured: list[tuple[str, str]] = []

    row = CaptionRowWidget(
        clip=clip,
        timestamp_label="[00:00.000 - 00:02.000]",
        commit_callback=lambda clip_id, text: captured.append((clip_id, text)),
    )
    row.show()
    row.begin_edit()

    row._text_edit.setText("Discarded")
    QTest.keyClick(row._text_edit, Qt.Key.Key_Escape)

    assert row._text_edit.text() == "Hello"
    assert captured == []
