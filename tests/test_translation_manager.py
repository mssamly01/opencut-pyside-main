"""Smoke tests for the i18n / translation layer."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.infrastructure import translation_manager as tm
from PySide6.QtWidgets import QApplication


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_default_language_is_vietnamese(monkeypatch):
    monkeypatch.delenv("OPENCUT_LANG", raising=False)
    # Force an unsupported system locale so we fall through to the default.
    monkeypatch.setattr(
        tm, "QLocale", _FakeQLocale("zz_ZZ"), raising=True
    )
    assert tm.resolve_language() == "vi"


def test_env_var_overrides_default(monkeypatch):
    monkeypatch.setenv("OPENCUT_LANG", "en")
    assert tm.resolve_language() == "en"


def test_explicit_argument_takes_highest_priority(monkeypatch):
    monkeypatch.setenv("OPENCUT_LANG", "en")
    assert tm.resolve_language("vi") == "vi"


def test_unsupported_language_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("OPENCUT_LANG", raising=False)
    monkeypatch.setattr(tm, "QLocale", _FakeQLocale("zz_ZZ"), raising=True)
    assert tm.resolve_language("klingon") == "vi"


def test_supported_system_locale_is_used(monkeypatch):
    monkeypatch.delenv("OPENCUT_LANG", raising=False)
    monkeypatch.setattr(tm, "QLocale", _FakeQLocale("en_US"), raising=True)
    assert tm.resolve_language() == "en"


def test_unsupported_system_locale_falls_through_to_default(monkeypatch):
    # Regression test: the system-locale branch must NOT pass the value
    # through _normalise (which would collapse unsupported locales onto the
    # default and make the membership guard a no-op).
    monkeypatch.delenv("OPENCUT_LANG", raising=False)
    monkeypatch.setattr(tm, "QLocale", _FakeQLocale("de_DE"), raising=True)
    assert tm.resolve_language() == "vi"


def test_repo_root_uses_meipass_when_frozen(monkeypatch, tmp_path):
    # Simulate a PyInstaller bundle: sys.frozen=True, sys._MEIPASS set to
    # the bundle root. _repo_root must return that instead of walking up
    # from __file__ (which would land inside <_MEIPASS>/app/).
    monkeypatch.setattr(tm.sys, "frozen", True, raising=False)
    monkeypatch.setattr(tm.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert tm._repo_root() == tmp_path


def test_repo_root_uses_file_when_not_frozen(monkeypatch):
    # Development run: sys.frozen is missing / False. Must walk up from
    # translation_manager.py's location.
    monkeypatch.setattr(tm.sys, "frozen", False, raising=False)
    expected = Path(tm.__file__).resolve().parent.parent
    assert tm._repo_root() == expected


def test_install_translators_is_noop_when_no_qm(tmp_path, qapp, monkeypatch):
    monkeypatch.delenv("OPENCUT_LANG", raising=False)
    # Empty directory -> nothing to install, function must not raise.
    installed = tm.install_translators(qapp, language="vi", i18n_dir=tmp_path)
    assert installed == []


def test_install_translators_loads_existing_qm(tmp_path, qapp, monkeypatch):
    # Use lrelease on the in-repo .ts to get a real .qm, but since pyside6
    # tooling is optional in dev environments we fabricate a minimal .qm
    # by copying any compiled translation produced by build. If no .qm is
    # available the test is skipped rather than flaky.
    from pathlib import Path

    real_qm = _find_any_qm(Path(__file__).resolve().parents[1] / "i18n")
    if real_qm is None:
        pytest.skip("no compiled .qm available in i18n/ (run scripts/update_translations.sh)")
    target = tmp_path / "opencut_vi.qm"
    target.write_bytes(real_qm.read_bytes())

    installed = tm.install_translators(qapp, language="vi", i18n_dir=tmp_path)
    assert len(installed) == 1


class _FakeQLocale:
    """Drop-in QLocale replacement returning a fixed system locale."""

    def __init__(self, locale: str) -> None:
        self._locale = locale

    def system(self):  # noqa: D401 - mimics QLocale.system
        return self

    def name(self) -> str:
        return self._locale


def _find_any_qm(directory):
    if not directory.is_dir():
        return None
    for candidate in directory.glob("*.qm"):
        return candidate
    return None
