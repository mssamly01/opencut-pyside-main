"""Sprint 16-D: end-to-end i18n smoke tests.

Loads the compiled English .qm via a fresh QTranslator and verifies that
known Vietnamese source strings used in the UI translate to their expected
English values. Default (no translator installed) must keep the Vietnamese
source — that is the documented behaviour because Vietnamese is the source
language.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QTranslator
from PySide6.QtWidgets import QApplication

I18N_DIR = Path(__file__).resolve().parents[1] / "i18n"
EN_QM = I18N_DIR / "opencut_en.qm"


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_default_locale_returns_vietnamese_source(qapp):
    # No translator installed for this lookup -> tr() must return the source
    # string verbatim. Use a known UI string from MediaPanel.
    text = QCoreApplication.translate("MediaPanel", "Thư viện phương tiện")
    assert text == "Thư viện phương tiện"


def test_english_qm_translates_known_strings(qapp):
    if not EN_QM.is_file():
        pytest.skip(
            "compiled opencut_en.qm not available; "
            "run ./scripts/update_translations.sh to build it"
        )
    translator = QTranslator(qapp)
    assert translator.load(str(EN_QM)), f"failed to load {EN_QM}"
    qapp.installTranslator(translator)
    try:
        # Spot-check a representative string from each major UI surface so
        # this test fails loudly if a context disappears from the .qm.
        assert (
            QCoreApplication.translate("MediaPanel", "Thư viện phương tiện")
            == "Media Library"
        )
        assert (
            QCoreApplication.translate("MediaPanel", "  Nhập phương tiện...")
            == "  Import Media..."
        )
        assert (
            QCoreApplication.translate("ClipInspectorBase", "Tên clip")
            == "Clip Name"
        )
        assert (
            QCoreApplication.translate("EffectsDrawer", "Chuyển cảnh")
            == "Transitions"
        )
        assert (
            QCoreApplication.translate("MainWindow", "Lưu")
            == "Save"
        )
    finally:
        qapp.removeTranslator(translator)


def test_no_unfinished_entries_in_translation_files():
    for ts in (I18N_DIR / "opencut_vi.ts", I18N_DIR / "opencut_en.ts"):
        text = ts.read_text(encoding="utf-8")
        assert 'type="unfinished"' not in text, f"{ts.name} still has unfinished entries"
