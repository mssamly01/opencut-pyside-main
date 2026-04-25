# Packaging - OpenCut PySide

## Windows bundle (PyInstaller)

### Prerequisites
1. Python 3.12 available in `PATH`.
2. Download ffmpeg from https://www.gyan.dev/ffmpeg/builds/ and place `ffmpeg.exe` at `packaging/bin/ffmpeg.exe`.
3. Optional: add `packaging/icon.ico` for app icon.

### Build
```powershell
pwsh scripts/build_windows.ps1
```

Output path: `dist/OpenCut/OpenCut.exe` (one-folder bundle).

### Smoke test
Run `dist/OpenCut/OpenCut.exe` on a Windows machine without Python:
1. Create a new project.
2. Import a media file.
3. Save and reload project.
4. Export MP4 successfully.

### Release
Zip `dist/OpenCut/` and upload to release artifacts.

## Linux / macOS

Current recommended path is source run:
```bash
python -m pip install -r requirements.txt
python main.py
```
