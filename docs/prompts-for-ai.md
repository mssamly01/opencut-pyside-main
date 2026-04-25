# Prompts-for-ai.md — Prompt Pack for Building the App

## 1. Mục đích

Tài liệu này chứa các prompt chuẩn để làm việc với AI khi xây dựng ứng dụng editor desktop theo kiến trúc đã định.

Mục tiêu:
- tránh prompt quá rộng,
- giữ kiến trúc ổn định,
- yêu cầu AI sửa đúng module,
- buộc AI mapping từ OpenCut sang Python/PySide6.

---

## 2. System rules cho mọi prompt

Luôn thêm phần này hoặc ý tương đương vào đầu prompt:

```text
Read docs/architecture.md and docs/feature-map.md first.
Reference reference/opencut only for UX inspiration.
Do not copy code from reference/opencut.
Implement only inside app/.
Do not modify anything in reference/opencut.
Keep UI, controller, domain, service, and infrastructure boundaries clean.
All clip mutations must go through controller and command system where applicable.
```

---

## 3. Output format chuẩn

Dùng format này gần như mọi lần:

```text
Output format:
1. Files to create/update
2. Implementation plan
3. Code
4. Explanation
5. Mapping from OpenCut concepts to Python modules
6. Manual test checklist
7. Edge cases
```

---

## 4. Prompt khởi tạo project

## Prompt 01 — Create project skeleton

```text
Read docs/architecture.md and docs/feature-map.md first.
Reference reference/opencut only for UX inspiration.
Do not copy code from reference/opencut.
Implement only inside app/.

Task:
Create the initial Python project skeleton for this desktop video editor.

Requirements:
- Use Python 3.11+
- Use PySide6
- Create the folder/module structure described in architecture.md
- Add placeholder files and minimal bootstrap wiring
- Create app/main.py
- Create a minimal app/bootstrap.py
- Create basic package init files where needed
- Do not implement business logic yet
- The app must launch successfully

Output format:
1. Files to create/update
2. Implementation plan
3. Code
4. Explanation
5. Manual test checklist
```

---

## 5. Prompt dựng main window

## Prompt 02 — Build main window shell

```text
Read docs/architecture.md and docs/feature-map.md first.
Reference reference/opencut only for UX inspiration.
Implement only inside app/.

Task:
Build the main editor shell UI using PySide6.

Requirements:
- Create a QMainWindow-based main window
- Layout must have 4 main regions:
  1. media panel on the left
  2. preview panel in the center
  3. inspector panel on the right
  4. timeline panel at the bottom
- Add a top toolbar with placeholder actions:
  new, open, save, undo, redo, play/pause, export
- Use splitters or dock-like layout
- Keep implementation clean and modular

Do not:
- Implement timeline logic
- Implement playback logic
- Put business logic inside widgets

Output format:
1. Files to create/update
2. Implementation plan
3. Code
4. Explanation
5. Mapping from OpenCut-inspired editor layout to PySide6 modules
6. Manual test checklist
```

---

## 6. Prompt dựng domain model

## Prompt 03 — Create domain models

```text
Read docs/architecture.md and docs/feature-map.md first.
Implement only inside app/.

Task:
Create the core domain models for the editor using Python dataclasses.

Requirements:
- Create:
  - Project
  - Timeline
  - Track
  - MediaAsset
  - BaseClip
  - VideoClip
  - AudioClip
  - ImageClip
  - TextClip
  - Keyframe
- Keep them pure Python
- Do not import PySide6 in domain
- Add helper methods where useful
- Add type hints
- Keep future extensibility in mind

Output format:
1. Files to create/update
2. Implementation plan
3. Code
4. Explanation
5. Example object relationships
6. Edge cases
```

---

## 7. Prompt tạo serialization

## Prompt 04 — Save/load project JSON

```text
Read docs/architecture.md and docs/feature-map.md first.
Implement only inside app/.

Task:
Implement project save/load support.

Requirements:
- Create ProjectService
- Serialize project domain models to JSON-friendly dict structure
- Deserialize JSON back into domain models
- Keep schema explicit and easy to debug
- Add version field
- Support media items and timeline tracks/clips
- Do not implement autosave yet

Output format:
1. Files to create/update
2. Implementation plan
3. Code
4. JSON schema explanation
5. Manual test checklist
6. Edge cases
```

---

## 8. Prompt dựng timeline UI MVP

## Prompt 05 — Build timeline widget MVP

```text
Read docs/architecture.md and docs/feature-map.md first.
Reference reference/opencut only for UX inspiration.
Implement only inside app/.

Task:
Build the MVP timeline UI using PySide6 QGraphicsView.

Requirements:
- Create:
  - TimelineView
  - TimelineScene
  - ClipItem
  - PlayheadItem
  - basic ruler area or ruler widget
- Timeline must render tracks and clip rectangles from domain data
- Add horizontal time-based layout
- Add scrolling support
- Add zoom foundation even if minimal
- Keep timeline logic separate from rendering logic

Do not:
- Implement trim/split yet
- Implement snapping yet
- Put domain mutations directly inside ClipItem

Output format:
1. Files to create/update
2. Implementation plan
3. Code
4. Explanation
5. Mapping from OpenCut-style timeline ideas to PySide6 implementation
6. Manual test checklist
```

---

## 9. Prompt interaction timeline

## Prompt 06 — Implement clip move interaction

```text
Read docs/architecture.md and docs/feature-map.md first.
Implement only inside app/.

Task:
Implement clip move interaction on the timeline.

Requirements:
- Add TimelineController
- Add drag behavior for moving clips horizontally on timeline
- Convert drag distance to timeline time
- Update clip positions through controller
- Do not mutate domain directly from UI items
- Emit proper update signals so timeline rerenders
- Keep code ready for future snapping support

Output format:
1. Files to create/update
2. Implementation plan
3. Code
4. Explanation
5. Manual test checklist
6. Edge cases
```

---

## 10. Prompt command system

## Prompt 07 — Add command system with undo/redo

```text
Read docs/architecture.md and docs/feature-map.md first.
Implement only inside app/.

Task:
Implement a command system for editor actions.

Requirements:
- Create BaseCommand
- Create CommandManager
- Add MoveClipCommand
- Integrate undo/redo support
- Keep command interface reusable for trim/split/delete/property update later
- Do not wire every future command yet, just build the foundation well

Output format:
1. Files to create/update
2. Implementation plan
3. Code
4. Explanation
5. Manual test checklist
6. Future extension notes
```

---

## 11. Prompt trim và split

## Prompt 08 — Implement trim and split clip

```text
Read docs/architecture.md and docs/feature-map.md first.
Implement only inside app/.

Task:
Implement trim and split operations for timeline clips.

Requirements:
- Add trim-left and trim-right support
- Add split-at-time support
- Use command objects for mutations
- Keep clip timing math safe
- Prevent invalid negative durations
- Update timeline rendering after operations

Output format:
1. Files to create/update
2. Implementation plan
3. Code
4. Timing math explanation
5. Manual test checklist
6. Edge cases
```

---

## 12. Prompt media import

## Prompt 09 — Implement media import and library

```text
Read docs/architecture.md and docs/feature-map.md first.
Implement only inside app/.

Task:
Implement media import and the media library panel.

Requirements:
- Add MediaService
- Add FFprobe-based metadata extraction abstraction
- Add MediaAsset creation
- Show imported assets in the media panel
- Include basic thumbnail placeholder support
- Make media items draggable to timeline
- Support video, audio, and image files

Do not:
- Implement full thumbnail generation pipeline if too large
- Block UI while scanning many files

Output format:
1. Files to create/update
2. Implementation plan
3. Code
4. Explanation
5. Manual test checklist
6. Edge cases
```

---

## 13. Prompt playback và preview

## Prompt 10 — Implement preview playback foundation

```text
Read docs/architecture.md and docs/feature-map.md first.
Implement only inside app/.

Task:
Implement the preview playback foundation.

Requirements:
- Add PlaybackController
- Add PreviewWidget
- Support play, pause, stop, and seek
- Sync current playback time with timeline playhead
- Show the active visual state at the current time
- Keep architecture ready for future text/image overlays
- Avoid overengineering realtime compositing at this step

Output format:
1. Files to create/update
2. Implementation plan
3. Code
4. Explanation
5. Manual test checklist
6. Edge cases
```

---

## 14. Prompt text overlay

## Prompt 11 — Implement text clip and text inspector

```text
Read docs/architecture.md and docs/feature-map.md first.
Implement only inside app/.

Task:
Implement text overlays as timeline clips.

Requirements:
- Add TextClip support if not already present
- Allow creating a new text clip
- Add text inspector UI
- Support editing:
  - content
  - font size
  - text color
- Reflect changes in preview
- Reflect text clip duration in timeline
- Use controller + command flow for property changes

Output format:
1. Files to create/update
2. Implementation plan
3. Code
4. Explanation
5. Manual test checklist
6. Edge cases
```

---

## 15. Prompt export

## Prompt 12 — Implement export pipeline MVP

```text
Read docs/architecture.md and docs/feature-map.md first.
Implement only inside app/.

Task:
Implement the MVP export pipeline.

Requirements:
- Add ExportService
- Add FFmpegGateway
- Build a simple export flow to mp4
- Use project canvas settings
- Support at least:
  - timeline video
  - timeline ordering
  - text overlay if feasible in MVP
- Run export work off the UI thread
- Provide progress callbacks/signals
- Handle failures cleanly

Output format:
1. Files to create/update
2. Implementation plan
3. Code
4. FFmpeg/export explanation
5. Manual test checklist
6. Edge cases
```

---

## 16. Prompt V2 features

## Prompt 13 — Implement multi-select

```text
Read docs/architecture.md and docs/feature-map.md first.
Implement only inside app/.

Task:
Implement timeline multi-selection.

Requirements:
- Add SelectionController
- Support:
  - single select
  - ctrl/cmd multi-select
  - optional drag rectangle selection
- Keep selection state outside widgets where practical
- Prepare for future grouped move behavior

Output format:
1. Files to create/update
2. Implementation plan
3. Code
4. Explanation
5. Manual test checklist
6. Edge cases
```

## Prompt 14 — Implement snapping

```text
Read docs/architecture.md and docs/feature-map.md first.
Implement only inside app/.

Task:
Implement timeline snapping.

Requirements:
- Add SnapEngine
- Snap to:
  - playhead
  - clip boundaries
  - markers if available
- Keep snapping tolerance configurable
- Show clear architecture boundaries
- Keep UI feedback extensible

Output format:
1. Files to create/update
2. Implementation plan
3. Code
4. Explanation
5. Manual test checklist
6. Edge cases
```

## Prompt 15 — Import captions from SRT/VTT

```text
Read docs/architecture.md and docs/feature-map.md first.
Implement only inside app/.

Task:
Implement caption import from SRT/VTT into text clips.

Requirements:
- Add CaptionService
- Parse SRT and/or VTT
- Convert caption segments into text clips on a subtitle/text track
- Add a simple import action in the UI
- Keep style defaults simple for now

Output format:
1. Files to create/update
2. Implementation plan
3. Code
4. Explanation
5. Manual test checklist
6. Edge cases
```

---

## 17. Prompt refactor khi code bắt đầu rối

## Prompt 16 — Refactor without changing behavior

```text
Read docs/architecture.md and docs/feature-map.md first.
Implement only inside app/.

Task:
Refactor the current implementation without changing user-visible behavior.

Requirements:
- Improve separation between UI, controller, domain, service, and infrastructure
- Remove duplicated logic
- Keep public behavior stable
- Explain what was moved and why
- Do not add unrelated new features

Output format:
1. Files to create/update
2. Refactor plan
3. Code
4. Explanation of structural improvements
5. Manual regression checklist
```

---

## 18. Prompt debug

## Prompt 17 — Debug a bug safely

```text
Read docs/architecture.md and docs/feature-map.md first.
Implement only inside app/.

Task:
Investigate and fix the following bug:

[describe bug here]

Requirements:
- First explain the likely root cause
- Then propose a minimal safe fix
- Keep architecture boundaries intact
- Do not rewrite unrelated modules
- Add a short regression checklist

Output format:
1. Suspected root cause
2. Files to update
3. Code
4. Explanation
5. Regression checklist
```

---

## 19. Prompt review code

## Prompt 18 — Review current implementation

```text
Read docs/architecture.md and docs/feature-map.md first.

Task:
Review the current implementation in app/ and identify architecture issues.

Requirements:
- Focus on:
  - UI/business logic leakage
  - direct domain mutation from widgets
  - missing command pattern usage
  - duplicated logic
  - likely scaling issues
- Do not rewrite code yet
- Provide a prioritized list of improvements

Output format:
1. Summary
2. High-priority issues
3. Medium-priority issues
4. Recommended refactor order
5. Quick wins
```

---

## 20. Prompt rule ngắn để dùng hàng ngày

Khi làm việc nhanh, bạn có thể dùng bản ngắn:

```text
Read docs/architecture.md and docs/feature-map.md.
Reference reference/opencut for UX only.
Implement only inside app/.
Do not copy code from reference/opencut.
Keep boundaries clean.
Now implement: [feature]
```

---

## 21. Quy tắc cuối cùng

Nếu AI bắt đầu:
- viết business logic trong widget,
- sửa trực tiếp domain từ UI item,
- tạo file lung tung ngoài kiến trúc,
- bê ý tưởng web stack sang Python một cách máy móc,

hãy dừng và dùng prompt refactor hoặc review ở trên.

Tài liệu này không chỉ để “ra lệnh cho AI”, mà để giữ cho dự án tăng trưởng có kiểm soát.
