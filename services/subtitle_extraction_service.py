"""Wrapper around the vendored Video Subtitle Extractor engine.

The real OCR engine lives in :mod:`app.vendor.vse_module.backend` and
pulls in heavy GPU-only dependencies (PaddlePaddle, PaddleOCR, OpenCV,
scikit-image, ...). To keep opencut importable on machines without
those extras, this module imports them lazily and reports a friendly
hint to the UI when something is missing.

Public surface (kept intentionally small for the first cut):

* :func:`is_available` -- probes whether extraction can run, returning
  a `(ok, hint)` tuple suitable for an error dialog.
* :func:`set_model_dir` / :func:`get_model_dir` -- paths to the user's
  copy of the V4 PaddleOCR models (the engine expects subdirectories
  ``V4/ch_det``, ``V4/ch_rec``, ...).
* :func:`extract_subtitles` -- run the engine on a video and return the
  resulting ``.srt`` file path.

The "Trích xuất phụ đề" UI in the captions panel calls these directly.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

VSE_MODULE_DIR = Path(__file__).resolve().parent.parent / "vendor" / "vse_module"
BACKEND_DIR = VSE_MODULE_DIR / "backend"
SETTINGS_INI_PATH = VSE_MODULE_DIR / "settings.ini"

MODEL_DIR_ENV = "OPENCUT_VSE_MODEL_DIR"

SUPPORTED_LANGUAGES: tuple[tuple[str, str], ...] = (
    ("vi", "Tiếng Việt"),
    ("en", "English"),
    ("ch", "简体中文"),
    ("chinese_cht", "繁體中文"),
    ("japan", "日本語"),
    ("korean", "한국어"),
)

SUPPORTED_MODES: tuple[tuple[str, str], ...] = (
    ("fast", "Fast (lightweight model)"),
    ("accurate", "Accurate (large model, GPU recommended)"),
    ("auto", "Auto (decide from GPU availability)"),
)


@dataclass(frozen=True)
class Availability:
    ok: bool
    hint: str


def _missing_dep(name: str) -> Availability:
    return Availability(
        ok=False,
        hint=(
            f"Thiếu dependency '{name}'. Hãy cài đầy đủ extras:\n"
            "  pip install \".[subtitle-extraction]\"\n"
            "(cần: paddlepaddle-gpu, paddleocr, opencv-python, pysrt, fsplit, "
            "wordsegment, Levenshtein, lmdb, pyclipper, shapely, scikit-image)"
        ),
    )


def is_available() -> Availability:
    """Check whether all engine deps + a usable model directory exist."""

    # Vendored backend imports `fsplit` và `wordsegment` ở top-level (config.py,
    # tools/reformat.py) nên phải probe luuôn -- thiếu một trong hai sẽ làm
    # _import_extractor() raise ImportError ngay khi reload, không hệ liên quan
    # đến paddle.
    for module_name in ("cv2", "paddle", "paddleocr", "pysrt", "fsplit", "wordsegment"):
        try:
            importlib.import_module(module_name)
        except ImportError:
            return _missing_dep(module_name)

    model_dir = get_model_dir()
    if not model_dir:
        return Availability(
            ok=False,
            hint=(
                "Chưa cấu hình thư mục models PaddleOCR.\n"
                "Sao chép thư mục 'modules/extractor/VSE_MODULE/backend/models' "
                "từ Extractor_doda vào một vị trí cố định, rồi chọn nó qua "
                "nút 'Chọn thư mục models'."
            ),
        )
    if not Path(model_dir).is_dir():
        return Availability(
            ok=False,
            hint=f"Thư mục models không tồn tại: {model_dir}",
        )
    if not (Path(model_dir) / "V4").is_dir():
        return Availability(
            ok=False,
            hint=(
                f"Thư mục '{model_dir}' không chứa subdir 'V4/'. "
                "Đường dẫn đúng phải là thư mục cha của 'V4/ch_det', 'V4/ch_rec', ..."
            ),
        )
    return Availability(ok=True, hint="")


def get_model_dir() -> str | None:
    value = os.environ.get(MODEL_DIR_ENV, "").strip()
    return value or None


def set_model_dir(path: str | None) -> None:
    """Set (or clear) the env var the vendored config.py reads at import time."""

    if path:
        os.environ[MODEL_DIR_ENV] = path
    else:
        os.environ.pop(MODEL_DIR_ENV, None)


def _write_settings_ini(language: str, mode: str) -> None:
    """Write the ini file the vendored engine reads at import time."""

    SETTINGS_INI_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_INI_PATH.write_text(
        "[DEFAULT]\n"
        "Interface = Tiếng Việt\n"
        f"Language = {language}\n"
        f"Mode = {mode}\n",
        encoding="utf-8",
    )


def _import_extractor():
    """Import (or reload) the vendored SubtitleExtractor with current env+ini."""

    from app.vendor.vse_module.backend import config as backend_config

    importlib.reload(backend_config)

    from app.vendor.vse_module.backend import main as backend_main

    importlib.reload(backend_main)
    return backend_main.SubtitleExtractor


def extract_subtitles(
    video_path: str,
    subtitle_area: tuple[int, int, int, int],
    language: str = "vi",
    mode: str = "fast",
    progress_callback: Callable[[float, str], None] | None = None,
) -> str:
    """Run the vendored extractor and return the resulting ``.srt`` path.

    ``subtitle_area`` is ``(ymin, ymax, xmin, xmax)`` in pixel coords of
    the source video, matching the engine's contract.

    ``progress_callback`` is currently best-effort: the engine writes to
    its own ``tqdm`` bar and we only emit coarse start/finish updates.
    A finer hook would require patching the engine's inner loop.
    """

    availability = is_available()
    if not availability.ok:
        raise RuntimeError(availability.hint)

    if not os.path.isfile(video_path):
        raise FileNotFoundError(video_path)

    if language not in {code for code, _ in SUPPORTED_LANGUAGES}:
        raise ValueError(f"Unsupported language: {language}")
    if mode not in {code for code, _ in SUPPORTED_MODES}:
        raise ValueError(f"Unsupported mode: {mode}")

    _write_settings_ini(language=language, mode=mode)

    if progress_callback is not None:
        progress_callback(0.0, "Khởi tạo engine OCR...")

    extractor_cls = _import_extractor()

    if progress_callback is not None:
        progress_callback(5.0, "Bắt đầu trích xuất...")

    extractor = extractor_cls(video_path, subtitle_area)
    extractor.run()

    srt_path = os.path.splitext(video_path)[0] + ".srt"
    if not os.path.isfile(srt_path):
        raise RuntimeError(
            "Trích xuất hoàn tất nhưng không thấy file .srt. "
            "Có thể vùng phụ đề bị rỗng hoặc model không nhận diện được ký tự."
        )

    if progress_callback is not None:
        progress_callback(100.0, "Hoàn tất.")

    return srt_path
