from __future__ import annotations

from app.controllers.playback_controller import PlaybackController
from app.controllers.timeline_controller import TimelineController
from app.domain.clips.base_clip import BaseClip
from app.ui.inspector.adjust_inspector import AdjustInspector
from app.ui.inspector.animation_inspector import AnimationInspector
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget


class ClipInspectorTabs(QWidget):
    """Tabbed container for clip inspector sections."""

    def __init__(
        self,
        timeline_controller: TimelineController,
        playback_controller: PlaybackController,
        basic_widget: QWidget,
        clip: BaseClip,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._timeline_controller = timeline_controller
        self._playback_controller = playback_controller
        self._basic_widget = basic_widget
        self._clip = clip

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._tabs = QTabWidget(self)
        self._tabs.setTabPosition(QTabWidget.TabPosition.North)
        self._tabs.setDocumentMode(True)

        self._tabs.addTab(basic_widget, "Basic")

        self._adjust = AdjustInspector(timeline_controller, clip, self)
        self._tabs.addTab(self._adjust, "Adjust")

        self._animation = AnimationInspector(
            timeline_controller=timeline_controller,
            playback_controller=playback_controller,
            clip=clip,
            parent=self,
        )
        self._tabs.addTab(self._animation, "Animation")

        root.addWidget(self._tabs)

    def set_clip(self, clip: BaseClip) -> None:
        self._clip = clip
        basic_setter = getattr(self._basic_widget, "set_clip", None)
        if callable(basic_setter):
            basic_setter(clip)
        self._adjust.set_clip(clip)
        self._animation.set_clip(clip)
