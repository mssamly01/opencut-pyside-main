from __future__ import annotations

import json
from pathlib import Path

from app.services.settings_service import SettingsService


def test_record_project_opened_updates_last_and_recent(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    service = SettingsService(settings_path=str(settings_path), max_recent_projects=3)

    first_project = tmp_path / "first.json"
    second_project = tmp_path / "second.json"

    service.record_project_opened(str(first_project))
    service.record_project_opened(str(second_project))
    service.record_project_opened(str(first_project))

    assert service.last_opened_project_path() == str(first_project.resolve())
    assert service.recent_project_paths() == [
        str(first_project.resolve()),
        str(second_project.resolve()),
    ]


def test_subtitle_extractor_model_dir_round_trip(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    service = SettingsService(settings_path=str(settings_path))

    assert service.subtitle_extractor_model_dir() is None

    model_dir = tmp_path / "ocr-models"
    model_dir.mkdir()
    service.set_subtitle_extractor_model_dir(str(model_dir))
    assert service.subtitle_extractor_model_dir() == str(model_dir.resolve())

    # Reload from disk to verify persistence.
    reloaded = SettingsService(settings_path=str(settings_path))
    assert reloaded.subtitle_extractor_model_dir() == str(model_dir.resolve())

    reloaded.set_subtitle_extractor_model_dir(None)
    assert reloaded.subtitle_extractor_model_dir() is None


def test_subtitle_extractor_model_dir_sanitizes_invalid_value_on_load(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"subtitle_extractor_model_dir": 42}),
        encoding="utf-8",
    )

    service = SettingsService(settings_path=str(settings_path))

    # Invalid value must be normalised to None and persisted as None.
    assert service.subtitle_extractor_model_dir() is None
    assert service._settings["subtitle_extractor_model_dir"] is None  # noqa: SLF001


def test_record_export_output_stores_directory(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    service = SettingsService(settings_path=str(settings_path))

    output_path = tmp_path / "exports" / "demo.mp4"
    service.record_export_output(str(output_path))

    assert service.last_export_directory() == str((tmp_path / "exports").resolve())


def test_load_ignores_invalid_json_payload(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{broken json", encoding="utf-8")

    service = SettingsService(settings_path=str(settings_path))

    assert service.last_opened_project_path() is None
    assert service.recent_project_paths() == []


def test_service_persists_to_disk(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    project_path = tmp_path / "project.json"

    first_service = SettingsService(settings_path=str(settings_path))
    first_service.record_project_saved(str(project_path))

    second_service = SettingsService(settings_path=str(settings_path))
    assert second_service.last_opened_project_path() == str(project_path.resolve())

    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    assert payload["last_opened_project_path"] == str(project_path.resolve())
