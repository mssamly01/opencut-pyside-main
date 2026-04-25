from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from app.controllers.project_controller import ProjectController
from app.domain.project import Project
from app.dto.export_dto import ExportOptions, ExportResult
from app.services.export_service import ExportService
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


@dataclass(slots=True)
class _ExportRequest:
    request_id: int
    project: Project
    project_path: str | None
    output_path: str
    options: ExportOptions | None = None


class _ExportSignals(QObject):
    progress = Signal(int, float, str)
    completed = Signal(int, object)
    failed = Signal(int, str)


class _ExportWorker(QRunnable):
    def __init__(self, request: _ExportRequest, export_service: ExportService) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._request = request
        self._export_service = export_service
        self.signals = _ExportSignals()

    def run(self) -> None:
        try:
            export_result = self._export_service.export_project(
                self._request.project,
                self._request.output_path,
                project_path=self._request.project_path,
                progress_callback=lambda percent, message: self.signals.progress.emit(
                    self._request.request_id,
                    percent,
                    message,
                ),
                options=self._request.options,
            )
        except Exception as exc:  # pragma: no cover - defensive guard for worker-thread failures
            self.signals.failed.emit(self._request.request_id, str(exc))
            return

        self.signals.completed.emit(self._request.request_id, export_result)


class ExportController(QObject):
    export_started = Signal(str)
    export_progress_changed = Signal(float, str)
    export_finished = Signal(object)
    export_failed = Signal(str)
    export_in_progress_changed = Signal(bool)

    def __init__(
        self,
        project_controller: ProjectController,
        export_service: ExportService,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._project_controller = project_controller
        self._export_service = export_service
        self._export_thread_pool = QThreadPool(self)
        self._export_thread_pool.setMaxThreadCount(1)
        self._export_request_counter = 0
        self._active_export_request_id: int | None = None
        self._is_exporting = False

    def is_exporting(self) -> bool:
        return self._is_exporting

    def export_active_project(
        self,
        output_path: str,
        options: ExportOptions | None = None,
    ) -> None:
        project = self._project_controller.active_project()
        if project is None:
            raise ValueError("No active project to export.")

        normalized_output_path = output_path.strip()
        if not normalized_output_path:
            raise ValueError("An export output path is required.")

        if self._is_exporting:
            raise RuntimeError("An export is already in progress.")

        request_id = self._export_request_counter + 1
        self._export_request_counter = request_id
        request = _ExportRequest(
            request_id=request_id,
            project=deepcopy(project),
            project_path=self._project_controller.active_project_path(),
            output_path=normalized_output_path,
            options=options,
        )

        worker = _ExportWorker(request, self._export_service)
        worker.signals.progress.connect(self._on_export_progress)
        worker.signals.completed.connect(self._on_export_completed)
        worker.signals.failed.connect(self._on_export_failed)

        self._active_export_request_id = request_id
        self._is_exporting = True
        self.export_in_progress_changed.emit(True)
        self.export_started.emit(normalized_output_path)

        try:
            self._start_export_worker(worker)
        except Exception:
            self._active_export_request_id = None
            self._is_exporting = False
            self.export_in_progress_changed.emit(False)
            raise

    def _start_export_worker(self, worker: QRunnable) -> None:
        self._export_thread_pool.start(worker)

    def _on_export_progress(self, request_id: int, percent: float, message: str) -> None:
        if request_id != self._active_export_request_id:
            return
        self.export_progress_changed.emit(percent, message)

    def _on_export_completed(self, request_id: int, export_result: ExportResult) -> None:
        if request_id != self._active_export_request_id:
            return

        self._active_export_request_id = None
        self._is_exporting = False
        self.export_finished.emit(export_result)
        self.export_in_progress_changed.emit(False)

    def _on_export_failed(self, request_id: int, message: str) -> None:
        if request_id != self._active_export_request_id:
            return

        self._active_export_request_id = None
        self._is_exporting = False
        self.export_failed.emit(message)
        self.export_in_progress_changed.emit(False)
