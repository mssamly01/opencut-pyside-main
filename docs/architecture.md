# Architecture.md — OpenCut-inspired Desktop Editor (Python + PySide6)

## 1. Mục tiêu kiến trúc

Tài liệu này định nghĩa kiến trúc chuẩn cho ứng dụng desktop lấy cảm hứng từ OpenCut, được xây bằng:

- Python 3.11+
- PySide6 cho UI desktop
- FFmpeg cho media processing
- JSON cho project persistence

Mục tiêu của kiến trúc:

- dễ mở rộng bằng AI-assisted coding,
- tách rõ UI và business logic,
- tránh nhồi toàn bộ logic vào widget,
- hỗ trợ timeline editor, preview, export, captions, keyframes theo lộ trình tăng dần.

---

## 2. Nguyên tắc kiến trúc

### 2.1. UI không phải là business logic
Widget chỉ nên:
- render dữ liệu,
- nhận input,
- phát event,
- gọi controller.

Widget không nên:
- quyết định logic timeline,
- sửa model trực tiếp,
- giữ state lõi của editor.

### 2.2. Domain phải thuần Python
Domain models không được phụ thuộc vào:
- PySide6,
- QWidget,
- signal/slot,
- FFmpeg process trực tiếp.

Điều này giúp:
- test dễ,
- refactor dễ,
- AI code ổn định hơn.

### 2.3. Services xử lý nghiệp vụ
Service là nơi chứa logic như:
- import media,
- load metadata,
- build export pipeline,
- autosave,
- caption parsing.

### 2.4. Infrastructure bọc hệ thống bên ngoài
Infrastructure là lớp tương tác với:
- FFmpeg,
- filesystem,
- cache,
- temp files,
- subprocess.

### 2.5. Controller là cầu nối giữa UI và domain
Controller nhận event từ UI, gọi command/service/model, rồi phát tín hiệu cập nhật lại UI.

---

## 3. Sơ đồ kiến trúc tổng thể

```text
+-----------------------+
|      UI (PySide6)     |
|  MainWindow, Panels   |
|  Timeline, Preview    |
+-----------+-----------+
            |
            v
+-----------------------+
|   Controllers Layer   |
| timeline / playback   |
| selection / project   |
+-----------+-----------+
            |
            v
+-----------------------+
|    Domain Models      |
| project / track /     |
| clip / keyframe       |
+-----------+-----------+
            |
            v
+-----------------------+
|      Services         |
| media / export /      |
| project / captions    |
+-----------+-----------+
            |
            v
+-----------------------+
|   Infrastructure      |
| ffmpeg / file io /    |
| cache / subprocess    |
+-----------------------+
```

---

## 4. Cấu trúc thư mục chuẩn

```text
your_app/
├─ app/
│  ├─ main.py
│  ├─ bootstrap.py
│  │
│  ├─ ui/
│  │  ├─ main_window.py
│  │  ├─ app_shell.py
│  │  ├─ media_panel/
│  │  │  ├─ media_panel.py
│  │  │  └─ media_item_widget.py
│  │  ├─ preview/
│  │  │  ├─ preview_widget.py
│  │  │  ├─ canvas_overlay.py
│  │  │  └─ playback_toolbar.py
│  │  ├─ timeline/
│  │  │  ├─ timeline_view.py
│  │  │  ├─ timeline_scene.py
│  │  │  ├─ clip_item.py
│  │  │  ├─ playhead_item.py
│  │  │  ├─ ruler_widget.py
│  │  │  └─ selection_rect.py
│  │  ├─ inspector/
│  │  │  ├─ inspector_panel.py
│  │  │  ├─ video_inspector.py
│  │  │  ├─ text_inspector.py
│  │  │  ├─ image_inspector.py
│  │  │  └─ project_inspector.py
│  │  └─ shared/
│  │     ├─ theme.py
│  │     ├─ icons.py
│  │     └─ dialogs.py
│  │
│  ├─ controllers/
│  │  ├─ app_controller.py
│  │  ├─ project_controller.py
│  │  ├─ timeline_controller.py
│  │  ├─ playback_controller.py
│  │  ├─ selection_controller.py
│  │  ├─ inspector_controller.py
│  │  └─ export_controller.py
│  │
│  ├─ domain/
│  │  ├─ project.py
│  │  ├─ timeline.py
│  │  ├─ track.py
│  │  ├─ clips/
│  │  │  ├─ base_clip.py
│  │  │  ├─ video_clip.py
│  │  │  ├─ audio_clip.py
│  │  │  ├─ image_clip.py
│  │  │  └─ text_clip.py
│  │  ├─ keyframe.py
│  │  ├─ selection.py
│  │  ├─ markers.py
│  │  └─ commands/
│  │     ├─ base_command.py
│  │     ├─ move_clip.py
│  │     ├─ trim_clip.py
│  │     ├─ split_clip.py
│  │     ├─ delete_clip.py
│  │     └─ update_property.py
│  │
│  ├─ services/
│  │  ├─ project_service.py
│  │  ├─ media_service.py
│  │  ├─ playback_service.py
│  │  ├─ export_service.py
│  │  ├─ caption_service.py
│  │  ├─ thumbnail_service.py
│  │  └─ autosave_service.py
│  │
│  ├─ infrastructure/
│  │  ├─ ffmpeg_gateway.py
│  │  ├─ ffprobe_gateway.py
│  │  ├─ file_repository.py
│  │  ├─ temp_manager.py
│  │  ├─ cache_store.py
│  │  └─ process_runner.py
│  │
│  ├─ dto/
│  │  ├─ project_dto.py
│  │  ├─ media_dto.py
│  │  └─ export_dto.py
│  │
│  ├─ utils/
│  │  ├─ timecode.py
│  │  ├─ math_utils.py
│  │  └─ id_generator.py
│  │
│  └─ tests/
│     ├─ domain/
│     ├─ services/
│     └─ integration/
│
├─ docs/
│  ├─ architecture.md
│  ├─ feature-map.md
│  ├─ product-spec.md
│  └─ prompts-for-ai.md
│
└─ reference/
   └─ opencut/
```

---

## 5. Lớp domain

## 5.1. Project
`Project` là aggregate root.

Trách nhiệm:
- lưu metadata project,
- canvas settings,
- media registry,
- tracks,
- markers,
- version format.

Ví dụ trường dữ liệu:

```python
@dataclass
class Project:
    project_id: str
    name: str
    width: int
    height: int
    fps: float
    sample_rate: int
    media_items: list[MediaAsset]
    timeline: Timeline
    markers: list[Marker]
    version: str = "0.1.0"
```

## 5.2. Timeline
`Timeline` chứa danh sách track và global duration.

Trách nhiệm:
- add/remove track,
- tra cứu clip theo id,
- tính duration tổng,
- validate overlap nếu cần.

## 5.3. Track
Một track đại diện cho:
- video track,
- audio track,
- overlay track,
- text track.

Track chịu trách nhiệm:
- sắp clip theo timeline_start,
- phát hiện overlap,
- insert clip vào đúng vị trí.

## 5.4. Clip hierarchy
Dùng inheritance hoặc tagged dataclass.

Base fields:
- id
- name
- track_id
- media_id
- timeline_start
- source_start
- source_end
- duration
- opacity
- transform
- is_locked
- is_muted

Clip types:
- `VideoClip`
- `AudioClip`
- `ImageClip`
- `TextClip`

## 5.5. Keyframe
Mỗi keyframe gồm:
- time
- property_name
- value
- interpolation

Ví dụ:
- position_x
- position_y
- scale
- rotation
- opacity

---

## 6. Command system

Đây là phần bắt buộc nếu muốn undo/redo.

### 6.1. Giao diện chuẩn

```python
class BaseCommand(ABC):
    @abstractmethod
    def execute(self) -> None: ...

    @abstractmethod
    def undo(self) -> None: ...
```

### 6.2. Command cần có ở MVP
- `AddClipCommand`
- `MoveClipCommand`
- `TrimClipCommand`
- `SplitClipCommand`
- `DeleteClipCommand`
- `UpdatePropertyCommand`

### 6.3. CommandManager
Nhiệm vụ:
- push command,
- undo,
- redo,
- clear stack khi mở project mới.

---

## 7. Controller layer

Controller nên là `QObject` để dùng signal/slot.

## 7.1. AppController
Điều phối toàn app:
- create/open/save project
- kết nối controller con
- notify dirty state

## 7.2. ProjectController
Phụ trách:
- khởi tạo project mới,
- load/save,
- autosave trigger,
- relink media.

## 7.3. TimelineController
Phụ trách:
- add clip vào track,
- move/trim/split,
- snap,
- zoom timeline,
- playhead sync.

Timeline UI không tự xử lý logic này.

## 7.4. PlaybackController
Phụ trách:
- play/pause/stop
- seek
- current time
- preview refresh cadence

## 7.5. SelectionController
Phụ trách:
- single select
- multi-select
- clear selection
- selection changed events

## 7.6. InspectorController
Phụ trách:
- ánh xạ selection -> inspector widget đúng loại
- apply property changes thành command

## 7.7. ExportController
Phụ trách:
- collect export settings
- gọi export service
- update progress
- cancel export

---

## 8. Services layer

## 8.1. ProjectService
- serialize project -> dict/json
- deserialize json -> project
- validate version
- migration format nếu cần

## 8.2. MediaService
- import file
- đọc metadata qua ffprobe
- phân loại file video/audio/image
- tạo MediaAsset

## 8.3. ThumbnailService
- generate thumbnails
- cache theo hash/path/time
- load thumbnail bất đồng bộ nếu cần

## 8.4. PlaybackService
- ánh xạ current timeline time -> active clips
- resolve frame/overlay cần hiển thị
- tách khỏi widget playback

## 8.5. CaptionService
- parse SRT/VTT
- chuyển caption thành text clips
- group theo style template

## 8.6. ExportService
- build render plan từ timeline
- generate ffmpeg pipeline/commands
- chạy export trong worker thread
- báo tiến trình

## 8.7. AutosaveService
- định kỳ lưu snapshot project
- khôi phục autosave gần nhất nếu crash

---

## 9. Infrastructure layer

## 9.1. FFmpegGateway
Chỉ làm việc với lệnh ffmpeg:
- trim,
- concat,
- overlay,
- encode,
- extract frame.

Không nên chứa business logic timeline.

## 9.2. FFprobeGateway
- duration
- fps
- resolution
- codec
- audio stream metadata

## 9.3. FileRepository
- save/load json
- quản lý project folder
- đường dẫn asset tương đối/tuyệt đối

## 9.4. CacheStore
- thumbnail cache
- waveform cache
- preview frame cache

## 9.5. ProcessRunner
Wrapper cho subprocess:
- start
- stdout/stderr
- cancel
- timeout
- error mapping

---

## 10. UI composition

## 10.1. Main window layout
Bố cục 4 vùng:

- trái: Media panel
- giữa: Preview
- phải: Inspector
- dưới: Timeline

Có toolbar trên cùng cho:
- open/save
- undo/redo
- zoom
- export

## 10.2. Media panel
- import file
- list asset
- search/filter
- drag vào timeline

## 10.3. Preview panel
- render preview
- play/pause
- seek
- zoom/pan canvas
- safe area guides về sau

## 10.4. Inspector panel
Dynamic panel:
- Video inspector
- Audio inspector
- Text inspector
- Image inspector
- Project inspector

## 10.5. Timeline panel
- ruler
- tracks
- clip items
- playhead
- selection box
- horizontal zoom
- snapping indicator về sau

---

## 11. Dòng dữ liệu chuẩn

## 11.1. Ví dụ: kéo clip trên timeline

```text
User drags clip
-> TimelineView emits drag event
-> TimelineController computes new time
-> SnapEngine adjusts target time
-> MoveClipCommand.execute()
-> Domain model updated
-> timeline_changed signal emitted
-> TimelineScene rerenders clip position
```

## 11.2. Ví dụ: đổi text trong inspector

```text
User edits text field
-> InspectorController receives value
-> UpdatePropertyCommand.execute()
-> TextClip.content updated
-> project_changed signal emitted
-> Preview refresh
-> Timeline repaint if needed
```

---

## 12. Persistence model

## 12.1. Project file format
Lưu ở JSON để dễ debug bằng AI.

Cấu trúc gợi ý:

```json
{
  "version": "0.1.0",
  "project_id": "proj_001",
  "name": "Demo",
  "canvas": {
    "width": 1920,
    "height": 1080,
    "fps": 30
  },
  "media_items": [
    {
      "id": "media_1",
      "path": "assets/video.mp4",
      "type": "video",
      "duration": 12.5
    }
  ],
  "timeline": {
    "tracks": [
      {
        "id": "track_1",
        "type": "video",
        "clips": []
      }
    ]
  }
}
```

## 12.2. Nguyên tắc persistence
- path nên tương đối nếu asset nằm trong project folder
- lưu version schema
- hỗ trợ restore missing media
- autosave tách riêng khỏi file chính

---

## 13. Concurrency model

Vì là desktop app, không nên block UI thread.

### Chạy ở worker thread:
- ffmpeg export
- thumbnail generation
- waveform analysis
- metadata scanning hàng loạt

### Chạy ở main thread:
- widget rendering
- selection state sync
- input events

Khuyến nghị:
- `QThread` hoặc `QRunnable`/`QThreadPool`

---

## 14. Error handling

### Quy tắc
- Service raise lỗi rõ nghĩa
- Controller bắt lỗi và chuyển thành UI message
- UI không tự parse exception hệ thống

Ví dụ:
- `MediaImportError`
- `ExportFailedError`
- `ProjectLoadError`

---

## 15. Logging strategy

Nên có logger theo module:
- app
- project
- media
- timeline
- export

Log tối thiểu:
- open/save project
- import media
- command execute/undo
- ffmpeg command
- export error

---

## 16. Test strategy

## 16.1. Unit tests
Ưu tiên test:
- timeline math
- clip move/trim/split
- project serialization
- caption parsing

## 16.2. Integration tests
- import media -> asset registry
- add clip -> save project -> reopen
- export pipeline build

## 16.3. UI tests
Làm sau:
- basic startup
- smoke test timeline widget

---

## 17. Quy ước để AI code an toàn

- Chỉ sửa trong `app/`
- Không import gì từ `reference/opencut/`
- Không viết business logic trực tiếp trong widget
- Mọi thay đổi state phải đi qua controller hoặc command
- Mọi property editor phải cập nhật model thông qua command system
- Mỗi feature mới phải khai báo file nào thuộc UI, controller, domain, service

---

## 18. Kiến trúc cho roadmap tương lai

Kiến trúc này hỗ trợ nâng cấp dần:

### Sau MVP
- snapping engine
- captions import
- image stickers
- text templates

### Giai đoạn tiếp
- keyframes
- graph editor
- waveform cache
- proxy preview
- background export jobs

### Giai đoạn nâng cao
- GPU preview
- plugin effects
- collaborative metadata
- Rust core về sau nếu cần

---

## 19. Quy tắc cuối cùng

Nếu phải chọn giữa:
- code nhanh nhưng dính chặt,
- code chậm hơn nhưng tách lớp rõ,

hãy chọn phương án thứ hai.

Trong dự án editor kiểu OpenCut, timeline và state sẽ phình rất nhanh. Kiến trúc sạch từ đầu giúp AI tiếp tục code được mà không phá app.
