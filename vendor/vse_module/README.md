# Vendored: Video Subtitle Extractor (VSE) backend

Source: [`mssamly01/Extractor_doda`](https://github.com/mssamly01/Extractor_doda),
folder `modules/extractor/VSE_MODULE/`.

## What is included

Only the Python OCR engine + i18n strings + PaddleOCR config helpers.

Skipped intentionally:

- `models/` — the V4 PaddleOCR weights (~106 MB). The user provides
  these out-of-tree; opencut points the engine at them via the
  `OPENCUT_VSE_MODEL_DIR` env var (set automatically by the
  "Trích xuất phụ đề" dialog after the user picks a directory once).
- `subfinder/windows/` — Windows-only C++ binary not used by the
  Python extraction path.
- `tools/NotoSansCJK-Bold.otf` — 17 MB CJK font only used for
  optional debug overlays. The vendored
  `tools/subtitle_ocr.py` is patched to lazy-load the font and
  no-op the overlay if it is absent, so dropping the file does not
  affect extraction quality.

## Local patches (kept minimal)

1. `backend/config.py`
   - Reads `OPENCUT_VSE_MODEL_DIR` and overrides `DET_MODEL_BASE` /
     `REC_MODEL_BASE` when set.
   - Replaces the legacy `while not IS_LEGAL_PATH: time.sleep(3)` loop
     with a single warning so an opencut install path containing CJK
     or whitespace does not deadlock the engine.

2. `backend/tools/subtitle_ocr.py`
   - Lazy-loads `NotoSansCJK-Bold.otf` (returns the original image
     unmodified when the font is missing).

If you re-sync from upstream, re-apply these patches and update this
README with the upstream commit you synced from.

## Runtime requirements

- `paddlepaddle-gpu==3.3.1` (Windows or Linux + NVIDIA CUDA/cuDNN)
- `paddleocr`
- `opencv-python`, `pysrt`, `Levenshtein`, `pyclipper`, `shapely`,
  `scikit-image`

Install via:

```
pip install ".[subtitle-extraction]"
```

The opencut UI calls `app.services.subtitle_extraction_service.is_available`
before invoking the engine and displays a friendly install hint when a
dependency is missing.
