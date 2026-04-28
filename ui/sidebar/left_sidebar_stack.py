from __future__ import annotations

from app.controllers.app_controller import AppController
from app.ui.captions_panel import CaptionsPanel
from app.ui.media_panel.media_panel import MediaPanel
from app.ui.sidebar.audio_panel import AudioPanel
from app.ui.sidebar.effects_panel import EffectsPanel
from app.ui.sidebar.left_rail import RAIL_CATEGORIES
from app.ui.sidebar.rail_library_panel import RailLibraryPanel
from app.ui.sidebar.transitions_panel import TransitionsPanel
from PySide6.QtWidgets import QStackedWidget


class LeftSidebarStack(QStackedWidget):
    """Stack of sidebar panels, keyed by LeftRail category."""

    def __init__(self, app_controller: AppController, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("leftSidebarStack")
        self.media_content_panel = MediaPanel(
            app_controller.project_controller,
            self,
            thumbnail_service=app_controller.thumbnail_service,
            timeline_controller=app_controller.timeline_controller,
            embedded=True,
        )
        self.audio_content_panel = AudioPanel(
            app_controller.project_controller,
            waveform_loader=app_controller.waveform_loader,
            timeline_controller=app_controller.timeline_controller,
            parent=self,
            embedded=True,
        )
        self.media_panel = RailLibraryPanel(self.media_content_panel, self)
        self.audio_panel = RailLibraryPanel(self.audio_content_panel, self)
        self.effects_panel = EffectsPanel(app_controller, self)
        self.transitions_panel = TransitionsPanel(self)
        self.captions_panel = CaptionsPanel(app_controller, self)
        self._key_to_index: dict[str, int] = {}
        self._panel_by_key = {
            "media": self.media_panel,
            "audio": self.audio_panel,
            "effects": self.effects_panel,
            "transitions": self.transitions_panel,
            "captions": self.captions_panel,
        }

        for key, _label, _icon_name in RAIL_CATEGORIES:
            panel = self._panel_by_key[key]
            index = self.addWidget(panel)
            self._key_to_index[key] = index

        self.show_category(RAIL_CATEGORIES[0][0])

    def show_category(self, key: str) -> None:
        index = self._key_to_index.get(key)
        if index is None:
            return
        self.setCurrentIndex(index)
