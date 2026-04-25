"""Sprint 13: ProjectService gracefully skips legacy sticker entities."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.project_service import ProjectService


def test_load_legacy_project_skips_sticker_clip(tmp_path: Path) -> None:
    project_path = tmp_path / "legacy.json"
    payload = {
        "project_id": "p1",
        "name": "Legacy Project",
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "version": "0.1.0",
        "media_items": [],
        "timeline": {
            "tracks": [
                {
                    "track_id": "t1",
                    "name": "Main",
                    "track_type": "video",
                    "track_role": "main",
                    "clips": [
                        {
                            "clip_id": "c1",
                            "name": "video",
                            "clip_type": "video",
                            "timeline_start": 0.0,
                            "duration": 5.0,
                            "media_id": None,
                            "source_start": 0.0,
                            "source_end": None,
                            "opacity": 1.0,
                            "is_locked": False,
                            "is_muted": False,
                            "fade_in_seconds": 0.0,
                            "fade_out_seconds": 0.0,
                            "brightness": 0.5,  # legacy field, ignored.
                            "color_preset": "vintage",  # legacy field.
                        },
                        {
                            "clip_id": "c2_sticker",
                            "name": "old sticker",
                            "clip_type": "sticker",
                            "timeline_start": 1.0,
                            "duration": 2.0,
                        },
                    ],
                }
            ]
        },
    }
    project_path.write_text(json.dumps(payload), encoding="utf-8")

    service = ProjectService()
    project = service.load_project(str(project_path))

    assert project.name == "Legacy Project"
    assert len(project.timeline.tracks) == 1
    track = project.timeline.tracks[0]
    clip_ids = [clip.clip_id for clip in track.clips]
    assert "c1" in clip_ids
    assert "c2_sticker" not in clip_ids


def test_load_legacy_project_skips_sticker_track_and_asset(tmp_path: Path) -> None:
    project_path = tmp_path / "legacy2.json"
    payload = {
        "project_id": "p2",
        "name": "Legacy 2",
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "version": "0.1.0",
        "media_items": [
            {
                "media_id": "m1",
                "name": "song",
                "file_path": "/tmp/song.mp3",
                "media_type": "audio",
            },
            {
                "media_id": "m2",
                "name": "old sticker asset",
                "file_path": "/tmp/sticker.png",
                "media_type": "sticker",
            },
        ],
        "timeline": {
            "tracks": [
                {
                    "track_id": "t1",
                    "name": "Stickers",
                    "track_type": "sticker",
                    "track_role": "main",
                    "clips": [],
                },
                {
                    "track_id": "t2",
                    "name": "Main",
                    "track_type": "video",
                    "track_role": "main",
                    "clips": [],
                },
            ]
        },
    }
    project_path.write_text(json.dumps(payload), encoding="utf-8")

    service = ProjectService()
    project = service.load_project(str(project_path))

    assert [item.media_id for item in project.media_items] == ["m1"]
    track_ids = [track.track_id for track in project.timeline.tracks]
    assert track_ids == ["t2"]
