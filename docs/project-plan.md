# Project-plan.md — Current Status & Execution Plan

## 1. Mục tiêu
Đồng bộ tài liệu kế hoạch với trạng thái code hiện tại, rồi dùng nó để chọn slice tiếp theo mà không làm lệch kiến trúc.

---

## 2. Snapshot hiện tại (Apr 2026)

- [x] App mở được, shell 4 panel hoạt động ổn định.
- [x] Timeline core đã có: render track/clip, selection, playhead, move/trim/split, zoom, ruler seek/scrub, snapping cơ bản.
- [x] Media flow đã có: import video/audio/image, media library, drag asset vào timeline, probe duration bằng `FFprobeGateway`.
- [x] Preview & playback cơ bản đã có: play/pause/stop, seek, preview frame cho video/image, audio playback đa clip.
- [x] Persistence đã có: save/load project JSON, autosave, recovery prompt khi khởi động.
- [x] Export MP4 đã có: worker-thread export, progress reporting, error handling, ffmpeg integration.
- [x] Settings store cơ bản đã có: nhớ project gần nhất, recent files, thư mục export gần nhất.
- [x] Text workflow MVP đã khép vòng: có add-text action, inspector text cơ bản (`content`, `font size`, `color`, `position`), preview text cơ bản, export text cơ bản, save/load text attrs.
- [ ] Các hạng mục V2 / polish như multi-select, captions, thumbnail service, logging, CI vẫn chưa làm.

---

## 3. Sprint status theo thực tế

## Sprint 1 (Day 1–3) — Foundation
Tasks:
- [x] Setup project structure
- [x] MainWindow layout
- [x] Basic app bootstrap
- [x] Project model skeleton
- [x] Settings store cơ bản

Deliverable:
- [x] App mở được
- [x] UI có 4 panel

---

## Sprint 2 (Day 4–7) — Timeline Core
Tasks:
- [x] TimelineView (QGraphicsView)
- [x] Clip rendering
- [x] Drag clip
- [x] Playhead
- [x] Selection basic

Deliverable:
- [x] Timeline drag được

---

## Sprint 3 (Day 8–10) — Editing Core
Tasks:
- [x] Trim clip
- [x] Split clip
- [x] Command system (undo/redo)
- [x] TimelineController

Deliverable:
- [x] Editor usable

---

## Sprint 4 (Day 11–14) — Media + Preview
Tasks:
- [x] Media import
- [x] Media panel
- [x] PlaybackController
- [x] PreviewWidget

Deliverable:
- [x] Có preview video

---

## Sprint 5 (Day 15–18) — Text + Export
Tasks:
- [x] Text clip end-to-end
- [x] Inspector panel cơ bản
- [x] ExportService
- [x] ffmpeg integration

Deliverable:
- [x] Export mp4 thành công
- [x] Text overlay workflow MVP hoàn chỉnh

Ghi chú:
- `TextClip` đã hỗ trợ thuộc tính text tối thiểu (`content`, `font_size`, `color`, `position_x`, `position_y`).
- UI đã có action `Add Text` tạo clip qua controller/command và undo/redo được.
- `PlaybackService` và `ExportService` đã có render text cơ bản cho MVP.

---

## Sprint 6 (Optional) — V2
Tasks:
- [ ] Multi-select
- [ ] Snapping nâng cao (hiện mới có snapping cơ bản cho single-clip drag/trim + guide line)
- [ ] Captions

---

## 4. Thứ tự triển khai khuyến nghị tiếp theo

### P0 — Close MVP text gap
1. ✅ Đã hoàn thành trong codebase hiện tại.
2. ✅ Ưu tiên kế tiếp: giữ ổn định bằng test/manual checklist khi có thay đổi playback/export sâu hơn.

### P1 — Foundation polish
1. ✅ Thay `print()` còn sót bằng `logging`.
2. ✅ Thêm “Open log folder” và ghi log quay vòng theo roadmap.
3. ✅ Đảm bảo local dev setup chạy được `pytest` từ `requirements-dev.txt`.

### P2 — Media pipeline hardening
1. ✅ `ThumbnailService` cơ bản đã thực thi (cache disk+memory, timeline hiển thị thumbnail cho video/image clip).
2. Cải thiện decode path cho preview để giảm shell-out FFmpeg mỗi frame.
3. Mở rộng thumbnail generation theo hướng filmstrip/background worker (không block UI).
4. Bổ sung waveform / metadata sâu hơn khi cần.

---

## 5. Daily Workflow

Mỗi ngày:
1. Đồng bộ docs nếu trạng thái hoặc scope thay đổi.
2. Chọn 1 slice nhỏ theo thứ tự ưu tiên hiện tại.
3. Implement theo ranh giới UI / controller / domain / service.
4. Run app hoặc `main.py --smoke-test`.
5. Fix bug + manual test flow chính.
6. Commit

---

## 6. Git Strategy

- branch theo feature
- commit nhỏ
- không commit code chưa chạy

---

## 7. Risk Tracking

| Risk | Status | Fix |
|------|--------|-----|
| Timeline bug | TBD | debug |
| Preview lag | TBD | simplify |
