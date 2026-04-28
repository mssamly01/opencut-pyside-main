from __future__ import annotations

from app.bootstrap import create_application
from app.controllers.project_controller import ProjectController
from app.domain.clips.video_clip import VideoClip
from app.domain.media_asset import MediaAsset
from app.domain.project import Project
from app.domain.timeline import Timeline
from app.domain.track import Track
from app.infrastructure.video_decoder import VideoDecoder
from app.services.playback_service import PlaybackService
from app.ui.preview.preview_widget import _PreviewCanvas
from app.ui.timeline.clip_item import ClipItem
from app.ui.timeline.playhead_item import PlayheadItem
from app.ui.timeline.timeline_scene import TimelineScene
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPixmap


class _StubTimelineController:
    def set_clip_transform(self, *args, **kwargs) -> bool:
        return True


class _StubSelectionController:
    def selected_clip_ids(self) -> list[str]:
        return []

    def primary_clip_id(self) -> str | None:
        return None


class _StubThumbnailService:
    def get_thumbnail_bytes(self, *args, **kwargs) -> bytes | None:
        return None


class _StubWaveformService:
    def get_peaks(self, *args, **kwargs) -> list[float]:
        return []

    def peek_cached_peaks(self, *args, **kwargs) -> list[float]:
        return []


def _project_with_long_video_clip(duration: float = 3600.0) -> Project:
    clip = VideoClip(
        clip_id="clip-1",
        name="Long Clip",
        track_id="track-1",
        media_id="media-1",
        timeline_start=0.0,
        duration=duration,
        source_start=0.0,
        source_end=duration,
    )
    return Project(
        project_id="project-1",
        name="Long Video",
        width=1920,
        height=1080,
        fps=30.0,
        timeline=Timeline(
            tracks=[
                Track(
                    track_id="track-1",
                    name="Main",
                    track_type="video",
                    clips=[clip],
                )
            ]
        ),
        media_items=[
            MediaAsset(
                media_id="media-1",
                name="long.mp4",
                file_path="/missing/long.mp4",
                media_type="video",
                duration_seconds=duration,
                width=1920,
                height=1080,
            )
        ],
    )


def test_playhead_updates_reuse_graphics_item() -> None:
    create_application(["pytest"])
    scene = TimelineScene(
        project=_project_with_long_video_clip(),
        project_path=None,
        thumbnail_service=_StubThumbnailService(),
        waveform_service=None,
    )

    initial_playhead = scene._playhead_item
    assert isinstance(initial_playhead, PlayheadItem)

    scene.set_playhead_seconds(0.25)
    scene.set_playhead_seconds(0.50)

    assert scene._playhead_item is initial_playhead
    assert scene._playhead_item.scene_x == scene.left_gutter + 0.50 * scene.pixels_per_second


def test_preview_canvas_reuses_scaled_pixmap_for_time_only_repaints() -> None:
    create_application(["pytest"])
    project_controller = ProjectController()
    project_controller.set_active_project(_project_with_long_video_clip())
    canvas = _PreviewCanvas(
        project_controller=project_controller,
        timeline_controller=_StubTimelineController(),
        selection_controller=_StubSelectionController(),
    )
    image = QImage(32, 18, QImage.Format.Format_ARGB32)
    image.fill(QColor("#335577"))
    canvas.resize(640, 360)
    canvas.set_preview_state(image, "frame", 0.0, True)
    project_rect = canvas._project_rect()

    first = canvas._scaled_preview(project_rect)
    canvas.set_preview_state(image, "frame", 1.0, True)
    second = canvas._scaled_preview(project_rect)

    assert second.cacheKey() == first.cacheKey()


def test_waveform_paint_samples_to_visible_width() -> None:
    clip = VideoClip(
        clip_id="clip-1",
        name="Long Clip",
        track_id="track-1",
        timeline_start=0.0,
        duration=3600.0,
        media_id="media-1",
    )
    item = ClipItem(
        clip=clip,
        rect=QRectF(0.0, 0.0, 40.0, 48.0),
        color_hex="#4a78d0",
        waveform_peaks=[0.5] * 4000,
    )

    path = item._waveform_path()

    assert path.elementCount() <= 42


def test_video_clip_paints_preview_tiles_without_child_pixmap_items() -> None:
    thumbnail = QPixmap(16, 9)
    thumbnail.fill(QColor("#224466"))
    clip = VideoClip(
        clip_id="clip-1",
        name="Long Clip",
        track_id="track-1",
        timeline_start=0.0,
        duration=3600.0,
        media_id="media-1",
    )

    item = ClipItem(
        clip=clip,
        rect=QRectF(0.0, 0.0, 160.0, 48.0),
        color_hex="#4a78d0",
        thumbnails=[thumbnail],
    )

    assert len(item._thumbnail_tiles) > 1
    assert item.childItems() == [item._label]


def test_playback_prefetch_frame_count_stays_near_playhead() -> None:
    assert PlaybackService._prefetch_frame_count_for_fps(30.0) == 10
    assert PlaybackService._prefetch_frame_count_for_fps(60.0) == 18


def test_cached_preview_frame_does_not_prefetch_next_window(tmp_path) -> None:
    media = tmp_path / "long.mp4"
    media.write_bytes(b"x")
    project = _project_with_long_video_clip(duration=60.0)
    project.media_items[0].file_path = str(media)
    decoder = VideoDecoder()
    decoder.put_frame(str(media), 30.0, 0, b"cached")
    service = PlaybackService(video_decoder=decoder)

    result = service.get_preview_frame(project, 0.0)

    assert result.frame_bytes == b"cached"
    assert decoder.cache_size() == 1
