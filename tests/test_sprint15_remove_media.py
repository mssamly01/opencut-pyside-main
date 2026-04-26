"""Sprint 15: cascade-delete media asset + clips referencing it, with undo."""

from __future__ import annotations

import pytest
from app.controllers.app_controller import AppController
from app.domain.clips.audio_clip import AudioClip
from app.domain.clips.video_clip import VideoClip
from app.domain.commands import CompositeCommand, RemoveMediaAssetCommand
from app.domain.media_asset import MediaAsset
from app.domain.project import Project, build_empty_project
from app.domain.timeline import Timeline
from PySide6.QtWidgets import QApplication


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _project_with_two_assets() -> Project:
    return Project(
        project_id="p1",
        name="t",
        width=1920,
        height=1080,
        fps=30.0,
        timeline=Timeline(tracks=[]),
        media_items=[
            MediaAsset(media_id="m1", name="A", file_path="/a.mp4", media_type="video"),
            MediaAsset(media_id="m2", name="B", file_path="/b.wav", media_type="audio"),
        ],
    )


def test_remove_media_asset_command_pops_and_restores_index() -> None:
    project = _project_with_two_assets()
    cmd = RemoveMediaAssetCommand(project=project, media_id="m1")

    cmd.execute()
    assert [asset.media_id for asset in project.media_items] == ["m2"]

    cmd.undo()
    assert [asset.media_id for asset in project.media_items] == ["m1", "m2"]


def test_remove_media_asset_command_raises_when_missing() -> None:
    project = _project_with_two_assets()
    cmd = RemoveMediaAssetCommand(project=project, media_id="missing")
    with pytest.raises(ValueError):
        cmd.execute()


def test_clips_using_media_returns_referencing_clip_ids(qapp: QApplication) -> None:
    controller = AppController()
    project = build_empty_project()
    project.media_items.append(
        MediaAsset(media_id="mA", name="A", file_path="/a.wav", media_type="audio")
    )
    # Empty project only ships with the main video track; create an audio track on demand.
    from app.domain.track import Track

    audio_track = Track(
        track_id="track_audio_test",
        name="Audio",
        track_type="audio",
        clips=[],
    )
    project.timeline.tracks.append(audio_track)
    audio_track.clips.extend(
        [
            AudioClip(
                clip_id="c1",
                name="clip1",
                track_id=audio_track.track_id,
                media_id="mA",
                timeline_start=0.0,
                duration=1.0,
                source_start=0.0,
                source_end=1.0,
            ),
            AudioClip(
                clip_id="c2",
                name="clip2",
                track_id=audio_track.track_id,
                media_id="mA",
                timeline_start=2.0,
                duration=1.0,
                source_start=0.0,
                source_end=1.0,
            ),
        ]
    )
    controller.project_controller.set_active_project(project)

    using = controller.timeline_controller.clips_using_media("mA")
    assert sorted(using) == ["c1", "c2"]
    assert controller.timeline_controller.clips_using_media("missing") == []


def test_remove_media_no_clips_only_pops_asset(qapp: QApplication) -> None:
    controller = AppController()
    project = build_empty_project()
    project.media_items.append(
        MediaAsset(media_id="mX", name="X", file_path="/x.mp4", media_type="video")
    )
    controller.project_controller.set_active_project(project)

    received: list[None] = []
    controller.project_controller.media_assets_changed.connect(lambda: received.append(None))

    removed = controller.timeline_controller.remove_media("mX")

    assert removed == 0
    assert [asset.media_id for asset in project.media_items] == []
    assert len(received) == 1


def test_remove_media_cascade_deletes_clips_and_undo_restores(qapp: QApplication) -> None:
    controller = AppController()
    project = build_empty_project()
    project.media_items.append(
        MediaAsset(media_id="mV", name="V", file_path="/v.mp4", media_type="video")
    )
    video_track = next(track for track in project.timeline.tracks if track.track_type == "video")
    video_track.clips.append(
        VideoClip(
            clip_id="vc1",
            name="vclip",
            track_id=video_track.track_id,
            media_id="mV",
            timeline_start=0.0,
            duration=2.0,
            source_start=0.0,
            source_end=2.0,
        )
    )
    controller.project_controller.set_active_project(project)

    removed = controller.timeline_controller.remove_media("mV")

    assert removed == 1
    assert project.media_items == []
    assert video_track.clips == []

    assert controller.timeline_controller.undo() is True
    assert [asset.media_id for asset in project.media_items] == ["mV"]
    assert [clip.clip_id for clip in video_track.clips] == ["vc1"]

    assert controller.timeline_controller.redo() is True
    assert project.media_items == []
    assert video_track.clips == []


def test_remove_media_unknown_media_id_is_noop_at_controller_level(qapp: QApplication) -> None:
    controller = AppController()
    project = build_empty_project()
    project.media_items.append(
        MediaAsset(media_id="mY", name="Y", file_path="/y.mp4", media_type="video")
    )
    controller.project_controller.set_active_project(project)

    with pytest.raises(ValueError):
        controller.timeline_controller.remove_media("not-a-real-id")
    # Asset list still intact
    assert [asset.media_id for asset in project.media_items] == ["mY"]


def test_composite_remove_with_clip_undo_order(qapp: QApplication) -> None:
    """Cascade undo restores clips and asset in original positions."""
    project = build_empty_project()
    project.media_items.append(
        MediaAsset(media_id="mZ", name="Z", file_path="/z.wav", media_type="audio")
    )
    from app.domain.track import Track

    audio_track = Track(
        track_id="track_audio_test_z",
        name="Audio",
        track_type="audio",
        clips=[],
    )
    project.timeline.tracks.append(audio_track)
    clip = AudioClip(
        clip_id="ac1",
        name="aclip",
        track_id=audio_track.track_id,
        media_id="mZ",
        timeline_start=1.5,
        duration=0.7,
        source_start=0.0,
        source_end=0.7,
    )
    audio_track.clips.append(clip)

    from app.domain.commands import DeleteClipCommand

    composite = CompositeCommand(
        [
            DeleteClipCommand(timeline=project.timeline, clip_id="ac1"),
            RemoveMediaAssetCommand(project=project, media_id="mZ"),
        ]
    )
    composite.execute()
    assert audio_track.clips == []
    assert project.media_items == []

    composite.undo()
    assert [asset.media_id for asset in project.media_items] == ["mZ"]
    assert [c.clip_id for c in audio_track.clips] == ["ac1"]
