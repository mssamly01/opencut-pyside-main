# opencut-pyside

A desktop video editor written in Python 3 + PySide6 (Qt 6), inspired by
[OpenCut](https://github.com/OpenCut-app/OpenCut) and CapCut. The long-term
goal is a fully featured, offline-first editor with timeline trimming,
multitrack audio, transitions, text / captions, keyframes, and MP4 export —
all driven by a cleanly layered codebase (domain / services / controllers /
UI).

This repo currently contains the **MVP skeleton**: a four-pane editor shell,
a command-pattern undo/redo timeline, drag-and-drop media import, autosave
recovery, and a threaded FFmpeg-based exporter. The
[`ROADMAP.md`](./ROADMAP.md) document describes how to evolve the project
toward CapCut-level functionality.

## Features already implemented

- **Four-panel Qt shell**: media library · preview · inspector · timeline.
- **Timeline view** with ruler, ticks, tracks, clips, selection, snapping
  guides, zoom in/out (Ctrl + mouse wheel), drag-to-move, drag-to-trim, and
  split at cursor.
- **Command pattern** (`app.domain.commands`) with a `CommandManager` that
  powers robust undo / redo for add / move / trim / split / delete / update
  operations.
- **Preview canvas** driven by `PlaybackController`, showing FFmpeg-decoded
  frames for the top-most video clip at the current playhead.
- **Audio playback** of multiple clips in parallel via `QMediaPlayer`, synced
  to the playhead.
- **Project persistence** (save / load JSON) and **autosave with recovery**
  prompt at startup.
- **Media import** via the media panel (file picker or drag-to-list) with
  drag-and-drop onto any timeline track.
- **Multi-track MP4 export** (H.264 / AAC, libx264 `veryfast`) via an
  `ExportService` that builds a filter_complex graph for overlays and audio
  mixing, with progress callbacks and a worker thread.
- **Inspector panels** for project settings, video clips, audio clips,
  image clips, and text clips — every edit goes through the command manager.
- **Cross-platform FFmpeg / FFprobe resolution**: bundled binaries in
  `./bin/` are preferred, and the app falls back to whatever is on `PATH`
  (works on Windows, macOS, and Linux).

## Project layout

The repository *is* the importable Python package `app`. When you run the
code you need the **parent directory** of this repo on `sys.path` (or a
symlink named `app`). The entry point takes care of this automatically when
launched as a script.

```
opencut-pyside/
├── main.py                 # `python main.py` entry point
├── bootstrap.py            # DI container: wires controllers + MainWindow
├── controllers/            # Qt QObject controllers (project, timeline, …)
├── domain/                 # pure-Python domain model + command pattern
│   ├── clips/              # VideoClip / AudioClip / ImageClip / TextClip
│   └── commands/           # BaseCommand, CommandManager, Add/Move/Trim/…
├── services/               # use-cases (export, autosave, playback, …)
├── infrastructure/         # thin adapters over subprocess ffmpeg / ffprobe
├── ui/                     # Qt widgets (app_shell, timeline, preview, …)
├── dto/                    # (de)serialization payloads
├── utils/                  # helpers (timecode, id_generator, …)
├── tests/                  # pytest smoke + unit tests
├── pyproject.toml
└── requirements.txt
```

## Requirements

- **Python 3.10+** (3.12 recommended).
- **PySide6 ≥ 6.6** (installed via `pip install -r requirements.txt`).
- **FFmpeg** and **FFprobe** binaries available either:
  - at `./bin/ffmpeg` (or `ffmpeg.exe` on Windows) and `./bin/ffprobe`, or
  - on the system `PATH`.
  The exporter and media-import duration probe degrade gracefully if they
  cannot be found, but preview frames and MP4 export require a real FFmpeg.

## Running the editor

```bash
# 1. Install Python dependencies.
pip install -r requirements.txt

# 2. Launch the editor (from the directory *containing* opencut-pyside).
python opencut-pyside/main.py
```

The repo ships with a runtime shim at the top of `main.py` that adjusts
`sys.path` so running it directly works from any working directory. To use
the packaged form instead:

```bash
cd <parent-of-opencut-pyside>
ln -s opencut-pyside app           # makes "import app" resolve to this repo
python -m app.main
```

### Smoke-test headless

CI and automated tests use the PySide `offscreen` Qt platform so no real
display is required:

```bash
QT_QPA_PLATFORM=offscreen python opencut-pyside/main.py --smoke-test
```

`--smoke-test` starts the application, shows the main window, and posts a
`QTimer.singleShot(0, quit)` — used for CI validation that startup works
end-to-end.

## Running the tests

```bash
pip install -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen python -m pytest tests/
```

The `tests/conftest.py` file creates a temporary symlink named `app`
pointing at the repo root so that `from app.xxx import ...` resolves
without manual path hacks.

## Keyboard & mouse cheatsheet

| Action                          | Shortcut / gesture                           |
| ------------------------------- | -------------------------------------------- |
| Import media                    | Toolbar → **Import Media**                   |
| Drag media onto timeline        | Drag from the media panel to any track row   |
| Move a clip                     | Left-click + drag inside the clip            |
| Trim a clip                     | Drag either edge of a clip                   |
| Split the selected clip         | Hover cursor, press **S**                    |
| Delete the selected clip        | Press **Delete**                             |
| Play / Pause                    | **Space**                                    |
| Scrub playhead                  | Click (and drag) on the timeline **ruler**   |
| Nudge playhead by 1 frame       | **←** / **→**                                |
| Nudge playhead by 1 second      | **Shift + ←** / **Shift + →**                |
| Jump to timeline start          | **Home**                                     |
| Zoom timeline                   | **Ctrl + mouse wheel**                       |
| Zoom buttons                    | Toolbar → **Zoom In / Zoom Out**             |
| Undo / Redo                     | Toolbar → **Undo / Redo**                    |

## Export

Use **File → Export** (or the export toolbar entry) to render the active
project to an MP4 file. Progress is reported through a non-blocking dialog
while the `ExportService` streams a `filter_complex` graph to FFmpeg on a
background thread.

## Contributing

- Keep line endings **LF only** (enforced via `.gitattributes`).
- Indent with **4 spaces** (no tabs).
- Run `ruff check .` and `QT_QPA_PLATFORM=offscreen pytest tests/` before
  opening a PR.
- See [`ROADMAP.md`](./ROADMAP.md) for the list of upcoming features that
  need owners.

## License

MIT. See [`LICENSE`](./LICENSE) if present, or file headers.
