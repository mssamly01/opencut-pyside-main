# Feature-map.md — OpenCut → Python/PySide6 Translation Map

## 1. Mục đích tài liệu

Tài liệu này dùng để chuyển các ý tưởng sản phẩm và UX từ OpenCut sang thiết kế triển khai bằng Python + PySide6.

Nguyên tắc quan trọng:

- OpenCut là nguồn tham khảo về product flow và editor behaviors.
- Không sao chép nguyên code TypeScript/Rust.
- Chỉ học:
  - feature breakdown,
  - panel organization,
  - timeline interactions,
  - state boundaries,
  - rendering concepts.
- Sau đó ánh xạ chúng thành module Python.

---

## 2. Cách sử dụng tài liệu này

Với mỗi tính năng:
1. xác định OpenCut đang giải quyết bài toán UX nào,
2. xác định module Python nào sẽ phụ trách,
3. xác định mức độ ưu tiên:
   - MVP,
   - V2,
   - Advanced.

---

## 3. Feature map tổng quan

| OpenCut Feature Area | Python/PySide6 Equivalent | Priority |
|---|---|---|
| Media import / asset library | Media panel + MediaService + asset registry | MVP |
| Timeline editor | TimelineView + TimelineController + Timeline domain | MVP |
| Clip move / resize / split | Command system + timeline interactions | MVP |
| Preview player | Preview widget + PlaybackController | MVP |
| Text overlays | TextClip + Inspector + Preview overlay | MVP |
| Export | ExportService + FFmpegGateway | MVP |
| Multi-select | SelectionController + selection model | V2 |
| Snapping | SnapEngine + timeline feedback | V2 |
| Captions from transcript | CaptionService + text clip generation | V2 |
| Stickers / image overlays | ImageClip + asset panel + inspector | V2 |
| Canvas size presets | Project settings + project inspector | V2 |
| Preview zoom / pan | Preview widget transforms | V2 |
| Keyframes | Keyframe model + keyframe lane UI | Advanced |
| Graph editor | Curve editor + interpolation UI | Advanced |

---

## 4. Mapping theo khu vực sản phẩm

## 4.1. App shell / editor layout

### OpenCut idea
Một editor thường có:
- media/assets ở bên trái,
- preview ở giữa,
- inspector ở bên phải,
- timeline phía dưới.

### Python translation
Modules:
- `ui/main_window.py`
- `ui/media_panel/`
- `ui/preview/`
- `ui/inspector/`
- `ui/timeline/`

### Ghi chú
Đây là điểm nên học mạnh từ OpenCut vì layout ảnh hưởng trực tiếp trải nghiệm người dùng.

### Priority
MVP

---

## 4.2. Media import / asset library

### OpenCut idea
Người dùng import asset rồi kéo vào timeline.

### Python translation
Domain / data:
- `MediaAsset`
- media registry trong `Project`

Services:
- `MediaService`
- `ThumbnailService`

UI:
- `MediaPanel`
- `MediaItemWidget`

Infrastructure:
- `FFprobeGateway`

### Hành vi chính
- import nhiều file,
- detect loại file,
- đọc metadata,
- sinh thumbnail,
- drag asset vào timeline.

### Priority
MVP

---

## 4.3. Timeline editor

### OpenCut idea
Timeline là trung tâm của editor:
- track
- clip blocks
- playhead
- zoom
- selection
- snapping
- trim/split

### Python translation
UI:
- `TimelineView`
- `TimelineScene`
- `ClipItem`
- `PlayheadItem`
- `RulerWidget`

Domain:
- `Timeline`
- `Track`
- `BaseClip` + subclasses

Controller:
- `TimelineController`

Commands:
- `MoveClipCommand`
- `TrimClipCommand`
- `SplitClipCommand`

### Hành vi chính
- hiển thị clip theo trục thời gian,
- kéo clip,
- trim đầu/cuối,
- split tại playhead,
- scroll/zoom timeline,
- đồng bộ playhead.

### Priority
MVP

---

## 4.4. Multi-select clips

### OpenCut idea
Chọn nhiều clip, di chuyển cùng lúc, resize logic rõ ràng.

### Python translation
Domain:
- `SelectionState`

Controller:
- `SelectionController`

UI:
- multi-select handling trong `TimelineView`
- selection rectangle

### Hành vi chính
- single click
- ctrl/cmd click
- shift selection
- drag-select rectangle
- move nhóm clip đã chọn

### Priority
V2

---

## 4.5. Snapping

### OpenCut idea
Clip snap vào:
- đầu/cuối clip khác,
- playhead,
- markers,
- grid.

### Python translation
Service/domain helper:
- `SnapEngine`

Controller:
- `TimelineController`

UI:
- snap indicator trong timeline

### Hành vi chính
- tìm vị trí gần nhất trong tolerance,
- hút clip về mốc phù hợp,
- hiển thị guide line.

### Priority
V2

---

## 4.6. Preview player

### OpenCut idea
Preview hiển thị kết quả hiện tại theo playhead.

### Python translation
UI:
- `PreviewWidget`
- `CanvasOverlay`

Controller:
- `PlaybackController`

Service:
- `PlaybackService`

### Hành vi chính
- play/pause
- seek
- current frame render
- overlay text/image
- zoom/pan canvas về sau

### Priority
MVP

---

## 4.7. Canvas size / project settings

### OpenCut idea
Người dùng chọn canvas size và layout video xuất ra.

### Python translation
Domain:
- `Project.canvas_width`
- `Project.canvas_height`
- `Project.fps`

UI:
- `ProjectInspector`

Controller:
- `ProjectController`

### Hành vi chính
- đổi preset 16:9 / 9:16 / square,
- cập nhật preview bounds,
- export bám theo canvas.

### Priority
V2

---

## 4.8. Text overlays

### OpenCut idea
Thêm text, đổi style, kéo vị trí, chỉnh thời lượng.

### Python translation
Domain:
- `TextClip`

UI:
- `TextInspector`
- overlay editor trong preview

Controller:
- `InspectorController`
- `TimelineController`

### Hành vi chính
- add text clip,
- sửa content,
- font size,
- color,
- alignment,
- position trên canvas,
- duration trên timeline.

### Priority
MVP

---

## 4.9. Stickers / image overlays

### OpenCut idea
Thêm image/sticker layer trên canvas.

### Python translation
Domain:
- `ImageClip`

Services:
- `MediaService`

UI:
- media panel reuse
- image inspector

Preview:
- overlay render layer

### Hành vi chính
- import png/jpg,
- kéo vào overlay track,
- scale/rotate/move,
- thay opacity.

### Priority
V2

---

## 4.10. Captions / transcript import

### OpenCut idea
Import transcript để tạo subtitles/captions.

### Python translation
Service:
- `CaptionService`

Domain:
- `TextClip` danh sách theo segment

UI:
- import captions action
- caption preset styling panel về sau

### Hành vi chính
- import `.srt` / `.vtt`,
- parse từng segment,
- tạo nhiều text clips,
- style caption cơ bản.

### Priority
V2

---

## 4.11. Keyframes

### OpenCut idea
Animate properties theo thời gian:
- position
- scale
- opacity
- rotation

### Python translation
Domain:
- `Keyframe`
- `KeyframeTrack` hoặc keyframes gắn vào clip

UI:
- keyframe lane dưới clip hoặc trong inspector timeline mini

Controller:
- `InspectorController`
- `TimelineController`

### Hành vi chính
- add/remove keyframe,
- chỉnh giá trị theo thời gian,
- interpolate giữa các keyframe.

### Priority
Advanced

---

## 4.12. Graph editor

### OpenCut idea
Hiển thị curve của animation easing/interpolation.

### Python translation
UI:
- `GraphEditorWidget`

Domain:
- interpolation model

### Hành vi chính
- bezier/ease curves,
- chỉnh tangents,
- preview motion curve.

### Priority
Advanced

---

## 4.13. Undo / redo

### OpenCut idea
Mọi thao tác editor nên quay lui được.

### Python translation
Domain:
- `BaseCommand`
- concrete commands

Controller:
- `CommandManager`
- `AppController`

### Hành vi chính
- execute
- undo
- redo
- grouping command về sau

### Priority
MVP gần cuối

---

## 4.14. Export pipeline

### OpenCut idea
Xuất video từ timeline hiện tại.

### Python translation
Service:
- `ExportService`

Infrastructure:
- `FFmpegGateway`
- `ProcessRunner`

Controller:
- `ExportController`

### Hành vi chính
- đọc timeline,
- tạo render plan,
- build command ffmpeg,
- xuất mp4,
- báo tiến trình.

### Priority
MVP

---

## 5. Mapping theo module Python

## 5.1. `app/domain/`
Đây là nơi nhận phần “editor state” từ OpenCut.

OpenCut concepts nên map vào đây:
- project state
- timeline state
- clip types
- keyframes
- markers
- selection

Không nên chứa:
- widget code
- subprocess code
- file dialog logic

---

## 5.2. `app/controllers/`
Đây là nơi nhận phần “interaction logic”.

Map từ OpenCut:
- timeline interaction
- playback behavior
- selection changes
- inspector apply changes
- project lifecycle

---

## 5.3. `app/services/`
Đây là nơi nhận phần “media operations”.

Map từ OpenCut:
- captions generation
- export preparation
- metadata reading
- playback resolution logic
- autosave

---

## 5.4. `app/ui/`
Đây là nơi nhận phần “editor shell”.

Map từ OpenCut:
- left asset panel
- center preview
- right inspector
- bottom timeline
- toolbar / shortcuts

---

## 5.5. `app/infrastructure/`
Đây là nơi nhận phần “external tools”.

Map từ OpenCut:
- rendering backend concept
- metadata probing
- file persistence
- cache/temp storage

---

## 6. Lộ trình ưu tiên feature

## 6.1. MVP
Bắt buộc hoàn thành trước:

1. project create/open/save
2. media import
3. timeline view
4. drag/move clip
5. trim clip
6. split clip
7. preview play/pause/seek
8. text overlay cơ bản
9. export mp4

## 6.2. V2
Làm sau khi MVP ổn:

1. multi-select
2. snapping
3. canvas presets
4. preview zoom/pan
5. image overlays
6. captions import
7. relink missing media
8. autosave

## 6.3. Advanced
Chỉ làm khi app đủ ổn định:

1. keyframes
2. graph editor
3. waveform audio
4. transitions
5. proxy preview
6. background render queue

---

## 7. Mapping theo user flow

## 7.1. Import asset flow
OpenCut-style intent:
- người dùng đưa media vào thư viện rồi kéo vào editor.

Python flow:
- `MediaPanel` -> `MediaService.import_files()` -> `Project.media_items` -> thumbnail list -> drag to timeline.

## 7.2. Edit clip flow
OpenCut-style intent:
- thao tác trực tiếp trên clip.

Python flow:
- `TimelineView` event -> `TimelineController` -> `Command` -> `Timeline domain` -> signal -> repaint.

## 7.3. Change properties flow
OpenCut-style intent:
- sửa thuộc tính clip trong inspector.

Python flow:
- `InspectorPanel` -> `InspectorController` -> `UpdatePropertyCommand` -> clip updated -> preview refresh.

## 7.4. Export flow
OpenCut-style intent:
- timeline hiện tại trở thành file video.

Python flow:
- `ExportDialog` -> `ExportController` -> `ExportService.build_plan()` -> `FFmpegGateway.run()`.

---

## 8. Những gì nên học từ OpenCut và những gì không nên học nguyên xi

## Nên học
- cách chia editor thành panel,
- feature priority,
- timeline-first workflow,
- overlay/text/caption workflow,
- định hướng keyframe/graph editor về lâu dài.

## Không nên bê nguyên
- stack web/Next.js,
- GPUI/Rust desktop code,
- state management của frontend web nếu không phù hợp Python,
- cấu trúc build tool của monorepo.

---

## 9. Quy tắc prompt cho AI khi dùng feature map này

Mẫu prompt:

```text
Read docs/architecture.md and docs/feature-map.md first.
Reference reference/opencut only for UX inspiration.
Implement only inside app/.
Do not copy code from reference/opencut.
Follow the module mapping in feature-map.md.
Use controller + domain + service boundaries from architecture.md.
```

Mẫu task tốt:

```text
Implement MVP timeline clip drag and resize.
Files should be added only under:
- app/ui/timeline/
- app/controllers/
- app/domain/
Use QGraphicsView for UI.
All clip mutations must go through TimelineController and command objects.
```

---

## 10. Quy tắc cuối cùng

OpenCut là bản đồ sản phẩm, không phải bộ mã nguồn để port.

Feature map này tồn tại để giúp AI luôn trả lời theo kiểu:
- “OpenCut làm gì?”
- “Python app của mình nên cài ở module nào?”
- “Mức độ ưu tiên là gì?”
- “Phần nào thuộc UI, controller, domain, service?”

Nếu mỗi lần code đều bám vào tài liệu này, dự án sẽ ít bị lệch kiến trúc hơn rất nhiều.
