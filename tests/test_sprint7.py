from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.dto.export_dto import ExportOptions


def test_gpu_encoder_probe_parses_encoders_list() -> None:
    from app.infrastructure.gpu_encoder import GpuEncoderProbe

    fake_output = (
        "Encoders:\n"
        " V..... libx264              libx264 H.264 / AVC\n"
        " V..... h264_nvenc           NVIDIA NVENC H.264 encoder\n"
        " V..... h264_qsv             Intel QSV H.264 encoder\n"
    )
    probe = GpuEncoderProbe(ffmpeg_executable="ffmpeg")
    with patch("app.infrastructure.gpu_encoder.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=fake_output, stderr="")
        available = probe.available()

    names = {codec.name for codec in available}
    assert "h264_nvenc" in names
    assert "h264_qsv" in names
    assert "h264_amf" not in names


def test_gpu_encoder_probe_handles_subprocess_failure() -> None:
    from app.infrastructure.gpu_encoder import GpuEncoderProbe

    probe = GpuEncoderProbe(ffmpeg_executable="ffmpeg")
    with patch("app.infrastructure.gpu_encoder.subprocess.run", side_effect=OSError("missing")):
        result = probe.available()
    assert result == ()


def test_export_uses_gpu_codec_when_override_auto_and_available() -> None:
    from app.domain.project import build_demo_project
    from app.services.export_service import ExportService

    project = build_demo_project()
    service = ExportService(ffmpeg_executable="/bin/true")
    fake_codec = MagicMock()
    fake_codec.name = "h264_nvenc"

    with patch.object(service._gpu_probe, "first_available_h264", return_value=fake_codec):
        command = service._build_ffmpeg_command(
            project=project,
            target_path=Path("out.mp4"),
            warnings=[],
            project_root=None,
            options=ExportOptions(gpu_codec_override="auto"),
            in_point=0.0,
            out_point=None,
        )

    codec_index = command.index("-c:v")
    assert command[codec_index + 1] == "h264_nvenc"


def test_export_falls_back_to_libx264_when_gpu_unavailable() -> None:
    from app.domain.project import build_demo_project
    from app.services.export_service import ExportService

    project = build_demo_project()
    service = ExportService(ffmpeg_executable="/bin/true")
    warnings: list[str] = []

    with patch.object(service._gpu_probe, "first_available_h264", return_value=None):
        command = service._build_ffmpeg_command(
            project=project,
            target_path=Path("out.mp4"),
            warnings=warnings,
            project_root=None,
            options=ExportOptions(gpu_codec_override="auto"),
            in_point=0.0,
            out_point=None,
        )

    codec_index = command.index("-c:v")
    assert command[codec_index + 1] == "libx264"
    assert any("No GPU encoder detected" in warning for warning in warnings)


def test_export_explicit_gpu_codec_unavailable_falls_back() -> None:
    from app.domain.project import build_demo_project
    from app.services.export_service import ExportService

    project = build_demo_project()
    service = ExportService(ffmpeg_executable="/bin/true")
    warnings: list[str] = []

    with patch.object(service._gpu_probe, "available", return_value=()):
        command = service._build_ffmpeg_command(
            project=project,
            target_path=Path("out.mp4"),
            warnings=warnings,
            project_root=None,
            options=ExportOptions(gpu_codec_override="h264_nvenc"),
            in_point=0.0,
            out_point=None,
        )

    codec_index = command.index("-c:v")
    assert command[codec_index + 1] == "libx264"
    assert any("Requested GPU encoder" in warning for warning in warnings)


def test_crash_reporter_writes_log_with_traceback(tmp_path: Path) -> None:
    from app.infrastructure.crash_reporter import CrashReporter

    crash_dir = tmp_path / "crash"
    reporter = CrashReporter(
        crash_dir=crash_dir,
        context_provider=lambda: {"foo": "bar"},
    )

    try:
        raise RuntimeError("boom")
    except RuntimeError:
        report_path = reporter.write_report(*sys.exc_info())

    assert report_path is not None
    assert report_path.exists()
    payload = report_path.read_text(encoding="utf-8")
    assert "RuntimeError" in payload
    assert "boom" in payload
    assert "foo: bar" in payload


def test_crash_reporter_handles_context_provider_failure(tmp_path: Path) -> None:
    from app.infrastructure.crash_reporter import CrashReporter

    def bad_provider() -> dict:
        raise ValueError("context died")

    reporter = CrashReporter(crash_dir=tmp_path / "crash", context_provider=bad_provider)

    try:
        raise RuntimeError("boom2")
    except RuntimeError:
        report_path = reporter.write_report(*sys.exc_info())

    assert report_path is not None
    payload = report_path.read_text(encoding="utf-8")
    assert "context provider failed" in payload


def test_thumbnail_service_lru_evicts_oldest(tmp_path: Path) -> None:
    from app.services.thumbnail_service import ThumbnailService

    service = ThumbnailService(cache_root=tmp_path / "thumb_cache", max_memory_entries=3)
    service._remember_in_cache("a", b"1")
    service._remember_in_cache("b", b"2")
    service._remember_in_cache("c", b"3")
    service._remember_in_cache("d", b"4")

    assert "a" not in service._memory_cache
    assert list(service._memory_cache.keys()) == ["b", "c", "d"]

    service._memory_cache.move_to_end("b")
    service._remember_in_cache("e", b"5")
    assert "c" not in service._memory_cache
    assert list(service._memory_cache.keys())[-1] == "e"
