# Current Task

Media pipeline hardening (P2)

## Current baseline
- MVP text workflow is complete: Add Text action, inspector editing, basic preview text, basic export text, save/load text attrs, undo/redo.
- Foundation polish is complete: centralized logging + rotating file + Open Logs action + local `pytest` setup.
- `ThumbnailService` baseline exists with disk+memory cache and timeline thumbnail rendering for video/image clips.
- Preview decode path now includes a rolling prefetch window cache in `PlaybackService` to reduce per-frame FFmpeg shell-outs during playback/scrub.

## Definition of done
- [x] Improve preview decode path to reduce FFmpeg shell-out per frame.
- [ ] Expand thumbnail generation toward filmstrip/background worker flow.
- [x] Keep existing import/preview/export workflows intact.
- [x] Update docs/plan to reflect active P2 progress.
- [x] `main.py --smoke-test` and `pytest` both pass after the current slice.
