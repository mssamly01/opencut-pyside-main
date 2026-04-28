from __future__ import annotations

from app.controllers.app_controller import AppController
from app.ui.inspector.inspector_panel import InspectorPanel
from app.ui.preview.preview_widget import PreviewWidget
from app.ui.shared.icons import build_icon
from app.ui.sidebar.left_rail import LeftRail
from app.ui.sidebar.left_sidebar_stack import LeftSidebarStack
from app.ui.timeline.timeline_toolbar import TimelineToolbar
from app.ui.timeline.timeline_view import TimelineView
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QLabel, QFrame, QHBoxLayout, QScrollArea, QSplitter, QToolButton, QVBoxLayout, QWidget


class AppShell(QWidget):
    """Main 4-panel editor shell for the MVP skeleton."""

    _TOP_REGION_HEADER_HEIGHT = 56
    _LEFT_RAIL_DETAIL_INSET = 8
    _LEFT_RAIL_DETAIL_GAP = 3

    def __init__(self, app_controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app_controller = app_controller
        self._rail_scroll: QScrollArea | None = None
        self._rail_left_button: QToolButton | None = None
        self._rail_right_button: QToolButton | None = None

        layout = QVBoxLayout(self)
        # Keep a global inset so the whole workspace cluster (top 3 panels +
        # timeline) stays away from the app window edge.
        layout.setContentsMargins(8, 8, 8, 8)

        # Sprint 9 top area: LeftRail | LeftSidebarStack | Preview | Inspector
        self.preview_widget = PreviewWidget(
            playback_controller=self._app_controller.playback_controller,
            project_controller=self._app_controller.project_controller,
            timeline_controller=self._app_controller.timeline_controller,
            selection_controller=self._app_controller.selection_controller,
            parent=self,
        )
        self.preview_widget.setObjectName("workspace_preview_region")
        self.inspector_panel = InspectorPanel(self._app_controller, self)
        self.inspector_panel.setObjectName("workspace_inspector_region")

        # Sprint 9-fix: left sidebar is a single vertical column [rail / stack].
        left_sidebar = QWidget(self)
        left_sidebar.setObjectName("left_sidebar")
        left_sidebar_layout = QVBoxLayout(left_sidebar)
        left_sidebar_layout.setContentsMargins(0, 0, 0, 0)
        left_sidebar_layout.setSpacing(0)

        self.left_rail = LeftRail(self)
        self.left_sidebar_stack = LeftSidebarStack(self._app_controller, self)
        self.media_panel = self.left_sidebar_stack.media_panel
        self.left_rail.category_selected.connect(self.left_sidebar_stack.show_category)

        rail_strip = QWidget(left_sidebar)
        rail_strip.setObjectName("left_sidebar_rail_region")
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
        self._rail_scroll.viewport().setObjectName("leftRailViewport")
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

        body_region = QWidget(left_sidebar)
        body_region.setObjectName("left_sidebar_body_region")
        body_layout = QVBoxLayout(body_region)
        body_layout.setContentsMargins(
            0,
            0,
            self._LEFT_RAIL_DETAIL_INSET,
            0,
        )
        body_layout.setSpacing(0)
        body_layout.addWidget(self.left_sidebar_stack, 1)

        rail_detail_gap = QWidget(left_sidebar)
        rail_detail_gap.setObjectName("left_sidebar_rail_detail_gap")
        rail_detail_gap.setFixedHeight(self._LEFT_RAIL_DETAIL_GAP)

        left_sidebar_layout.addWidget(rail_strip)
        left_sidebar_layout.addWidget(rail_detail_gap)
        left_sidebar_layout.addWidget(body_region, stretch=1)

        left_region_container = QWidget(self)
        left_region_container.setObjectName("workspace_left_region_container")
        left_region_layout = QVBoxLayout(left_region_container)
        left_region_layout.setContentsMargins(0, 6, 3, 4)
        left_region_layout.setSpacing(0)
        left_region_layout.addWidget(left_sidebar, 1)

        top_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        top_splitter.setObjectName("workspace_top_splitter")
        top_splitter.setHandleWidth(6)

        center_region_container = QWidget(self)
        center_region_container.setObjectName("workspace_center_region_container")
        center_region_layout = QVBoxLayout(center_region_container)
        center_region_layout.setContentsMargins(3, 6, 3, 4)
        center_region_layout.setSpacing(0)
        center_region_layout.addWidget(
            self._build_region_header(self.tr("Xem trước"), parent=center_region_container)
        )
        center_gap = QWidget(center_region_container)
        center_gap.setFixedHeight(self._LEFT_RAIL_DETAIL_GAP)
        center_region_layout.addWidget(center_gap)
        center_region_layout.addWidget(self.preview_widget, 1)

        right_region_container = QWidget(self)
        right_region_container.setObjectName("workspace_right_region_container")
        right_region_layout = QVBoxLayout(right_region_container)
        right_region_layout.setContentsMargins(3, 6, 0, 4)
        right_region_layout.setSpacing(0)
        right_region_layout.addWidget(
            self._build_region_header(self.tr("Chi tiết"), accent=True, parent=right_region_container)
        )
        right_gap = QWidget(right_region_container)
        right_gap.setFixedHeight(self._LEFT_RAIL_DETAIL_GAP)
        right_region_layout.addWidget(right_gap)
        right_region_layout.addWidget(self.inspector_panel, 1)

        top_splitter.addWidget(left_region_container)
        top_splitter.addWidget(center_region_container)
        top_splitter.addWidget(right_region_container)
        top_splitter.setStretchFactor(0, 2)
        top_splitter.setStretchFactor(1, 6)
        top_splitter.setStretchFactor(2, 3)
        top_splitter.setSizes([420, 860, 420])
        left_region_container.setMinimumWidth(320)
        right_region_container.setMinimumWidth(300)

        # Root: [Top area]
        #       -----------
        #       [Timeline]
        root_splitter = QSplitter(Qt.Orientation.Vertical, self)
        root_splitter.setObjectName("workspace_root_splitter")
        root_splitter.setHandleWidth(6)
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
        timeline_container.setObjectName("workspace_timeline_region")
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

    def _build_region_header(
        self,
        title: str,
        *,
        accent: bool = False,
        parent: QWidget | None = None,
    ) -> QWidget:
        header = QWidget(parent or self)
        header.setObjectName("workspace_region_header")
        header.setFixedHeight(self._TOP_REGION_HEADER_HEIGHT)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 0, 14, 0)
        header_layout.setSpacing(0)

        title_label = QLabel(title, header)
        title_label.setObjectName("workspace_region_header_title")
        title_label.setProperty("accent", bool(accent))
        header_layout.addWidget(
            title_label,
            0,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
        )
        header_layout.addStretch(1)
        return header

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
