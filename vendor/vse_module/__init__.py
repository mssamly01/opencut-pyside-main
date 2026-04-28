"""Video Subtitle Extractor (VSE) backend, vendored from
https://github.com/mssamly01/Extractor_doda (modules/extractor/VSE_MODULE/).

Patches applied (kept minimal to ease re-syncing):
  - tools/subtitle_ocr.py: lazy-load the CJK debug font so the package
    can be imported without bundling the 17 MB .otf binary.
  - backend/config.py: model directory may be overridden via the
    ``OPENCUT_VSE_MODEL_DIR`` environment variable; the legacy
    "illegal path" while-loop is downgraded to a single warning.

Models are NOT vendored; the user must point opencut at their own copy
via the in-app "Trích xuất phụ đề" → model directory picker. See
``app/services/subtitle_extraction_service.py`` for the integration
layer.
"""
