# opencut-pyside Roadmap — Becoming a CapCut-class desktop editor

This document is the strategic plan that complements the code-level fixes
landed in the initial review PR. It translates the CapCut feature-set into
concrete, sequenced milestones that are achievable on top of this repo's
existing clean architecture (domain → services → controllers → UI).

> The numbered milestones are ordered by **dependency** — each one makes
> the next one easier. Individual features inside a milestone can usually
> be parallelized.

---

## Snapshot of the current state (post-review PR)

What already works end-to-end:

- 4-panel editor shell (media · preview · inspector · timeline).
- Timeline scene with ruler, tracks, clips, zoom, snapping guides.
- Drag-to-move, drag-to-trim, split-at-cursor, delete — all undoable.
- Command-pattern manager (`app.domain.commands`) driving every edit.
- Preview frames via threaded FFmpeg.
- Multi-clip audio via `QMediaPlayer`.
- Project save / load + autosave recovery.
- Media import with **duration probe** (new in this PR).
- Multi-track MP4 export with filter_complex graph, on a worker thread.

Known rough edges (most addressed in this PR):

- FFmpeg path was Windows-only — fixed, now cross-platform.
- No `README`, `pyproject.toml`, `requirements.txt`, `.gitignore`,
  `.gitattributes` — all added in this PR.
- Mixed CRLF / LF and tab / space inconsistencies — normalized in this PR.
- `infrastructure/ffprobe_gateway.py` was an empty placeholder — now
  implemented and wired into `MediaService` so imported media carry real
  duration metadata.
- Timeline ruler did not respond to clicks — now click-to-seek and
  drag-to-scrub are supported, along with Space / ←→ / Home shortcuts.
- No tests — a pytest harness (`tests/`) now covers the demo project
  build, Qt startup, the command manager, snap engine, and media probe.

Everything below builds on top of that cleaned-up baseline.

---

## Milestone 0 — Foundations (1–2 weeks)

**Goal:** make the code easy to iterate on and shippable on Windows / macOS
/ Linux.

- [x] `README.md`, `ROADMAP.md`, `pyproject.toml`, `requirements.txt`.
- [x] Cross-platform FFmpeg / FFprobe binary resolution.
- [x] `FFprobeGateway` + duration probing during media import.
- [x] Timeline ruler click-to-seek and keyboard shortcuts.
- [x] Initial pytest smoke + unit tests.
- [ ] GitHub Actions CI: `ruff check`, `pytest` on
      `{ubuntu-latest, windows-latest, macos-latest}` × Python 3.11 / 3.12.
- [ ] **PyInstaller / Briefcase bundling** with FFmpeg/FFprobe shipped in
      `./bin/` — produces a `.msi`, `.dmg`, `.AppImage`.
- [x] Crash reporter: write a rotating log to
      `~/.opencut-pyside/logs/` and show an "Open log folder" menu entry.
- [x] Replace `print(...)` debugging left in utilities with `logging`.
- [x] Settings store at `~/.opencut-pyside/settings.json`
      (last export preset, last-opened project, recent files).

---

## Milestone 1 — Media pipeline hardening (3–4 weeks)

**Goal:** preview and edit real footage comfortably.

- [ ] **PyAV-based `VideoDecoder`** (replace per-frame FFmpeg shell-outs).
      Cache a rolling window of decoded RGB frames around the playhead so
      scrubbing is buttery smooth.
- [ ] **Background thumbnail generation** for clips on the timeline
      (`ThumbnailService` — the placeholder already exists). Render a
      filmstrip across each video clip, cached on disk under
      `~/.opencut-pyside/cache/thumbnails/<media_id>/<time>.webp`.
- [ ] **Audio waveform rendering** on audio/video clips (downsampled PCM
      via `ffmpeg -f s16le` or PyAV → cached).
- [ ] **Proxy / optimized-media workflow**: offer to transcode imported
      4K / HEVC media to 720p H.264 proxies on import. Swap back to the
      original source at export time.
- [ ] **True media duration & FPS** already probed with `FFprobeGateway`;
      next step is **video dimensions** and **audio sample-rate / channel
      count** so the `Project` can auto-configure from the first import.
- [ ] Validate dropped media against project FPS / resolution and warn on
      mismatch.

---

## Milestone 2 — Playback engine (2–3 weeks)

**Goal:** frame-accurate preview that plays like CapCut.

- [ ] Replace the single-frame FFmpeg extractor with a **continuous video
      thread** that reads the active top-most clip's frames and posts them
      to the preview at the project FPS.
- [ ] **Audio-video sync:** route audio through a single `QAudioSink` fed
      with decoded PCM so clips line up sample-perfectly with the video.
- [ ] **Loop region** (mark In / Out, press `L` to toggle loop playback).
- [ ] **Playback rate** control (0.25× / 0.5× / 1× / 2× / 4×) — drives the
      video thread's scheduling and the audio pitch/speed filter.
- [ ] **J / K / L** keyboard shuttle controls.
- [ ] Reuse the video thread for the exporter to render a preview of the
      currently visible frame at any moment (used in the Inspector to
      show a still of the selected clip).

---

## Milestone 3 — Timeline parity with CapCut (4–6 weeks)

**Goal:** feel at home for CapCut users.

- [ ] **Ripple / roll / slip / slide** trims (currently only basic L/R
      trims). Ripple mode should push downstream clips on the same track.
- [ ] **Magnetic timeline**: optional mode where clips snap to neighbours
      without overlap (same track) and the gap is closed automatically.
- [ ] **Lock / mute / solo** per track (domain flags already exist,
      wire them into UI and playback).
- [ ] **Track reordering** (drag up/down) and **dynamic track creation**
      (drop a clip below the last track to create a new one).
- [ ] **Selection model** upgrade to multi-select (Shift-click, marquee
      select), group / ungroup, and box-copy/paste.
- [ ] **Clipboard**: Cmd/Ctrl+C / Ctrl+V / Ctrl+X for clips across
      projects.
- [ ] **Marker track** (`domain.markers` already has the skeleton) with
      timeline labels and keyboard shortcut `M`.
- [ ] **Timecode display** (HH:MM:SS:FF) in the playback toolbar and
      ruler based on project FPS — reuse `utils/timecode.py` (currently a
      stub).
- [ ] **Range In/Out** for export — only render between the marks.

---

## Milestone 4 — Effects & transitions engine (6–8 weeks)

**Goal:** creative editing, not just cut/paste.

- [ ] **Transitions** between two neighbouring video clips on the same
      track: fade, crossfade, slide, whip-pan, zoom. Implement as a new
      `Transition` domain object referenced by the outgoing & incoming
      clips. Export-time: insert the right `xfade` / `acrossfade` filter.
- [ ] **Video effects stack per clip**: brightness/contrast, saturation,
      LUT, color wheels, Gaussian blur, vignette, chroma-key (green
      screen), speed curves.
- [ ] **Keyframe system**: generalize `domain.keyframe` (currently a
      stub) so every numeric property on a clip (opacity, scale, rotation,
      position, volume, ...) can animate over time. UI: inline
      keyframe diamonds on the clip strip + a "Curves" editor.
- [ ] **Speed ramps** (variable playback speed over time).
- [ ] **Animation presets** ("In", "Out", "Combo" like CapCut) — a
      bundle of keyframes applied with one click.

---

## Milestone 5 — Text, stickers & overlays (3–4 weeks)

**Goal:** social-video ready overlays.

- [ ] **Rich text clips**: font family/size/weight, color, stroke,
      drop-shadow, background box, alignment, per-letter animation.
      Render via `QTextDocument` → `QImage` → overlay.
- [ ] **Text templates** (CapCut-style "animated text" presets).
- [ ] **Sticker / PNG overlay** clips with transform handles in the
      preview canvas (drag to reposition, corner handles to scale/rotate).
- [ ] **Auto-captions** (Whisper via `faster-whisper` by default, fallback
      to cloud providers). Already a `caption_service.py` placeholder.
- [ ] **Caption styling** (word-by-word highlight like TikTok / CapCut).
- [ ] **Subtitle import/export** (`.srt`, `.vtt`).

---

## Milestone 6 — Audio features (3–4 weeks)

**Goal:** respectable mixer.

- [ ] **Per-clip envelopes** for volume & pan (keyframed).
- [ ] **Mute / solo** per track and per-clip.
- [ ] **Audio effects**: EQ, compressor, de-noise (rnnoise), reverb, pitch
      shift. Use FFmpeg audio filters at export time and live preview
      through `QAudioEffects` where possible.
- [ ] **Beat detection** → marker generation (madmom/aubio) so users can
      snap clips to the beat, CapCut-style.
- [ ] **Auto-ducking**: voice-over track ducks music track by N dB.

---

## Milestone 7 — Export pipeline (2–3 weeks)

**Goal:** robust, flexible, fast export.

- [ ] **Export presets** (YouTube 1080p, TikTok 1080×1920, Reels,
      ProRes 422, H.265 10-bit, WAV-only, MP3-only).
- [ ] **GPU acceleration** (`h264_nvenc`, `h264_qsv`, `h264_videotoolbox`,
      `hevc_vaapi`) detected at runtime with a safe `libx264` fallback.
- [ ] **Two-pass encoding** toggle for size-constrained targets.
- [ ] **Export queue** — enqueue multiple render jobs, each with its own
      progress and cancel button.
- [ ] **Frame-accurate export range** (uses the In/Out marks from
      Milestone 3).
- [ ] **Lossless intermediate** export (CFR ProRes / DNxHR) for round-
      tripping to external grading tools.

---

## Milestone 8 — Cloud & collaboration (stretch)

**Goal:** team workflows.

- [ ] Project format v2: **content-addressable assets** stored under
      `<project>/assets/<sha256>.ext` so projects are self-contained.
- [ ] **Project bundle** (`.ocpkg`) — zip of project JSON + assets for
      sharing.
- [ ] **Cloud sync** (user-configurable backend: S3-compatible, WebDAV,
      or a thin opencut-pyside server).
- [ ] **Live co-editing** (CRDT on the `Timeline` domain via `automerge`).
- [ ] **Versioning / snapshots** (every save creates an immutable hash
      referenced by the autosave service).

---

## Milestone 9 — Polish & mobile-scale UX (ongoing)

**Goal:** match CapCut's polish.

- [ ] **Dark / light theme** (CSS variables in `ui/shared/theme.py`).
- [ ] **High-DPI / retina** handling across preview and timeline
      (QPainter scale + oversampling).
- [ ] **Onboarding tour** & contextual tooltips.
- [ ] **Project templates** (9:16 reel, 16:9 YouTube, 1:1 square).
- [ ] **Undo history panel** (scrollable list of commands — command
      manager already keeps them all).
- [ ] **Panel docking / layouts** using `QDockWidget` (replace the fixed
      `QSplitter` shell).
- [ ] **Localization** (Vietnamese first — the project's primary audience
      — then English, then others via `lupdate` / Qt Linguist).

---

## Architecture guidelines (keep while scaling)

1. **Keep the domain pure.** `domain/*` must stay free of Qt imports so
   it's easily testable and re-usable (unit tests + CLI tooling).
2. **Controllers are the only Qt glue** — services and domain talk through
   interfaces, never through `QSignal` directly.
3. **All state mutations go through `CommandManager`** — this is what
   keeps undo/redo coherent as the editor grows.
4. **Persistent state lives in `Project` JSON** — no hidden state on
   controllers. This enables autosave, collaboration, and cloud sync.
5. **Infrastructure (`ffmpeg_gateway`, `ffprobe_gateway`, `file_repository`,
   `process_runner`, `cache_store`, `temp_manager`) abstracts the outside
   world** and is the only place `subprocess`, file I/O and caches live.
6. **Workers stay off the Qt thread.** `QThreadPool` + `QRunnable` for
   fire-and-forget jobs (export), dedicated `QThread` for long-lived
   work (video decoder). Emit results via `Signal`s back to the main
   thread.

---

## How to help

Good first issues:

- Port `utils/timecode.py` (currently empty) into a `Timecode` value
  object with `from_seconds` / `to_seconds` / `from_smpte` / `to_smpte`
  and wire it into the playback toolbar.
- Implement `services/thumbnail_service.py` using the new
  `FFmpegGateway.extract_frame_png` method.
- Replace remaining `print()` calls with the `logging` module and add a
  shared `logging_config.py` that writes to stdout + rotating file.
- Add a **File → Recent Projects** submenu backed by the settings store.
- Wire the already-existing `is_locked` / `is_muted` clip flags into the
  timeline painter (grey-out / strikethrough).

See `ROADMAP.md` sections above for larger initiatives.
