from __future__ import annotations

from app.controllers.app_controller import AppController
from app.domain.clips.audio_clip import AudioClip
from app.domain.clips.image_clip import ImageClip
from app.domain.clips.sticker_clip import StickerClip
from app.domain.clips.text_clip import TextClip
from app.domain.clips.video_clip import VideoClip
from app.ui.inspector.audio_inspector import AudioInspector
from app.ui.inspector.clip_inspector_tabs import ClipInspectorTabs
from app.ui.inspector.image_inspector import ImageInspector
from app.ui.inspector.project_inspector import ProjectInspector
from app.ui.inspector.text_inspector import TextInspector
from app.ui.inspector.video_inspector import VideoInspector
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QTabWidget, QVBoxLayout, QWidget


class InspectorPanel(QWidget):
    """Tabbed Project/Clip inspector to keep the right panel compact."""

    def __init__(self, app_controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app_controller = app_controller
        self._project_inspector = ProjectInspector(self._app_controller.timeline_controller, self)
        self._clip_placeholder = QLabel("Select a clip to edit", self)
        self._clip_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._clip_placeholder.setStyleSheet("color: #7a8794; padding: 24px;")
        self._clip_container = QWidget(self)
        self._clip_container_layout = QVBoxLayout(self._clip_container)
        self._clip_container_layout.setContentsMargins(0, 0, 0, 0)
        self._clip_container_layout.setSpacing(0)
        self._clip_widget: QWidget | None = None
        self._clip_widget_type: type[QWidget] | None = None

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self._tabs = QTabWidget(self)
        self._tabs.setTabPosition(QTabWidget.TabPosition.North)
        self._tabs.setDocumentMode(True)
        outer_layout.addWidget(self._tabs)

        project_tab = QWidget(self._tabs)
        project_layout = QVBoxLayout(project_tab)
        project_layout.setContentsMargins(8, 8, 8, 8)
        project_layout.setSpacing(8)
        project_layout.addWidget(self._project_inspector)
        project_layout.addStretch()
        self._tabs.addTab(project_tab, "Project")

        clip_tab = QWidget(self._tabs)
        clip_layout = QVBoxLayout(clip_tab)
        clip_layout.setContentsMargins(0, 0, 0, 0)
        clip_layout.setSpacing(0)

        scroll = QScrollArea(clip_tab)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        scroll_content = QWidget(scroll)
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(8, 8, 8, 8)
        scroll_layout.setSpacing(8)
        self._clip_container_layout.addWidget(self._clip_placeholder)
        scroll_layout.addWidget(self._clip_container)
        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)

        clip_layout.addWidget(scroll)
        self._tabs.addTab(clip_tab, "Clip")

        self._app_controller.project_controller.project_changed.connect(self._refresh_project_inspector)
        self._app_controller.timeline_controller.timeline_edited.connect(self._refresh_from_state)
        self._app_controller.selection_controller.selection_changed.connect(self._on_selection_changed)
        self._refresh_from_state()

    def _on_selection_changed(self) -> None:
        self._refresh_clip_inspector()
        if self._selected_clip(self._app_controller.project_controller.active_project()) is not None:
            self._tabs.setCurrentIndex(1)

    def _refresh_from_state(self) -> None:
        self._refresh_project_inspector()
        self._refresh_clip_inspector()

    def _refresh_project_inspector(self) -> None:
        self._project_inspector.set_project(self._app_controller.project_controller.active_project())

    def _refresh_clip_inspector(self) -> None:
        project = self._app_controller.project_controller.active_project()
        clip = self._selected_clip(project)

        if clip is None:
            self._swap_clip_widget(None)
            return

        widget_type = self._widget_type_for_clip(clip)
        if self._clip_widget is not None and self._clip_widget_type is widget_type:
            setter = getattr(self._clip_widget, "set_clip", None)
            if callable(setter):
                setter(clip)
                return

        basic_widget = widget_type(self._app_controller.timeline_controller, clip, self)
        tabs = ClipInspectorTabs(
            self._app_controller.timeline_controller,
            self._app_controller.playback_controller,
            basic_widget,
            clip,
            self,
        )
        tabs._clip_basic_type = widget_type  # type: ignore[attr-defined]
        self._swap_clip_widget(tabs, widget_type=widget_type)

    def _swap_clip_widget(self, widget: QWidget | None, widget_type: type[QWidget] | None = None) -> None:
        while self._clip_container_layout.count():
            item = self._clip_container_layout.takeAt(0)
            child = item.widget()
            if child is None:
                continue
            if child is not self._clip_placeholder:
                child.setParent(None)
                child.deleteLater()

        self._clip_widget = None
        self._clip_widget_type = None

        if widget is None:
            self._clip_placeholder.show()
            self._clip_container_layout.addWidget(self._clip_placeholder)
            return

        self._clip_placeholder.hide()
        self._clip_container_layout.addWidget(widget)
        self._clip_widget = widget
        self._clip_widget_type = widget_type if widget_type is not None else type(widget)

    def _selected_clip(self, project) -> object | None:
        if project is None:
            return None

        selected_clip_id = self._app_controller.selection_controller.selected_clip_id()
        if selected_clip_id is None:
            return None

        for track in project.timeline.tracks:
            for clip in track.clips:
                if clip.clip_id == selected_clip_id:
                    return clip
        return None

    @staticmethod
    def _widget_type_for_clip(clip: object) -> type[QWidget]:
        if isinstance(clip, VideoClip):
            return VideoInspector
        if isinstance(clip, AudioClip):
            return AudioInspector
        if isinstance(clip, (ImageClip, StickerClip)):
            return ImageInspector
        if isinstance(clip, TextClip):
            return TextInspector
        return TextInspector
