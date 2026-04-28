"""Dialog for the "Trích xuất phụ đề từ video" action.

Lets the user pick a video file, draw the subtitle area on a frame
preview, choose language + mode, and run the vendored OCR engine in a
background thread. Resulting ``.srt`` is auto-imported into opencut's
subtitle library.
"""

from __future__ import annotations

from pathlib import Path

from app.infrastructure.ffmpeg_gateway import FFmpegGateway
from app.infrastructure.ffprobe_gateway import FFprobeGateway
from app.services.settings_service import SettingsService
from app.services.subtitle_extraction_service import (
    SUPPORTED_LANGUAGES,
    SUPPORTED_MODES,
    extract_subtitles,
    is_available,
    set_model_dir,
)
from PySide6.QtCore import QObject, QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

PREVIEW_MAX_WIDTH = 480
PREVIEW_MAX_HEIGHT = 270


class _ExtractionWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        video_path: str,
        subtitle_area: tuple[int, int, int, int],
        language: str,
        mode: str,
    ) -> None:
        super().__init__()
        self._video_path = video_path
        self._subtitle_area = subtitle_area
        self._language = language
        self._mode = mode

    def run(self) -> None:
        try:
            srt_path = extract_subtitles(
                video_path=self._video_path,
                subtitle_area=self._subtitle_area,
                language=self._language,
                mode=self._mode,
            )
        except Exception as exc:  # noqa: BLE001 — surface any engine error to UI.
            self.failed.emit(str(exc))
            return
        self.finished.emit(srt_path)


class _PreviewLabel(QLabel):
    """QLabel that paints a red subtitle-area rectangle on top of its pixmap."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(QSize(PREVIEW_MAX_WIDTH, PREVIEW_MAX_HEIGHT))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background:#202020;color:#888;")
        self.setText(self.tr("Chưa chọn video"))
        self._source_pixmap: QPixmap | None = None
        self._video_size: tuple[int, int] = (0, 0)
        self._area: tuple[int, int, int, int] = (0, 0, 0, 0)  # ymin, ymax, xmin, xmax

    def set_preview(self, pixmap: QPixmap, video_size: tuple[int, int]) -> None:
        self._source_pixmap = pixmap
        self._video_size = video_size
        self._render()

    def set_area(self, ymin: int, ymax: int, xmin: int, xmax: int) -> None:
        self._area = (ymin, ymax, xmin, xmax)
        self._render()

    def _render(self) -> None:
        if self._source_pixmap is None or self._video_size == (0, 0):
            return
        scaled = self._source_pixmap.scaled(
            PREVIEW_MAX_WIDTH,
            PREVIEW_MAX_HEIGHT,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        canvas = QPixmap(scaled.size())
        canvas.fill(Qt.GlobalColor.black)
        painter = QPainter(canvas)
        painter.drawPixmap(0, 0, scaled)
        ymin, ymax, xmin, xmax = self._area
        if ymax > ymin and xmax > xmin:
            vid_w, vid_h = self._video_size
            sx = scaled.width() / max(1, vid_w)
            sy = scaled.height() / max(1, vid_h)
            pen = QPen(QColor(255, 64, 64))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawRect(
                int(xmin * sx),
                int(ymin * sy),
                int((xmax - xmin) * sx),
                int((ymax - ymin) * sy),
            )
        painter.end()
        self.setPixmap(canvas)


class ExtractSubtitleDialog(QDialog):
    """Compose video + subtitle area + language picker; emit a path.

    On success, ``result_srt_path`` holds the produced ``.srt`` and the
    dialog ``accept()``s. The caller is expected to import that path
    into the subtitle library.
    """

    def __init__(
        self,
        settings_service: SettingsService,
        parent: QWidget | None = None,
        initial_video_path: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Trích xuất phụ đề từ video"))
        self.setModal(True)
        self.resize(560, 640)

        self._settings = settings_service
        self._ffmpeg = FFmpegGateway()
        self._ffprobe = FFprobeGateway()
        self._video_size: tuple[int, int] = (0, 0)
        self._thread: QThread | None = None
        self._worker: _ExtractionWorker | None = None
        self.result_srt_path: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # --- Video picker -------------------------------------------------
        video_row = QHBoxLayout()
        self._video_edit = QLineEdit(initial_video_path or "", self)
        self._video_edit.setReadOnly(True)
        video_browse = QPushButton(self.tr("Chọn video..."), self)
        video_browse.clicked.connect(self._on_pick_video)
        video_row.addWidget(QLabel(self.tr("Video:"), self))
        video_row.addWidget(self._video_edit, 1)
        video_row.addWidget(video_browse)
        root.addLayout(video_row)

        # --- Frame preview + area picker ---------------------------------
        self._preview = _PreviewLabel(self)
        root.addWidget(self._preview, 1)

        area_form = QFormLayout()
        area_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._x_spin = QSpinBox(self)
        self._y_spin = QSpinBox(self)
        self._w_spin = QSpinBox(self)
        self._h_spin = QSpinBox(self)
        for spin in (self._x_spin, self._y_spin, self._w_spin, self._h_spin):
            spin.setRange(0, 16384)
            spin.valueChanged.connect(self._sync_preview_area)
        area_form.addRow(self.tr("X (trái):"), self._x_spin)
        area_form.addRow(self.tr("Y (trên):"), self._y_spin)
        area_form.addRow(self.tr("Rộng:"), self._w_spin)
        area_form.addRow(self.tr("Cao:"), self._h_spin)
        root.addLayout(area_form)

        # --- Language + mode ---------------------------------------------
        opts_form = QFormLayout()
        self._lang_combo = QComboBox(self)
        for code, label in SUPPORTED_LANGUAGES:
            self._lang_combo.addItem(label, userData=code)
        self._mode_combo = QComboBox(self)
        for code, label in SUPPORTED_MODES:
            self._mode_combo.addItem(label, userData=code)
        opts_form.addRow(self.tr("Ngôn ngữ:"), self._lang_combo)
        opts_form.addRow(self.tr("Chế độ:"), self._mode_combo)
        root.addLayout(opts_form)

        # --- Model directory ---------------------------------------------
        model_row = QHBoxLayout()
        self._model_edit = QLineEdit(self)
        self._model_edit.setReadOnly(True)
        self._model_edit.setPlaceholderText(
            self.tr("Chưa chọn thư mục models PaddleOCR (V4)")
        )
        model_browse = QPushButton(self.tr("Chọn thư mục models..."), self)
        model_browse.clicked.connect(self._on_pick_model_dir)
        model_row.addWidget(QLabel(self.tr("Models:"), self))
        model_row.addWidget(self._model_edit, 1)
        model_row.addWidget(model_browse)
        root.addLayout(model_row)

        # --- Progress + buttons ------------------------------------------
        self._progress = QProgressBar(self)
        self._progress.setRange(0, 0)  # indeterminate while running
        self._progress.setVisible(False)
        root.addWidget(self._progress)

        self._status_label = QLabel("", self)
        self._status_label.setStyleSheet("color:#aaa;")
        self._status_label.setWordWrap(True)
        root.addWidget(self._status_label)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr("Trích xuất"))
        self._buttons.accepted.connect(self._on_run)
        self._buttons.rejected.connect(self.reject)
        root.addWidget(self._buttons)

        # --- Wire initial state ------------------------------------------
        existing_model_dir = self._settings.subtitle_extractor_model_dir()
        if existing_model_dir:
            self._model_edit.setText(existing_model_dir)
            set_model_dir(existing_model_dir)

        if initial_video_path:
            self._load_video(initial_video_path)

    # ---------------------------------------------------------------- pickers
    def _on_pick_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Chọn file video"),
            self._video_edit.text() or "",
            self.tr("Video (*.mp4 *.mov *.mkv *.avi *.webm);;All files (*.*)"),
        )
        if path:
            self._video_edit.setText(path)
            self._load_video(path)

    def _on_pick_model_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            self.tr("Chọn thư mục models PaddleOCR (chứa subdir 'V4/')"),
            self._model_edit.text() or str(Path.home()),
        )
        if not path:
            return
        if not (Path(path) / "V4").is_dir():
            QMessageBox.warning(
                self,
                self.tr("Thư mục models không hợp lệ"),
                self.tr(
                    "Thư mục đã chọn không chứa subdir 'V4/'. Hãy trỏ vào thư "
                    "mục cha (ví dụ '<Extractor_doda>/modules/extractor/"
                    "VSE_MODULE/backend/models')."
                ),
            )
            return
        self._model_edit.setText(path)
        self._settings.set_subtitle_extractor_model_dir(path)
        set_model_dir(path)

    # ---------------------------------------------------------------- preview
    def _load_video(self, video_path: str) -> None:
        probe = self._ffprobe.probe(video_path) if self._ffprobe.is_available() else None
        if probe is None or not probe.width or not probe.height:
            self._video_size = (0, 0)
            self._preview.setText(self.tr("Không đọc được metadata của video."))
            return

        width, height = int(probe.width), int(probe.height)
        self._video_size = (width, height)

        for spin in (self._x_spin, self._y_spin, self._w_spin, self._h_spin):
            spin.blockSignals(True)
        self._x_spin.setRange(0, max(0, width - 1))
        self._y_spin.setRange(0, max(0, height - 1))
        self._w_spin.setRange(1, width)
        self._h_spin.setRange(1, height)
        # Default subtitle area: bottom 18% strip, full width.
        default_h = max(40, int(height * 0.18))
        default_y = max(0, height - default_h - max(20, int(height * 0.03)))
        self._x_spin.setValue(0)
        self._y_spin.setValue(default_y)
        self._w_spin.setValue(width)
        self._h_spin.setValue(default_h)
        for spin in (self._x_spin, self._y_spin, self._w_spin, self._h_spin):
            spin.blockSignals(False)

        png_bytes = self._ffmpeg.extract_frame_png(video_path, time_seconds=1.0)
        if png_bytes:
            image = QImage.fromData(png_bytes, "PNG")
            if not image.isNull():
                pixmap = QPixmap.fromImage(image)
                self._preview.set_preview(pixmap, (width, height))

        self._sync_preview_area()

    def _sync_preview_area(self) -> None:
        x = self._x_spin.value()
        y = self._y_spin.value()
        w = self._w_spin.value()
        h = self._h_spin.value()
        self._preview.set_area(ymin=y, ymax=y + h, xmin=x, xmax=x + w)

    # ---------------------------------------------------------------- run
    def _on_run(self) -> None:
        video_path = self._video_edit.text().strip()
        if not video_path or not Path(video_path).is_file():
            QMessageBox.warning(
                self,
                self.tr("Thiếu video"),
                self.tr("Hãy chọn một file video hợp lệ."),
            )
            return
        if self._video_size == (0, 0):
            QMessageBox.warning(
                self,
                self.tr("Video chưa đọc được"),
                self.tr("Không đọc được metadata. Kiểm tra ffprobe và file video."),
            )
            return

        availability = is_available()
        if not availability.ok:
            QMessageBox.warning(self, self.tr("Chưa thể trích xuất"), availability.hint)
            return

        x = self._x_spin.value()
        y = self._y_spin.value()
        w = self._w_spin.value()
        h = self._h_spin.value()
        if w <= 0 or h <= 0:
            QMessageBox.warning(
                self,
                self.tr("Vùng phụ đề không hợp lệ"),
                self.tr("Rộng và cao phải lớn hơn 0."),
            )
            return
        subtitle_area = (y, y + h, x, x + w)

        language = self._lang_combo.currentData() or "vi"
        mode = self._mode_combo.currentData() or "fast"

        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self._buttons.button(QDialogButtonBox.StandardButton.Cancel).setEnabled(False)
        self._progress.setVisible(True)
        self._status_label.setText(self.tr("Đang chạy OCR... có thể mất vài phút."))

        self._thread = QThread(self)
        self._worker = _ExtractionWorker(
            video_path=video_path,
            subtitle_area=subtitle_area,
            language=language,
            mode=mode,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_finished(self, srt_path: str) -> None:
        self.result_srt_path = srt_path
        self._progress.setVisible(False)
        self._status_label.setText(self.tr("Hoàn tất: {path}").format(path=srt_path))
        self.accept()

    def _on_failed(self, error_message: str) -> None:
        self._progress.setVisible(False)
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        self._buttons.button(QDialogButtonBox.StandardButton.Cancel).setEnabled(True)
        self._status_label.setText(self.tr("Lỗi: {msg}").format(msg=error_message))
        QMessageBox.critical(self, self.tr("Trích xuất thất bại"), error_message)

    def _is_extraction_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def reject(self) -> None:
        # Chặn đóng dialog (qua nút X hoặc Esc) trong khi engine còn chạy.
        # Nếu cho phép, QThread sẽ bị deleted khi parent destroy → crash, và
        # mỗi lần reopen sẽ tích thêm 1 OCR thread chạy ngầm.
        if self._is_extraction_running():
            QMessageBox.information(
                self,
                self.tr("Đang trích xuất"),
                self.tr("Quá trình trích xuất đang chạy. Vui lòng đợi đến khi hoàn tất."),
            )
            return
        super().reject()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._is_extraction_running():
            QMessageBox.information(
                self,
                self.tr("Đang trích xuất"),
                self.tr("Quá trình trích xuất đang chạy. Vui lòng đợi đến khi hoàn tất."),
            )
            event.ignore()
            return
        super().closeEvent(event)
