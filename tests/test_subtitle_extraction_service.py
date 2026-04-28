"""Tests for app.services.subtitle_extraction_service.

The service intentionally lazy-imports paddle / paddleocr / cv2 so the
opencut test suite can run on machines without the GPU stack. These
tests therefore exercise:

  - the availability probe (deps + model dir),
  - the model-dir env var helpers,
  - the settings.ini renderer that the vendored engine reads at import
    time,
  - argument validation on the public ``extract_subtitles`` entry point
    when the engine is not installed.

We do NOT exercise the engine itself here -- that requires PaddleOCR +
the 100 MB model bundle, which the user provides out-of-tree.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import app.services.subtitle_extraction_service as svc
import pytest


@pytest.fixture(autouse=True)
def _restore_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Always start each test with an empty model-dir env var."""

    monkeypatch.delenv(svc.MODEL_DIR_ENV, raising=False)


def test_set_model_dir_round_trip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(svc.MODEL_DIR_ENV, raising=False)
    assert svc.get_model_dir() is None

    target = tmp_path / "ocr-models"
    target.mkdir()
    svc.set_model_dir(str(target))
    assert svc.get_model_dir() == str(target)

    svc.set_model_dir(None)
    assert svc.get_model_dir() is None


def test_is_available_reports_missing_dep(monkeypatch: pytest.MonkeyPatch) -> None:
    """When a runtime dep is absent, ``is_available`` must say so."""

    real_import = importlib.import_module

    def fake_import(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name in {"cv2", "paddle", "paddleocr", "pysrt"}:
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(svc.importlib, "import_module", fake_import)

    result = svc.is_available()
    assert result.ok is False
    assert "pip install" in result.hint


def test_is_available_reports_missing_model_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """All deps importable but no model dir configured -> not ok."""

    real_import = importlib.import_module

    def fake_import(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name in {"cv2", "paddle", "paddleocr", "pysrt"}:
            return type("FakeModule", (), {})()
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(svc.importlib, "import_module", fake_import)
    monkeypatch.delenv(svc.MODEL_DIR_ENV, raising=False)

    result = svc.is_available()
    assert result.ok is False
    assert "models" in result.hint.lower()


def test_is_available_reports_missing_v4_subdir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    real_import = importlib.import_module

    def fake_import(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name in {"cv2", "paddle", "paddleocr", "pysrt"}:
            return type("FakeModule", (), {})()
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(svc.importlib, "import_module", fake_import)
    svc.set_model_dir(str(tmp_path))  # exists but no V4/

    result = svc.is_available()
    assert result.ok is False
    assert "V4" in result.hint


def test_is_available_ok_when_all_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    real_import = importlib.import_module

    def fake_import(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name in {"cv2", "paddle", "paddleocr", "pysrt"}:
            return type("FakeModule", (), {})()
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(svc.importlib, "import_module", fake_import)

    model_root = tmp_path / "models"
    (model_root / "V4").mkdir(parents=True)
    svc.set_model_dir(str(model_root))

    result = svc.is_available()
    assert result.ok is True
    assert result.hint == ""


def test_extract_subtitles_raises_when_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If deps are missing, the public entry point surfaces the hint."""

    real_import = importlib.import_module

    def fake_import(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "paddle":
            raise ImportError("paddle")
        if name in {"cv2", "paddleocr", "pysrt"}:
            return type("FakeModule", (), {})()
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(svc.importlib, "import_module", fake_import)

    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")

    with pytest.raises(RuntimeError) as excinfo:
        svc.extract_subtitles(
            video_path=str(video),
            subtitle_area=(0, 100, 0, 100),
        )
    assert "paddle" in str(excinfo.value).lower()


def test_extract_subtitles_validates_language(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    real_import = importlib.import_module

    def fake_import(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name in {"cv2", "paddle", "paddleocr", "pysrt"}:
            return type("FakeModule", (), {})()
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(svc.importlib, "import_module", fake_import)
    model_root = tmp_path / "models"
    (model_root / "V4").mkdir(parents=True)
    svc.set_model_dir(str(model_root))

    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")

    with pytest.raises(ValueError, match="Unsupported language"):
        svc.extract_subtitles(
            video_path=str(video),
            subtitle_area=(0, 100, 0, 100),
            language="klingon",
        )


def test_write_settings_ini_renders_keys(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The vendored engine reads ``Language`` and ``Mode`` from this file."""

    target = tmp_path / "settings.ini"
    monkeypatch.setattr(svc, "SETTINGS_INI_PATH", target)
    svc._write_settings_ini(language="vi", mode="fast")

    content = target.read_text(encoding="utf-8")
    assert "[DEFAULT]" in content
    assert "Language = vi" in content
    assert "Mode = fast" in content
