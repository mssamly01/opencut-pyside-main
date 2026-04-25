from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.clips.audio_clip import AudioClip
from app.domain.clips.text_clip import TextClip
from app.domain.clips.video_clip import VideoClip
from app.domain.media_asset import MediaAsset
from app.domain.timeline import Timeline
from app.domain.track import Track


@dataclass(slots=True)
class Project:
    project_id: str
    name: str
    width: int
    height: int
    fps: float
    timeline: Timeline
    media_items: list[MediaAsset] = field(default_factory=list)
    version: str = "0.1.0"


def build_empty_project() -> Project:
    """Create an empty project scaffold with Text/Main/Media tracks."""
    text_track = Track(
        track_id="track_text_1",
        name="Text 1",
        track_type="text",
        clips=[],
    )
    video_track = Track(
        track_id="track_video_1",
        name="Main",
        track_type="video",
        clips=[],
    )
    media_track = Track(
        track_id="track_media_1",
        name="Media",
        track_type="audio",
        clips=[],
    )
    return Project(
        project_id="proj_untitled",
        name="Untitled",
        width=1920,
        height=1080,
        fps=30.0,
        timeline=Timeline(tracks=[text_track, video_track, media_track]),
        media_items=[],
    )


def build_demo_project() -> Project:
    text_track = Track(
        track_id="track_text_1",
        name="Text 1",
        track_type="text",
        clips=[
            TextClip(
                clip_id="clip_t1_1",
                name="Logo Bumper",
                track_id="track_text_1",
                timeline_start=1.5,
                duration=2.3,
                content="OpenCut",
                font_size=64,
                color="#ffffff",
                position_x=0.5,
                position_y=0.5,
            ),
            TextClip(
                clip_id="clip_t1_2",
                name="Lower Third",
                track_id="track_text_1",
                timeline_start=6.2,
                duration=2.0,
                content="Presenter Name",
                font_size=36,
                color="#ffd9a3",
                position_x=0.1,
                position_y=0.85,
            ),
        ],
    )

    video_track = Track(
        track_id="track_video_1",
        name="Main",
        track_type="video",
        clips=[
            VideoClip(
                clip_id="clip_v1_1",
                name="Intro Shot",
                track_id="track_video_1",
                media_id="media_intro",
                timeline_start=0.0,
                duration=3.8,
                source_start=0.0,
                source_end=3.8,
            ),
            VideoClip(
                clip_id="clip_v1_2",
                name="City B-roll",
                track_id="track_video_1",
                media_id="media_city",
                timeline_start=4.1,
                duration=5.4,
                source_start=0.0,
                source_end=5.4,
            ),
        ],
    )

    media_track = Track(
        track_id="track_media_1",
        name="Media",
        track_type="audio",
        clips=[
            AudioClip(
                clip_id="clip_a1_1",
                name="Music Bed",
                track_id="track_media_1",
                media_id="media_music",
                timeline_start=0.0,
                duration=10.5,
                source_start=0.0,
                source_end=10.5,
            ),
            AudioClip(
                clip_id="clip_a1_2",
                name="SFX Hit",
                track_id="track_media_1",
                media_id="media_sfx",
                timeline_start=3.2,
                duration=0.8,
                source_start=0.0,
                source_end=0.8,
            ),
        ],
    )

    return Project(
        project_id="proj_demo_001",
        name="Demo Timeline Project",
        width=1920,
        height=1080,
        fps=30.0,
        timeline=Timeline(tracks=[text_track, video_track, media_track]),
        media_items=[
            MediaAsset(
                media_id="media_intro",
                name="intro",
                file_path="demo/intro.mp4",
                media_type="video",
                duration_seconds=3.8,
            ),
            MediaAsset(
                media_id="media_city",
                name="city_broll",
                file_path="demo/city_broll.mp4",
                media_type="video",
                duration_seconds=5.4,
            ),
            MediaAsset(
                media_id="media_music",
                name="music_bed",
                file_path="demo/music_bed.wav",
                media_type="audio",
                duration_seconds=10.5,
            ),
            MediaAsset(
                media_id="media_sfx",
                name="sfx_hit",
                file_path="demo/sfx_hit.wav",
                media_type="audio",
                duration_seconds=0.8,
            ),
        ],
    )
