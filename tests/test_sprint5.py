from __future__ import annotations

import pytest
from app.controllers.app_controller import AppController
from app.domain.clips.sticker_clip import StickerClip
from app.domain.clips.text_clip import TextClip
from app.domain.clips.video_clip import VideoClip
from app.domain.commands import AddStickerClipCommand, CommandManager, UpdateKeyframeBezierCommand
from app.domain.keyframe import Keyframe
from app.domain.project import build_demo_project
from app.domain.track import Track
from app.domain.word_timing import WordTiming
from app.services.caption_service import CaptionSegment
from app.services.project_service import ProjectService
from PySide6.QtWidgets import QApplication


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_caption_segment_split_words_evenly() -> None:
    segment = CaptionSegment(start_seconds=1.0, end_seconds=3.0, text="hello world again")
    words = segment.split_words_evenly()
    assert len(words) == 3
    assert words[0].text == "hello"
    assert words[-1].end_seconds == pytest.approx(3.0)


def test_text_clip_split_words_evenly_uses_timeline_start() -> None:
    clip = TextClip(
        clip_id="t1",
        name="Caption",
        track_id="track_text",
        timeline_start=4.0,
        duration=2.0,
        content="one two",
    )
    words = clip.split_words_evenly()
    assert len(words) == 2
    assert words[0].start_seconds == pytest.approx(4.0)
    assert words[1].end_seconds == pytest.approx(6.0)


def test_add_sticker_clip_command_undo_redo() -> None:
    track = Track(track_id="track_overlay", name="Overlay", track_type="overlay")
    clip = StickerClip(
        clip_id="sticker_1",
        name="heart",
        track_id=track.track_id,
        timeline_start=0.0,
        duration=2.0,
        sticker_path="ui/resources/stickers/heart.png",
    )
    manager = CommandManager()
    manager.execute(AddStickerClipCommand(track, clip))
    assert len(track.clips) == 1
    manager.undo()
    assert track.clips == []
    manager.redo()
    assert len(track.clips) == 1


def test_update_keyframe_bezier_command_undo() -> None:
    clip = VideoClip(
        clip_id="v1",
        name="video",
        track_id="track_video",
        timeline_start=0.0,
        duration=3.0,
    )
    keyframe = Keyframe(time_seconds=1.0, value=1.0, interpolation="bezier")
    clip.scale_keyframes.append(keyframe)
    manager = CommandManager()
    manager.execute(
        UpdateKeyframeBezierCommand(
            clip=clip,
            property_name="scale_keyframes",
            time_seconds=1.0,
            cp1_dx=0.1,
            cp1_dy=0.2,
            cp2_dx=0.9,
            cp2_dy=0.8,
        )
    )
    assert keyframe.bezier_cp1_dx == pytest.approx(0.1)
    manager.undo()
    assert keyframe.bezier_cp1_dx == pytest.approx(0.42)


def test_project_service_roundtrip_sticker_and_word_timings(tmp_path) -> None:
    project = build_demo_project()
    video_track = next(track for track in project.timeline.tracks if track.track_type == "video")
    text_track = next(track for track in project.timeline.tracks if track.track_type == "text")
    text_clip = next(clip for clip in text_track.clips if isinstance(clip, TextClip))

    video_track.clips.append(
        StickerClip(
            clip_id="sticker_clip",
            name="star",
            track_id=video_track.track_id,
            timeline_start=2.0,
            duration=1.2,
            sticker_path="ui/resources/stickers/star.png",
            scale=0.4,
        )
    )
    text_clip.highlight_color = "#ffcc00"
    text_clip.word_timings = [
        WordTiming(start_seconds=text_clip.timeline_start, end_seconds=text_clip.timeline_start + 0.4, text="Open"),
        WordTiming(start_seconds=text_clip.timeline_start + 0.4, end_seconds=text_clip.timeline_start + 0.8, text="Cut"),
    ]

    save_path = tmp_path / "sprint5_roundtrip.json"
    service = ProjectService()
    service.save_project(project, str(save_path))
    loaded = service.load_project(str(save_path))

    loaded_video_track = next(track for track in loaded.timeline.tracks if track.track_id == video_track.track_id)
    loaded_sticker = next(clip for clip in loaded_video_track.clips if clip.clip_id == "sticker_clip")
    assert isinstance(loaded_sticker, StickerClip)
    assert loaded_sticker.scale == pytest.approx(0.4)

    loaded_text_track = next(track for track in loaded.timeline.tracks if track.track_id == text_track.track_id)
    loaded_text = next(clip for clip in loaded_text_track.clips if clip.clip_id == text_clip.clip_id)
    assert isinstance(loaded_text, TextClip)
    assert loaded_text.highlight_color == "#ffcc00"
    assert len(loaded_text.word_timings) == 2


def test_project_service_roundtrip_video_speed_keyframes(tmp_path) -> None:
    project = build_demo_project()
    video_track = next(track for track in project.timeline.tracks if track.track_type == "video")
    video_clip = next(clip for clip in video_track.clips if isinstance(clip, VideoClip))
    video_clip.playback_speed_keyframes = [
        Keyframe(time_seconds=0.0, value=1.0),
        Keyframe(time_seconds=video_clip.duration * 0.5, value=0.5),
    ]

    save_path = tmp_path / "speed_ramp.json"
    service = ProjectService()
    service.save_project(project, str(save_path))
    loaded = service.load_project(str(save_path))

    loaded_video_track = next(track for track in loaded.timeline.tracks if track.track_id == video_track.track_id)
    loaded_clip = next(clip for clip in loaded_video_track.clips if clip.clip_id == video_clip.clip_id)
    assert isinstance(loaded_clip, VideoClip)
    assert len(loaded_clip.playback_speed_keyframes) == 2
    assert loaded_clip.playback_speed_keyframes[1].value == pytest.approx(0.5)


def test_timeline_controller_add_sticker(qapp: QApplication) -> None:
    _ = qapp
    controller = AppController()
    controller.project_controller.load_demo_project()
    timeline = controller.project_controller.active_project().timeline
    video_track = next(track for track in timeline.tracks if track.track_type == "video")

    clip_id = controller.timeline_controller.add_sticker(
        track_id=video_track.track_id,
        sticker_path="ui/resources/stickers/heart.png",
        timeline_start=1.0,
        duration_seconds=1.5,
    )
    assert clip_id is not None
    created = None
    for track in timeline.tracks:
        created = next((clip for clip in track.clips if clip.clip_id == clip_id), None)
        if created is not None:
            break
    assert isinstance(created, StickerClip)
    assert created.sticker_path.endswith("heart.png")


def test_timeline_controller_set_track_role(qapp: QApplication) -> None:
    _ = qapp
    controller = AppController()
    controller.project_controller.load_demo_project()
    timeline = controller.project_controller.active_project().timeline
    audio_track = next(track for track in timeline.tracks if track.track_type == "audio")

    assert controller.timeline_controller.set_track_role(audio_track.track_id, "voice") is True
    assert audio_track.track_role == "voice"
