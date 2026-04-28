"""Tests for the dialog's lifecycle guards.

Focus on the close/reject path: while the OCR worker thread is running,
the dialog must refuse to close (otherwise Qt destroys an alive QThread
and threads accumulate across reopen cycles -- see PR review on #29).
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.services.settings_service import SettingsService  # noqa: E402
from app.ui.dialogs.extract_subtitle_dialog import ExtractSubtitleDialog  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _FakeRunningThread:
    """Drop-in for QThread that always reports as running."""

    def isRunning(self) -> bool:  # noqa: N802 - matches Qt API
        return True


def test_reject_blocked_while_thread_running(qapp, tmp_path, monkeypatch):
    settings = SettingsService(settings_path=str(tmp_path / "s.json"))
    dialog = ExtractSubtitleDialog(settings_service=settings)

    # Pretend a worker is mid-extraction.
    dialog._thread = _FakeRunningThread()  # type: ignore[assignment]

    info_calls: list[tuple[str, str]] = []

    def fake_info(parent, title, message, *_args, **_kwargs):
        info_calls.append((title, message))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "information", staticmethod(fake_info))

    dialog.reject()

    # super().reject() would have set the result code to Rejected; the guard
    # must short-circuit before that and tell the user why.
    assert dialog.result() == 0
    assert len(info_calls) == 1
    assert "trích xuất" in info_calls[0][1].lower()


def test_close_event_ignored_while_thread_running(qapp, tmp_path, monkeypatch):
    settings = SettingsService(settings_path=str(tmp_path / "s.json"))
    dialog = ExtractSubtitleDialog(settings_service=settings)
    dialog._thread = _FakeRunningThread()  # type: ignore[assignment]

    monkeypatch.setattr(
        QMessageBox,
        "information",
        staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Ok),
    )

    class _Event:
        def __init__(self) -> None:
            self.accepted = True

        def ignore(self) -> None:
            self.accepted = False

        def accept(self) -> None:
            self.accepted = True

    event = _Event()
    dialog.closeEvent(event)
    assert event.accepted is False


def test_on_failed_clears_thread_ref_before_message_box(qapp, tmp_path, monkeypatch):
    """Reproduces stale `self._thread` after error: critical() spins event loop,
    finished -> deleteLater fires, then _is_extraction_running would touch a
    deleted C++ object. Fix: clear refs *before* QMessageBox.critical."""

    settings = SettingsService(settings_path=str(tmp_path / "s.json"))
    dialog = ExtractSubtitleDialog(settings_service=settings)

    sentinel_thread = _FakeRunningThread()
    sentinel_worker = object()
    dialog._thread = sentinel_thread  # type: ignore[assignment]
    dialog._worker = sentinel_worker  # type: ignore[assignment]

    captured: dict[str, object] = {}

    def fake_critical(parent, title, message, *_args, **_kwargs):
        captured["thread_at_messagebox"] = dialog._thread
        captured["worker_at_messagebox"] = dialog._worker
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "critical", staticmethod(fake_critical))

    dialog._on_failed("boom")

    assert captured["thread_at_messagebox"] is None
    assert captured["worker_at_messagebox"] is None
    assert dialog._thread is None
    assert dialog._worker is None


def test_reject_passes_through_when_idle(qapp, tmp_path, monkeypatch):
    settings = SettingsService(settings_path=str(tmp_path / "s.json"))
    dialog = ExtractSubtitleDialog(settings_service=settings)

    info_calls: list[tuple[str, str]] = []

    def fake_info(parent, title, message, *_args, **_kwargs):
        info_calls.append((title, message))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "information", staticmethod(fake_info))

    # No _thread set -> reject must not pop a "wait" message; super().reject
    # is allowed to dismiss the dialog as normal.
    dialog.reject()
    assert info_calls == []
