# Product-spec.md — OpenCut-inspired Desktop Editor MVP

## 1. Mục tiêu sản phẩm

Xây dựng một ứng dụng chỉnh sửa video desktop lấy cảm hứng từ OpenCut, dành cho người dùng cần một editor gọn, hiện đại, dễ mở rộng, và phù hợp để phát triển bằng AI-assisted coding.

Ứng dụng được xây bằng:

- Python 3.11+
- PySide6 cho giao diện desktop
- FFmpeg cho xử lý media
- JSON cho project persistence

Mục tiêu của MVP không phải là clone toàn bộ OpenCut, mà là tạo ra một editor desktop có trải nghiệm cốt lõi tương đương về mặt workflow:

- import media,
- dựng timeline,
- chỉnh clip cơ bản,
- preview playback,
- chèn text,
- export ra video.

---

## 2. Phạm vi MVP

## 2.1. In scope

### Project management
- tạo project mới
- mở project
- lưu project
- autosave cơ bản

### Media
- import video
- import audio
- import image
- hiển thị media library
- drag media từ library vào timeline

### Timeline editing
- hiển thị nhiều track
- tạo clip block theo thời gian
- chọn clip
- kéo clip
- trim đầu clip
- trim cuối clip
- split clip tại playhead
- delete clip
- playhead sync
- zoom timeline cơ bản

### Preview
- play
- pause
- stop
- seek theo playhead
- hiển thị preview frame hiện tại
- hiển thị text overlay cơ bản

### Text overlay
- thêm text clip
- sửa nội dung text
- đổi màu chữ
- đổi size
- chỉnh vị trí cơ bản
- chỉnh duration trên timeline

### Export
- export ra mp4
- dùng canvas size của project
- hỗ trợ ít nhất một pipeline export ổn định cho video + text overlay cơ bản

---

## 2.2. Out of scope cho MVP

Không làm trong MVP:
- graph editor
- advanced effects
- transitions phức tạp
- mask
- multi-cam
- collaboration
- cloud sync
- AI editing
- audio waveform nâng cao
- advanced keyframe editor
- plugin system
- proxy workflow hoàn chỉnh
- color grading nâng cao

Các phần này chỉ xem là roadmap sau MVP.

---

## 3. Đối tượng người dùng mục tiêu

### Persona chính
Người dùng muốn một video editor desktop gọn nhẹ, dễ thao tác, phù hợp cho:
- cắt clip nhanh,
- thêm text,
- ghép video,
- làm social content đơn giản,
- thử nghiệm editor workflow.

### Persona phụ
Developer hoặc maker muốn dùng AI để phát triển dần một editor từ nền tảng có cấu trúc tốt.

---

## 4. Giá trị cốt lõi

Ứng dụng phải thể hiện được 4 giá trị:

1. **Timeline-first**
   - Người dùng thấy timeline là trung tâm của trải nghiệm.

2. **Direct manipulation**
   - Người dùng kéo, trim, split trực tiếp thay vì qua nhiều menu.

3. **Fast feedback**
   - Preview và UI phải cho cảm giác phản hồi nhanh.

4. **Extensible foundation**
   - Sau MVP có thể thêm captions, keyframes, stickers, snapping mà không đập bỏ kiến trúc.

---

## 5. User stories

## 5.1. Project
- Là người dùng, tôi muốn tạo project mới để bắt đầu edit.
- Là người dùng, tôi muốn lưu project để tiếp tục làm việc sau.
- Là người dùng, tôi muốn mở lại project cũ mà không mất cấu trúc timeline.

## 5.2. Media
- Là người dùng, tôi muốn import video/audio/image vào thư viện.
- Là người dùng, tôi muốn xem danh sách asset đã import.
- Là người dùng, tôi muốn kéo asset từ thư viện vào timeline.

## 5.3. Timeline
- Là người dùng, tôi muốn nhìn thấy clip theo trục thời gian.
- Là người dùng, tôi muốn kéo clip sang trái/phải để đổi vị trí.
- Là người dùng, tôi muốn trim đầu/cuối clip để cắt nhanh.
- Là người dùng, tôi muốn split clip tại vị trí playhead.
- Là người dùng, tôi muốn delete clip đã chọn.
- Là người dùng, tôi muốn playhead hiển thị đúng vị trí hiện tại.

## 5.4. Preview
- Là người dùng, tôi muốn play/pause preview.
- Là người dùng, tôi muốn khi kéo playhead thì preview cập nhật theo.
- Là người dùng, tôi muốn thấy text overlay xuất hiện đúng thời điểm.

## 5.5. Text
- Là người dùng, tôi muốn thêm một dòng text vào video.
- Là người dùng, tôi muốn chỉnh nội dung, màu và cỡ chữ.
- Là người dùng, tôi muốn text có duration trên timeline.

## 5.6. Export
- Là người dùng, tôi muốn export project thành file mp4.
- Là người dùng, tôi muốn file export phản ánh các clip và text đã sắp trên timeline.

---

## 6. Luồng người dùng chính

## 6.1. Flow A — Tạo project và import media
1. Người dùng mở app
2. Tạo project mới
3. Chọn canvas preset
4. Import một hoặc nhiều media file
5. Asset xuất hiện ở media library

## 6.2. Flow B — Dựng timeline
1. Người dùng kéo asset vào timeline
2. Clip xuất hiện ở track phù hợp
3. Người dùng kéo clip để đổi vị trí
4. Người dùng trim clip
5. Người dùng split clip nếu cần

## 6.3. Flow C — Thêm text
1. Người dùng click “Add Text”
2. Một text clip được tạo
3. Người dùng sửa nội dung trong inspector
4. Text xuất hiện trên preview
5. Người dùng chỉnh duration trên timeline

## 6.4. Flow D — Preview và export
1. Người dùng play preview
2. Người dùng seek theo playhead
3. Khi hài lòng, mở export dialog
4. Chọn output path
5. Export ra mp4

---

## 7. Giao diện chính

## 7.1. Main layout
App chia 4 vùng:

- trái: media panel
- giữa: preview panel
- phải: inspector panel
- dưới: timeline panel

Toolbar trên cùng:
- new/open/save
- undo/redo
- play/pause
- zoom
- export

## 7.2. Media panel
Hiển thị:
- nút import
- danh sách media
- thumbnail
- tên file
- duration cơ bản

## 7.3. Preview panel
Hiển thị:
- preview canvas
- playback controls
- current time

## 7.4. Inspector panel
Hiển thị theo selection:
- project settings
- video clip properties
- text clip properties
- image clip properties

## 7.5. Timeline panel
Hiển thị:
- tracks
- clip blocks
- playhead
- ruler
- selection state
- horizontal zoom/scroll

---

## 8. Functional requirements

## 8.1. Project
- FR-001: hệ thống phải cho phép tạo project mới
- FR-002: hệ thống phải cho phép lưu project thành file JSON
- FR-003: hệ thống phải cho phép mở lại project từ file JSON
- FR-004: hệ thống nên autosave định kỳ

## 8.2. Media
- FR-010: hệ thống phải cho phép import nhiều file media
- FR-011: hệ thống phải xác định loại media
- FR-012: hệ thống phải hiển thị media trong library
- FR-013: hệ thống phải cho phép kéo asset vào timeline

## 8.3. Timeline
- FR-020: hệ thống phải hiển thị clip theo timeline_start và duration
- FR-021: hệ thống phải cho phép move clip
- FR-022: hệ thống phải cho phép trim clip
- FR-023: hệ thống phải cho phép split clip
- FR-024: hệ thống phải cho phép delete clip
- FR-025: hệ thống phải cập nhật playhead khi playback thay đổi

## 8.4. Preview
- FR-030: hệ thống phải play/pause preview
- FR-031: hệ thống phải seek theo current time
- FR-032: hệ thống phải render text overlay cơ bản

## 8.5. Text
- FR-040: hệ thống phải cho phép thêm text clip
- FR-041: hệ thống phải cho phép sửa text content
- FR-042: hệ thống phải cho phép đổi color và font size
- FR-043: hệ thống phải cho phép chỉnh duration text clip

## 8.6. Export
- FR-050: hệ thống phải export được project thành mp4
- FR-051: export phải dùng canvas size của project
- FR-052: export phải phản ánh đúng timeline order cơ bản

---

## 9. Non-functional requirements

- NFR-001: app phải khởi động ổn định trên môi trường desktop mục tiêu
- NFR-002: UI không được block khi export
- NFR-003: project file phải dễ đọc và debug
- NFR-004: codebase phải tách rõ UI, domain, service, infrastructure
- NFR-005: command system phải hỗ trợ undo/redo cho các thao tác chính

---

## 10. Success criteria cho MVP

MVP được xem là thành công nếu:

1. app mở được và layout editor hoạt động,
2. import được media,
3. kéo media vào timeline được,
4. move/trim/split clip được,
5. play/pause/seek preview được,
6. thêm text overlay được,
7. export ra mp4 thành công,
8. save/load project không làm mất timeline cơ bản.

---

## 11. Milestones

## Milestone 1 — Foundation
- project structure
- main window
- panel layout
- basic project creation

## Milestone 2 — Timeline Core
- timeline widget
- clip rendering
- move/trim/split
- playhead
- selection

## Milestone 3 — Media & Preview
- media import
- asset library
- playback sync
- preview panel

## Milestone 4 — Text & Export
- text clip
- inspector editing
- export pipeline
- save/load polish

---

## 12. Acceptance checklist

### Project
- [ ] Có thể tạo project mới
- [ ] Có thể lưu project
- [ ] Có thể mở project

### Media
- [ ] Có thể import video/audio/image
- [ ] Asset hiển thị trong library
- [ ] Có thể kéo asset vào timeline

### Timeline
- [ ] Clip hiển thị đúng vị trí
- [ ] Có thể move clip
- [ ] Có thể trim clip
- [ ] Có thể split clip
- [ ] Có thể delete clip

### Preview
- [ ] Có thể play/pause
- [ ] Playhead và preview sync

### Text
- [ ] Có thể thêm text clip
- [ ] Có thể sửa text
- [ ] Có thể đổi màu và cỡ chữ

### Export
- [ ] Có thể export mp4
- [ ] File export mở được
- [ ] Timeline cơ bản phản ánh đúng trong output

---

## 13. Roadmap sau MVP

Sau MVP, ưu tiên như sau:

### V2
- multi-select
- snapping
- preview zoom/pan
- canvas presets
- image overlays
- captions import
- autosave hoàn chỉnh
- relink missing media

### V3
- keyframes
- graph editor
- waveform
- transitions
- proxy preview
- export queue

---

## 14. Quy tắc triển khai

- Không copy code từ OpenCut
- Chỉ dùng OpenCut để học product flow, timeline behaviors, panel organization
- Tất cả logic mới phải tuân theo `architecture.md`
- Tất cả tính năng mới phải map theo `feature-map.md`

Tài liệu này là chuẩn để quyết định “có làm trong MVP hay không”.
