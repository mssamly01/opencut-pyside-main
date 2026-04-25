from __future__ import annotations

from app.controllers.app_controller import AppController
from app.domain.clips.audio_clip import AudioClip
from app.domain.clips.base_clip import BaseClip
from app.domain.clips.image_clip import ImageClip
from app.domain.clips.text_clip import TextClip
from app.domain.clips.video_clip import VideoClip
from app.domain.project import Project
from app.ui.inspector.audio_inspector import AudioInspector
from app.ui.inspector.image_inspector import ImageInspector
from app.ui.inspector.project_inspector import ProjectInspector
from app.ui.inspector.text_inspector import TextInspector
from app.ui.inspector.video_inspector import VideoInspector
from PySide6.QtWidgets import QLabel, QStackedWidget, QVBoxLayout, QWidget


class EditorInspectorPage(QWidget):
    """Switches between project editor and clip editors."""

    _PAGE_EMPTY = 0
    _PAGE_PROJECT = 1
    _PAGE_VIDEO = 2
    _PAGE_AUDIO = 3
    _PAGE_IMAGE = 4
    _PAGE_TEXT = 5

    def __init__(self, app_controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app_controller = app_controller

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)

        self._stack = QStackedWidget(self)
        layout.addWidget(self._stack)

        self._empty_label = QLabel("Không có lựa chọn để chỉnh sửa.", self)
        self._stack.insertWidget(self._PAGE_EMPTY, self._empty_label)

        timeline_controller = app_controller.timeline_controller
        self._project_inspector = ProjectInspector(timeline_controller, self)
        self._stack.insertWidget(self._PAGE_PROJECT, self._project_inspector)

        self._video_inspector: VideoInspector | None = None
        self._audio_inspector: AudioInspector | None = None
        self._image_inspector: ImageInspector | None = None
        self._text_inspector: TextInspector | None = None

        app_controller.project_controller.project_changed.connect(self._refresh)
        app_controller.timeline_controller.timeline_edited.connect(self._refresh)
        app_controller.selection_controller.selection_changed.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        project = self._app_controller.project_controller.active_project()
        clip = self._selected_clip(project)
        if clip is not None:
            self._show_clip_editor(clip)
            return
        if project is not None:
            self._project_inspector.set_project(project)
            self._stack.setCurrentIndex(self._PAGE_PROJECT)
            return
        self._stack.setCurrentIndex(self._PAGE_EMPTY)

    def _show_clip_editor(self, clip: BaseClip) -> None:
        timeline_controller = self._app_controller.timeline_controller
        if isinstance(clip, VideoClip):
            if self._video_inspector is None:
                self._video_inspector = VideoInspector(timeline_controller, clip, self)
                self._stack.insertWidget(self._PAGE_VIDEO, self._video_inspector)
            else:
                self._video_inspector.set_clip(clip)
            self._stack.setCurrentIndex(self._PAGE_VIDEO)
            return

        if isinstance(clip, AudioClip):
            if self._audio_inspector is None:
                self._audio_inspector = AudioInspector(timeline_controller, clip, self)
                self._stack.insertWidget(self._PAGE_AUDIO, self._audio_inspector)
            else:
                self._audio_inspector.set_clip(clip)
            self._stack.setCurrentIndex(self._PAGE_AUDIO)
            return

        if isinstance(clip, ImageClip):
            if self._image_inspector is None:
                self._image_inspector = ImageInspector(timeline_controller, clip, self)
                self._stack.insertWidget(self._PAGE_IMAGE, self._image_inspector)
            else:
                self._image_inspector.set_clip(clip)
            self._stack.setCurrentIndex(self._PAGE_IMAGE)
            return

        if isinstance(clip, TextClip):
            if self._text_inspector is None:
                self._text_inspector = TextInspector(timeline_controller, clip, self)
                self._stack.insertWidget(self._PAGE_TEXT, self._text_inspector)
            else:
                self._text_inspector.set_clip(clip)
            self._stack.setCurrentIndex(self._PAGE_TEXT)
            return

        self._stack.setCurrentIndex(self._PAGE_EMPTY)

    def _selected_clip(self, project: Project | None) -> BaseClip | None:
        if project is None:
            return None
        clip_id = self._app_controller.selection_controller.selected_clip_id()
        if clip_id is None:
            return None
        for track in project.timeline.tracks:
            for clip in track.clips:
                if clip.clip_id == clip_id:
                    return clip
        return None
