from __future__ import annotations

from app.controllers.app_controller import AppController
from app.ui.inspector.inspector_panel import InspectorPanel
from app.ui.media_panel.media_panel import MediaPanel
from app.ui.preview.preview_widget import PreviewWidget
from app.ui.sidebar.left_rail import LeftRail
from app.ui.sidebar.left_sidebar_stack import LeftSidebarStack
from app.ui.shared.icons import build_icon
from app.ui.timeline.timeline_toolbar import TimelineToolbar
from app.ui.timeline.timeline_view import TimelineView
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QSplitter, QToolButton, QVBoxLayout, QWidget


class AppShell(QWidget):
    """Main 4-panel editor shell for the MVP skeleton."""

    def __init__(self, app_controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app_controller = app_controller
        self._rail_scroll: QScrollArea | None = None
        self._rail_left_button: QToolButton | None = None
        self._rail_right_button: QToolButton | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Sprint 9 top area: LeftRail | LeftSidebarStack | Preview | Inspector
        self.media_panel = MediaPanel(
            self._app_controller.project_controller,
            self,
            thumbnail_service=self._app_controller.thumbnail_service,
        )
        self.preview_widget = PreviewWidget(
            playback_controller=self._app_controller.playback_controller,
            project_controller=self._app_controller.project_controller,
            timeline_controller=self._app_controller.timeline_controller,
            selection_controller=self._app_controller.selection_controller,
            parent=self,
        )
        self.inspector_panel = InspectorPanel(self._app_controller, self)

        # Sprint 9-fix: left sidebar is a single vertical column [rail / stack].
        left_sidebar = QWidget(self)
        left_sidebar_layout = QVBoxLayout(left_sidebar)
        left_sidebar_layout.setContentsMargins(0, 0, 0, 0)
        left_sidebar_layout.setSpacing(0)

        self.left_rail = LeftRail(self)
        self.left_sidebar_stack = LeftSidebarStack(self.media_panel, self)
        self.left_rail.category_selected.connect(self.left_sidebar_stack.show_category)

        rail_strip = QWidget(left_sidebar)
        rail_strip_layout = QHBoxLayout(rail_strip)
        rail_strip_layout.setContentsMargins(0, 0, 0, 0)
        rail_strip_layout.setSpacing(0)

        self._rail_left_button = QToolButton(rail_strip)
        self._rail_left_button.setIcon(build_icon("step-back"))
        self._rail_left_button.setIconSize(QSize(18, 18))
        self._rail_left_button.setAutoRaise(True)
        self._rail_left_button.setFixedSize(22, 28)
        self._rail_left_button.setStyleSheet(
            "QToolButton { border: none; border-radius: 6px; padding: 0px; }"
            "QToolButton:hover { background: rgba(255,255,255,0.12); }"
        )
        self._rail_left_button.clicked.connect(lambda: self._scroll_rail(-120))

        self._rail_right_button = QToolButton(rail_strip)
        self._rail_right_button.setIcon(build_icon("step-forward"))
        self._rail_right_button.setIconSize(QSize(18, 18))
        self._rail_right_button.setAutoRaise(True)
        self._rail_right_button.setFixedSize(22, 28)
        self._rail_right_button.setStyleSheet(
            "QToolButton { border: none; border-radius: 6px; padding: 0px; }"
            "QToolButton:hover { background: rgba(255,255,255,0.12); }"
        )
        self._rail_right_button.clicked.connect(lambda: self._scroll_rail(120))

        self._rail_scroll = QScrollArea(rail_strip)
        self._rail_scroll.setObjectName("leftRailScroll")
        self._rail_scroll.setWidget(self.left_rail)
        self._rail_scroll.setWidgetResizable(False)
        self._rail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._rail_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._rail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._rail_scroll.setFixedHeight(56)

        rail_bar = self._rail_scroll.horizontalScrollBar()
        rail_bar.valueChanged.connect(lambda _value: self._update_rail_arrow_state())
        rail_bar.rangeChanged.connect(lambda _min, _max: self._update_rail_arrow_state())

        rail_strip_layout.addWidget(self._rail_left_button, 0, Qt.AlignmentFlag.AlignVCenter)
        rail_strip_layout.addWidget(self._rail_scroll, 1)
        rail_strip_layout.addWidget(self._rail_right_button, 0, Qt.AlignmentFlag.AlignVCenter)
        left_sidebar_layout.addWidget(rail_strip)
        left_sidebar_layout.addWidget(self.left_sidebar_stack, stretch=1)

        top_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        top_splitter.addWidget(left_sidebar)
        top_splitter.addWidget(self.preview_widget)
        top_splitter.addWidget(self.inspector_panel)
        top_splitter.setStretchFactor(0, 2)
        top_splitter.setStretchFactor(1, 6)
        top_splitter.setStretchFactor(2, 3)
        top_splitter.setSizes([260, 720, 320])
        left_sidebar.setMinimumWidth(220)
        self.inspector_panel.setMinimumWidth(240)

        # Root: [Top area]
        #       -----------
        #       [Timeline]
        root_splitter = QSplitter(Qt.Orientation.Vertical, self)
        root_splitter.addWidget(top_splitter)

        self.timeline_view = TimelineView(
            self._app_controller.timeline_controller,
            self._app_controller.playback_controller,
            self._app_controller.selection_controller,
            self._app_controller.thumbnail_service,
            self._app_controller.waveform_service,
            self,
        )
        timeline_container = QWidget(self)
        timeline_layout = QVBoxLayout(timeline_container)
        timeline_layout.setContentsMargins(0, 0, 0, 0)
        timeline_layout.setSpacing(0)
        timeline_layout.addWidget(
            TimelineToolbar(
                timeline_controller=self._app_controller.timeline_controller,
                timeline_view=self.timeline_view,
                parent=timeline_container,
            )
        )
        timeline_layout.addWidget(self.timeline_view)
        root_splitter.addWidget(timeline_container)

        # Give more space to the top area by default
        root_splitter.setStretchFactor(0, 4)
        root_splitter.setStretchFactor(1, 2)

        layout.addWidget(root_splitter)
        self._update_rail_arrow_state()

    def _scroll_rail(self, delta: int) -> None:
        if self._rail_scroll is None:
            return
        scroll_bar = self._rail_scroll.horizontalScrollBar()
        scroll_bar.setValue(scroll_bar.value() + delta)
        self._update_rail_arrow_state()

    def _update_rail_arrow_state(self) -> None:
        if self._rail_scroll is None or self._rail_left_button is None or self._rail_right_button is None:
            return
        scroll_bar = self._rail_scroll.horizontalScrollBar()
        has_overflow = scroll_bar.maximum() > scroll_bar.minimum()
        if not has_overflow:
            self._rail_left_button.setVisible(False)
            self._rail_right_button.setVisible(False)
            return
        at_left = scroll_bar.value() <= scroll_bar.minimum()
        at_right = scroll_bar.value() >= scroll_bar.maximum()
        self._rail_left_button.setVisible(not at_left)
        self._rail_right_button.setVisible(not at_right)
