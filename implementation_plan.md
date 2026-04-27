# Kế hoạch cải thiện giao diện (Phong cách CapCut) - Bản cập nhật chính xác

Bản kế hoạch này tập trung vào việc loại bỏ các thành phần rườm rà và tối ưu hóa cho việc quản lý tên dự án cũng như phụ đề.

## 1. Điều chỉnh Thanh tiêu đề (Top Bar)
Tệp tin: `app/ui/top_bar.py`

- **Sửa tên trực tiếp:** Thay thế nhãn tên dự án bằng một ô nhập liệu (`QLineEdit`).
- **Hành vi:** Click vào tên dự án ở giữa thanh để sửa, nhấn Enter để lưu. Đồng bộ với toàn bộ ứng dụng.

## 2. Tinh chỉnh bảng điều khiển (Inspector Panel)
Tệp tin: `app/ui/inspector/inspector_panel.py`

- **Nút điều khiển (Tabs):**
    - **Loại bỏ** hoàn toàn nút/tab mang tên **"Chi tiết"** (Details).
    - **Thêm mới** tab mang tên **"Phụ đề"** (Subtitles) chỉ khi người dùng chọn vào một đoạn phụ đề SRT.
- **Mục tiêu:** Giao diện sạch sẽ, chỉ hiển thị tab khi thực sự cần thiết.

## 3. Cải tiến nội dung hiển thị (Details Inspector)
Tệp tin: `app/ui/inspector/details_inspector.py`

- **Tiêu đề (Header):**
    - Sử dụng tên dự án hoặc tên clip làm tiêu đề chính ở trên cùng.
    - Cho phép click vào tiêu đề này để sửa tên trực tiếp (đồng bộ với Top Bar).
- **Dọn dẹp nội dung:**
    - **Loại bỏ** các hàng thông số kỹ thuật (Resolution, FPS, Duration, Codec...) khi đang ở chế độ xem thông tin chung.
- **Chế độ Phụ đề:**
    - Khi tab "Phụ đề" được kích hoạt, chỉ hiển thị danh sách các câu phụ đề (`QListWidget`) để người dùng theo dõi và chỉnh sửa.

## 4. Các bước thực hiện
1. **Bước 1:** Cập nhật `top_bar.py` để hỗ trợ sửa tên dự án tại thanh tiêu đề.
2. **Bước 2:** Chỉnh sửa `inspector_panel.py` để xóa nút "Chi tiết" và thêm logic hiển thị tab "Phụ đề" linh hoạt.
3. **Bước 3:** Chỉnh sửa `details_inspector.py` để dọn dẹp các hàng thông số và thêm tính năng sửa tên tại header.
4. **Bước 4:** Kiểm tra tính năng đồng bộ và khả năng Hoàn tác (Undo).

---
> [!NOTE]
> Việc loại bỏ tab "Chi tiết" sẽ giúp giao diện trở nên tối giản và hiện đại hơn, đúng theo phong cách của CapCut.
