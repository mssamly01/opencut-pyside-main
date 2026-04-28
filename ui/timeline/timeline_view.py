from __future__ import annotations

from time import monotonic_ns

from app.controllers.playback_controller import PlaybackController
from app.controllers.selection_controller import SelectionController
from app.controllers.timeline_controller import TimelineController
from app.services.thumbnail_service import ThumbnailService
from app.services.waveform_service import WaveformService
from app.ui.effects_drawer import TRANSITION_MIME_TYPE
from app.ui.media_panel.media_item_widget import media_id_from_mime_data
from app.ui.timeline.clip_item import ClipItem
from app.ui.timeline.timeline_scene import TimelineScene
from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QCursor,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QFrame, QGraphicsItem, QGraphicsView, QInputDialog, QMenu, QWidget


class TimelineView(QGraphicsView):
    _HOVER_SCRUB_THROTTLE_MS = 40

    def __init__(
        self,
        timeline_controller: TimelineController,
        playback_controller: PlaybackController,
        selection_controller: SelectionController,
        thumbnail_service: ThumbnailService,
        waveform_service: WaveformService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._timeline_controller = timeline_controller
        self._playback_controller = playback_controller
        self._selection_controller = selection_controller
        self._timeline_scene = TimelineScene(
            project=self._timeline_controller.active_project(),
            project_path=self._timeline_controller.active_project_path(),
            thumbnail_service=thumbnail_service,
            waveform_service=waveform_service,
            parent=self,
        )
        self.setScene(self._timeline_scene)
        self.setMinimumHeight(220)

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        self.horizontalScrollBar().valueChanged.connect(self._on_scroll_changed)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)

        self._timeline_controller.timeline_changed.connect(self._refresh_from_controller)
        self._playback_controller.current_time_changed.connect(self._on_playback_time_changed)
        self._selection_controller.selection_changed.connect(self._refresh_selection_from_controller)

        self._timeline_scene.set_selected_clip_ids(self._selection_controller.selected_clip_ids())
        self._timeline_scene.set_playhead_seconds(self._playback_controller.current_time())

        self._trim_handle_pixels = 8.0
        self._min_clip_pixels = 16.0
        self._snap_threshold_pixels = 10.0

        self._timeline_controller.configure_timeline_metrics(
            pixels_per_second=self._timeline_scene.pixels_per_second,
            snap_threshold_pixels=self._snap_threshold_pixels,
            playhead_seconds=self._playback_controller.current_time(),
            minimum_clip_duration_seconds=self._min_clip_pixels / self._timeline_scene.pixels_per_second,
        )
        self._timeline_controller.set_playhead_seconds(self._playback_controller.current_time())

        self._drag_mode: str | None = None
        self._drag_clip_id: str | None = None
        self._drag_start_scene_x = 0.0
        self._drag_item_start_x = 0.0
        self._drag_item_start_width = 0.0
        self._drag_clip_start_time = 0.0
        self._drag_clip_start_duration = 0.0
        self._pending_fade_seconds: float | None = None
        self._is_dragging = False
        self._is_scrubbing = False
        self._is_playhead_dragging = False
        self._playhead_sticky_to_mouse = True

        self._header_resize_track_id: str | None = None
        self._header_resize_start_scene_y = 0.0
        self._header_resize_start_height = 0.0
        self._header_resize_pending_height = 0.0
        self._marquee_pending = False
        self._marquee_active = False
        self._marquee_start_scene = (0.0, 0.0)
        self._marquee_current_scene = (0.0, 0.0)
        self._marquee_initial_selection: list[str] = []

        # Hover-scrub: when enabled, moving the mouse over the ruler / clip
        # area seeks the playhead without requiring a click. Throttled to
        # _HOVER_SCRUB_THROTTLE_MS to avoid swamping the decoder while the
        # user sweeps the cursor across the timeline.
        self._hover_scrub_enabled = False
        self._hover_scrub_last_seek_ms = 0
        self.viewport().setMouseTracking(True)

    def _on_scroll_changed(self, _value: int) -> None:
        self._timeline_scene.invalidate(
            self._timeline_scene.sceneRect(),
            self._timeline_scene.SceneLayer.ForegroundLayer,
        )

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasFormat(TRANSITION_MIME_TYPE):
            event.acceptProposedAction()
            return
        media_id = media_id_from_mime_data(event.mimeData())
        if media_id is not None:
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if event.mimeData().hasFormat(TRANSITION_MIME_TYPE):
            event.acceptProposedAction()
            return
        media_id = media_id_from_mime_data(event.mimeData())
        if media_id is not None:
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        if event.mimeData().hasFormat(TRANSITION_MIME_TYPE):
            transition_type = bytes(event.mimeData().data(TRANSITION_MIME_TYPE)).decode(
                "utf-8",
                errors="ignore",
            ).strip()
            if not transition_type:
                event.ignore()
                return

            scene_pos = self.mapToScene(event.position().toPoint())
            pair = self._find_clip_pair_near_scene_x(
                scene_x=scene_pos.x(),
                scene_y=scene_pos.y(),
                edge_tolerance_px=30.0,
            )
            if pair is None:
                event.ignore()
                return

            track_id, clip_a_id, clip_b_id = pair
            if self._timeline_controller.add_transition(
                track_id=track_id,
                from_clip_id=clip_a_id,
                to_clip_id=clip_b_id,
                transition_type=transition_type,
            ):
                event.acceptProposedAction()
            else:
                event.ignore()
            return

        media_id = media_id_from_mime_data(event.mimeData())
        if media_id is None:
            super().dropEvent(event)
            return

        scene_pos = self.mapToScene(event.position().toPoint())
        timeline_start = max(0.0, (scene_pos.x() - self._timeline_scene.left_gutter) / self._timeline_scene.pixels_per_second)
        rounded_timeline_start = round(timeline_start, 3)
        target_track_id = self._timeline_scene.track_id_at_scene_y(scene_pos.y())
        max_track_bottom = max(
            (layout.bottom for layout in self._timeline_scene.track_layouts),
            default=self._timeline_scene.ruler_height,
        )
        force_new_track = target_track_id is None and scene_pos.y() > max_track_bottom

        try:
            created_clip_id = self._timeline_controller.add_clip_from_media(
                media_id=media_id,
                timeline_start=rounded_timeline_start,
                preferred_track_id=target_track_id,
                force_new_track=force_new_track,
            )
        except ValueError:
            created_clip_id = None

        if created_clip_id is None:
            event.ignore()
            return

        self._selection_controller.select_clip(created_clip_id)
        event.acceptProposedAction()

    def zoom_in(self) -> None:
        self._perform_zoom(self._timeline_controller.zoom_in)

    def zoom_out(self) -> None:
        self._perform_zoom(self._timeline_controller.zoom_out)

    def fit_timeline(self) -> None:
        project = self._timeline_controller.active_project()
        if project is None:
            return
        duration = max(1.0, project.timeline.total_duration())
        usable_width = max(
            240.0,
            self.viewport().width() - self._timeline_scene.left_gutter - self._timeline_scene.right_padding - 24.0,
        )
        self._timeline_controller.set_pixels_per_second(usable_width / duration)
        self._set_horizontal_scroll(0.0)

    def playhead_sticky_to_mouse_enabled(self) -> bool:
        return self._playhead_sticky_to_mouse

    def set_playhead_sticky_to_mouse_enabled(self, enabled: bool) -> None:
        self._playhead_sticky_to_mouse = bool(enabled)

    def hover_scrub_enabled(self) -> bool:
        return self._hover_scrub_enabled

    def set_hover_scrub_enabled(self, enabled: bool) -> None:
        self._hover_scrub_enabled = bool(enabled)
        # Reset the throttle clock so the next hover seeks immediately
        # instead of being deferred by a stale timestamp from before the
        # toggle.
        self._hover_scrub_last_seek_ms = 0

    def _perform_zoom(self, zoom_fn, anchor_scene_x: float | None = None) -> None:
        if anchor_scene_x is None:
            viewport_rect = self.viewport().rect()
            anchor_scene_x = self.mapToScene(viewport_rect.center()).x()

        anchor_view_x = self.mapFromScene(anchor_scene_x, 0).x()
        old_pps = self._timeline_controller.pixels_per_second
        anchor_time = (anchor_scene_x - self._timeline_scene.left_gutter) / old_pps
        zoom_fn()
        new_pps = self._timeline_controller.pixels_per_second
        new_scene_x = anchor_time * new_pps + self._timeline_scene.left_gutter
        self._set_horizontal_scroll(new_scene_x - anchor_view_x)

    def _set_horizontal_scroll(self, value: float) -> None:
        bar = self.horizontalScrollBar()
        clamped_value = max(bar.minimum(), min(int(value), bar.maximum()))
        bar.setValue(clamped_value)

    def _refresh_from_controller(self) -> None:
        viewport_width = self.viewport().width()
        viewport_height = self.viewport().height()

        self._timeline_scene.pixels_per_second = self._timeline_controller.pixels_per_second
        self._timeline_scene.set_project(
            self._timeline_controller.active_project(),
            project_path=self._timeline_controller.active_project_path(),
            min_width=viewport_width,
            min_height=viewport_height,
        )
        self._timeline_scene.set_selected_clip_ids(self._selection_controller.selected_clip_ids())

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._refresh_from_controller()

    def _refresh_selection_from_controller(self) -> None:
        self._timeline_scene.set_selected_clip_ids(self._selection_controller.selected_clip_ids())

    def _on_playback_time_changed(self, time_seconds: float) -> None:
        self._timeline_controller.set_playhead_seconds(time_seconds)
        self._timeline_scene.set_playhead_seconds(time_seconds)

        if not self._is_dragging:
            self._ensure_playhead_visible(time_seconds)

    def _ensure_playhead_visible(self, time_seconds: float) -> None:
        pps = self._timeline_controller.pixels_per_second
        playhead_x = self._timeline_scene.left_gutter + time_seconds * pps

        viewport_rect = self.viewport().rect()
        visible_scene_rect = self.mapToScene(viewport_rect).boundingRect()
        margin_px = 40.0
        is_playing = self._playback_controller.is_playing()

        if is_playing:
            if playhead_x > visible_scene_rect.right() - margin_px:
                new_scroll_x = playhead_x - (viewport_rect.width() * 0.2)
                self._set_horizontal_scroll(new_scroll_x)
        else:
            if playhead_x < visible_scene_rect.left() + margin_px or playhead_x > visible_scene_rect.right() - margin_px:
                new_scroll_x = playhead_x - (viewport_rect.width() * 0.5)
                self._set_horizontal_scroll(new_scroll_x)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)

        viewport_x = float(event.position().x())
        scene_pos = self.mapToScene(event.position().toPoint())

        if viewport_x <= self._timeline_scene.left_gutter:
            handled = self._handle_header_press(viewport_x, scene_pos.y())
            event.accept()
            if not handled:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        if self._timeline_scene.hit_test_playhead(scene_pos.x(), scene_pos.y()):
            self._is_playhead_dragging = True
            self._seek_to_scene_x(scene_pos.x())
            self.setCursor(Qt.CursorShape.SizeHorCursor)
            if self._playhead_sticky_to_mouse:
                self.viewport().grabMouse()
            event.accept()
            return

        if self._is_ruler_scene_y(scene_pos.y()):
            self._seek_to_scene_x(scene_pos.x())
            self._is_scrubbing = True
            self.setCursor(Qt.CursorShape.SizeHorCursor)
            event.accept()
            return

        scene_item = self.itemAt(event.position().toPoint())
        clip_item = self._clip_item_from_item(scene_item)
        modifiers = event.modifiers()
        multiselect = bool(modifiers & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier))
        if clip_item is None:
            if not multiselect:
                self._selection_controller.clear_selection()
            self._marquee_pending = True
            self._marquee_active = False
            self._marquee_start_scene = (scene_pos.x(), scene_pos.y())
            self._marquee_current_scene = (scene_pos.x(), scene_pos.y())
            self._marquee_initial_selection = self._selection_controller.selected_clip_ids()
            event.accept()
            return

        clip_id = clip_item.clip.clip_id
        if multiselect:
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                self._selection_controller.toggle_selection(clip_id)
            else:
                self._selection_controller.add_to_selection(clip_id)
            event.accept()
            return
        self._selection_controller.select_clip(clip_id)
        active_item = self._find_clip_item_by_id(clip_id)
        if active_item is None:
            event.accept()
            return

        edge_handle = active_item.hit_test_edge(scene_pos.x(), self._trim_handle_pixels)
        fade_handle = active_item.hit_test_fade_handle(scene_pos.x(), scene_pos.y())

        self._drag_mode = "move"
        if fade_handle is not None:
            self._drag_mode = fade_handle
        elif edge_handle == "left":
            self._drag_mode = "trim_left"
        elif edge_handle == "right":
            self._drag_mode = "trim_right"

        self._drag_clip_id = clip_id
        self._drag_start_scene_x = scene_pos.x()
        self._drag_item_start_x = active_item.scenePos().x()
        self._drag_item_start_width = active_item.rect().width()
        self._drag_clip_start_time = active_item.clip.timeline_start
        self._drag_clip_start_duration = active_item.clip.duration
        self._pending_fade_seconds = None
        self._is_dragging = True

        if self._drag_mode in {"move"}:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif self._drag_mode in {"trim_left", "trim_right", "fade_in", "fade_out"}:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        event.accept()

    def _handle_header_press(self, viewport_x: float, scene_y: float) -> bool:
        hit = self._timeline_scene.header_hit_test(viewport_x, scene_y)
        if hit is None:
            return False
        track_id, action = hit
        project = self._timeline_controller.active_project()
        if project is None:
            return False
        track = next((track for track in project.timeline.tracks if track.track_id == track_id), None)
        if track is None:
            return False

        if action == "mute":
            self._timeline_controller.set_track_muted(track_id, not track.is_muted)
            return True
        if action == "lock":
            self._timeline_controller.set_track_locked(track_id, not track.is_locked)
            return True
        if action == "hidden":
            self._timeline_controller.set_track_hidden(track_id, not track.is_hidden)
            return True
        if action == "resize":
            self._header_resize_track_id = track_id
            self._header_resize_start_scene_y = scene_y
            self._header_resize_start_height = track.height
            self._header_resize_pending_height = track.height
            self.setCursor(Qt.CursorShape.SizeVerCursor)
            return True
        return True

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        scene_pos = self.mapToScene(event.position().toPoint())

        if self._is_playhead_dragging:
            self._seek_to_scene_x(scene_pos.x())
            event.accept()
            return

        if self._marquee_pending and not self._is_dragging:
            self._marquee_current_scene = (scene_pos.x(), scene_pos.y())
            dx = abs(self._marquee_current_scene[0] - self._marquee_start_scene[0])
            dy = abs(self._marquee_current_scene[1] - self._marquee_start_scene[1])
            if dx >= 4.0 or dy >= 4.0:
                self._marquee_active = True
            if self._marquee_active:
                self.viewport().update()
            event.accept()
            return

        if self._marquee_active and not self._is_dragging:
            self._marquee_current_scene = (scene_pos.x(), scene_pos.y())
            self.viewport().update()
            event.accept()
            return

        if self._header_resize_track_id is not None:
            delta = scene_pos.y() - self._header_resize_start_scene_y
            self._header_resize_pending_height = max(28.0, min(240.0, self._header_resize_start_height + delta))
            event.accept()
            return

        if self._is_scrubbing:
            self._seek_to_scene_x(scene_pos.x())
            event.accept()
            return

        if not self._is_dragging or self._drag_clip_id is None:
            self._update_hover_cursor(event)
            self._maybe_hover_scrub(event, scene_pos)
            super().mouseMoveEvent(event)
            return

        clip_item = self._find_clip_item_by_id(self._drag_clip_id)
        if clip_item is None:
            self._cancel_drag()
            self._refresh_from_controller()
            super().mouseMoveEvent(event)
            return

        if self._drag_mode in {"fade_in", "fade_out"}:
            self._pending_fade_seconds = self._fade_seconds_from_pointer(clip_item, scene_pos.x(), self._drag_mode)
            event.accept()
            return

        pps = self._timeline_scene.pixels_per_second
        left_gutter = self._timeline_scene.left_gutter
        delta_x = scene_pos.x() - self._drag_start_scene_x

        if self._drag_mode == "move":
            proposed_x = self._drag_item_start_x + delta_x
            proposed_start = (proposed_x - left_gutter) / pps
            proposed_duration = self._drag_clip_start_duration
        elif self._drag_mode == "trim_left":
            right_edge = self._drag_item_start_x + self._drag_item_start_width
            proposed_x = self._drag_item_start_x + delta_x
            proposed_start = (proposed_x - left_gutter) / pps
            proposed_duration = (right_edge - proposed_x) / pps
        else:
            proposed_start = self._drag_clip_start_time
            proposed_duration = (self._drag_item_start_width + delta_x) / pps

        snapped_start, snapped_duration, snap_target_time = self._timeline_controller.get_snap_position(
            self._drag_clip_id,
            proposed_start,
            proposed_duration,
            self._drag_mode,
        )

        display_x = left_gutter + snapped_start * pps
        display_width = snapped_duration * pps

        if self._drag_mode == "move":
            clip_item.setX(display_x)
        else:
            clip_item.set_display_geometry(display_x, display_width)

        if snap_target_time is not None:
            self._timeline_scene.show_snap_guide(left_gutter + snap_target_time * pps)
        else:
            self._timeline_scene.hide_snap_guide()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._is_dragging and (self._marquee_active or self._marquee_pending):
            if self._marquee_active:
                selection_rect = self._marquee_scene_rect()
                hit_ids = self._clip_ids_intersecting_scene_rect(selection_rect)
                modifiers = event.modifiers()
                multiselect = bool(modifiers & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier))
                if multiselect:
                    merged = list(self._marquee_initial_selection)
                    for clip_id in hit_ids:
                        if clip_id not in merged:
                            merged.append(clip_id)
                    self._selection_controller.set_selection(merged)
                else:
                    self._selection_controller.set_selection(hit_ids)
                self.viewport().update()
            self._marquee_pending = False
            self._marquee_active = False
            self._marquee_initial_selection = []
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton and self._is_playhead_dragging:
            self._is_playhead_dragging = False
            if QWidget.mouseGrabber() is self.viewport():
                self.viewport().releaseMouse()
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton and self._header_resize_track_id is not None:
            self._timeline_controller.set_track_height(self._header_resize_track_id, self._header_resize_pending_height)
            self._header_resize_track_id = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton and self._is_scrubbing:
            self._is_scrubbing = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        if event.button() != Qt.MouseButton.LeftButton or not self._is_dragging or self._drag_clip_id is None:
            super().mouseReleaseEvent(event)
            return

        clip_item = self._find_clip_item_by_id(self._drag_clip_id)
        if clip_item is None:
            self._cancel_drag()
            self._refresh_from_controller()
            super().mouseReleaseEvent(event)
            return

        if self._drag_mode == "move":
            pixels_per_second = self._timeline_scene.pixels_per_second
            left_gutter = self._timeline_scene.left_gutter
            scene_x = max(left_gutter, clip_item.scenePos().x())
            new_timeline_start = max(0.0, (scene_x - left_gutter) / pixels_per_second)
            rounded_timeline_start = round(new_timeline_start, 3)
            moved = abs(rounded_timeline_start - self._drag_clip_start_time) > 1e-6
            if moved:
                try:
                    did_move = self._timeline_controller.move_clip(self._drag_clip_id, rounded_timeline_start)
                except ValueError:
                    did_move = False
                if not did_move:
                    self._refresh_from_controller()
            else:
                self._refresh_from_controller()
        elif self._drag_mode in {"trim_left", "trim_right"}:
            pixels_per_second = self._timeline_scene.pixels_per_second
            left_gutter = self._timeline_scene.left_gutter
            scene_x = max(left_gutter, clip_item.scenePos().x())
            new_timeline_start = max(0.0, (scene_x - left_gutter) / pixels_per_second)
            new_duration = max(self._min_clip_pixels / pixels_per_second, clip_item.rect().width() / pixels_per_second)
            rounded_timeline_start = round(new_timeline_start, 3)
            rounded_duration = round(new_duration, 3)
            trimmed = (
                abs(rounded_timeline_start - self._drag_clip_start_time) > 1e-6
                or abs(rounded_duration - self._drag_clip_start_duration) > 1e-6
            )
            if trimmed:
                try:
                    did_trim = self._timeline_controller.trim_clip(
                        self._drag_clip_id,
                        rounded_timeline_start,
                        rounded_duration,
                        trim_side="left" if self._drag_mode == "trim_left" else "right",
                    )
                except ValueError:
                    did_trim = False
                if not did_trim:
                    self._refresh_from_controller()
            else:
                self._refresh_from_controller()
        elif self._drag_mode in {"fade_in", "fade_out"}:
            fade_seconds = self._pending_fade_seconds
            if fade_seconds is not None:
                if self._drag_mode == "fade_in":
                    self._timeline_controller.set_clip_fade(self._drag_clip_id, fade_in_seconds=fade_seconds)
                else:
                    self._timeline_controller.set_clip_fade(self._drag_clip_id, fade_out_seconds=fade_seconds)

        self._cancel_drag()
        event.accept()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        scene_pos = self.mapToScene(event.pos())
        viewport_x = float(event.pos().x())
        scene_item = self.itemAt(event.pos())
        clip_item = self._clip_item_from_item(scene_item)
        menu = QMenu(self)

        if clip_item is not None:
            clip_id = clip_item.clip.clip_id
            self._selection_controller.select_clip(clip_id)

            split_action = menu.addAction("Split")
            duplicate_action = menu.addAction("Duplicate")
            menu.addSeparator()
            cut_action = menu.addAction("Cut")
            copy_action = menu.addAction("Copy")
            paste_action = menu.addAction("Paste")
            mute_action = menu.addAction("Toggle Mute")
            menu.addSeparator()
            delete_action = menu.addAction("Delete")
            ripple_delete_action = menu.addAction("Ripple Delete")

            triggered = menu.exec(self.mapToGlobal(event.pos()))
            if triggered is None:
                return
            if triggered == split_action:
                self._timeline_controller.split_selected_clip(self._playback_controller.current_time())
            elif triggered == duplicate_action:
                self._timeline_controller.duplicate_clip(clip_id)
            elif triggered == cut_action:
                self._timeline_controller.cut_clip_to_clipboard(clip_id)
            elif triggered == copy_action:
                self._timeline_controller.copy_clip_to_clipboard(clip_id)
            elif triggered == paste_action:
                target_track_id = self._timeline_scene.track_id_at_scene_y(scene_pos.y())
                self._timeline_controller.paste_clipboard_at(
                    timeline_start=self._playback_controller.current_time(),
                    preferred_track_id=target_track_id,
                )
            elif triggered == mute_action:
                self._timeline_controller.set_clip_muted(clip_id, not clip_item.clip.is_muted)
            elif triggered == delete_action:
                self._timeline_controller.delete_clip(clip_id)
            elif triggered == ripple_delete_action:
                self._timeline_controller.ripple_delete_clip(clip_id)
            return

        hovered_track = self._track_at_scene_y(scene_pos.y())
        rename_track_action = None
        role_actions: dict[object, str] = {}
        if hovered_track is not None and viewport_x <= self._timeline_scene.left_gutter:
            rename_track_action = menu.addAction("Rename Track...")
            if hovered_track.track_type.lower() in {"audio", "mixed"}:
                role_menu = menu.addMenu("Track Role")
                current_role = str(getattr(hovered_track, "track_role", "music")).lower()
                for role_value, role_label in (("voice", "Voice"), ("music", "Music"), ("sfx", "SFX")):
                    role_action = role_menu.addAction(role_label)
                    role_action.setCheckable(True)
                    role_action.setChecked(current_role == role_value)
                    role_actions[role_action] = role_value
            menu.addSeparator()

        paste_action = menu.addAction("Paste")
        paste_action.setEnabled(self._timeline_controller.has_clipboard_clip())
        add_track_menu = menu.addMenu("Add Track")
        add_video_track = add_track_menu.addAction("Video Track")
        add_overlay_track = add_track_menu.addAction("Overlay Track")
        add_audio_track = add_track_menu.addAction("Audio Track")
        add_text_track = add_track_menu.addAction("Text Track")

        triggered = menu.exec(self.mapToGlobal(event.pos()))
        if triggered is None:
            return
        if rename_track_action is not None and triggered == rename_track_action and hovered_track is not None:
            value, accepted = QInputDialog.getText(self, "Rename Track", "Track name:", text=hovered_track.name)
            if accepted and value.strip():
                self._timeline_controller.rename_track(hovered_track.track_id, value)
            return
        if hovered_track is not None and triggered in role_actions:
            self._timeline_controller.set_track_role(hovered_track.track_id, role_actions[triggered])
            return
        if triggered == paste_action:
            target_track_id = self._timeline_scene.track_id_at_scene_y(scene_pos.y())
            self._timeline_controller.paste_clipboard_at(
                timeline_start=self._playback_controller.current_time(),
                preferred_track_id=target_track_id,
            )
        elif triggered == add_video_track:
            self._timeline_controller.add_track("video")
        elif triggered == add_overlay_track:
            self._timeline_controller.add_track("overlay")
        elif triggered == add_audio_track:
            self._timeline_controller.add_track("audio")
        elif triggered == add_text_track:
            self._timeline_controller.add_track("text")

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        viewport_x = float(event.position().x())
        scene_pos = self.mapToScene(event.position().toPoint())
        if viewport_x > self._timeline_scene.left_gutter:
            super().mouseDoubleClickEvent(event)
            return

        hit = self._timeline_scene.header_hit_test(viewport_x, scene_pos.y())
        if hit is None:
            super().mouseDoubleClickEvent(event)
            return
        track_id, action = hit
        if action != "name":
            super().mouseDoubleClickEvent(event)
            return

        project = self._timeline_controller.active_project()
        if project is None:
            return
        track = next((track for track in project.timeline.tracks if track.track_id == track_id), None)
        if track is None:
            return

        value, accepted = QInputDialog.getText(self, "Rename Track", "Track name:", text=track.name)
        if accepted and value.strip():
            self._timeline_controller.rename_track(track_id, value)
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        modifiers = event.modifiers()
        if event.key() == Qt.Key.Key_Delete:
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                if self._timeline_controller.ripple_delete_clip():
                    event.accept()
                    return
            elif self._timeline_controller.delete_selected_clip():
                event.accept()
                return

        if event.key() == Qt.Key.Key_S and modifiers == Qt.KeyboardModifier.NoModifier:
            if self._timeline_controller.split_selected_clip(self._playback_controller.current_time()):
                event.accept()
                return

        if event.key() == Qt.Key.Key_D and modifiers == Qt.KeyboardModifier.ControlModifier:
            if self._timeline_controller.duplicate_clip() is not None:
                event.accept()
                return

        if event.key() == Qt.Key.Key_X and modifiers == Qt.KeyboardModifier.ControlModifier:
            if self._timeline_controller.cut_clip_to_clipboard():
                event.accept()
                return

        if event.key() == Qt.Key.Key_C and modifiers == Qt.KeyboardModifier.ControlModifier:
            if self._timeline_controller.copy_clip_to_clipboard():
                event.accept()
                return

        if event.key() == Qt.Key.Key_V and modifiers == Qt.KeyboardModifier.ControlModifier:
            pasted = self._timeline_controller.paste_clipboard_at(
                timeline_start=self._playback_controller.current_time(),
                preferred_track_id=self._timeline_scene.track_id_at_scene_y(self._last_mouse_scene_pos().y()),
            )
            if pasted is not None:
                event.accept()
                return

        if event.key() == Qt.Key.Key_Space and modifiers == Qt.KeyboardModifier.NoModifier:
            if self._playback_controller.is_playing():
                self._playback_controller.pause()
            else:
                self._playback_controller.play()
            event.accept()
            return

        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            step = self._playhead_nudge_step(modifiers)
            if step > 0.0:
                direction = -1.0 if event.key() == Qt.Key.Key_Left else 1.0
                new_time = max(0.0, self._playback_controller.current_time() + direction * step)
                self._playback_controller.seek(new_time)
                event.accept()
                return

        if event.key() == Qt.Key.Key_Home and modifiers == Qt.KeyboardModifier.NoModifier:
            self._playback_controller.seek(0.0)
            event.accept()
            return

        if event.key() == Qt.Key.Key_End and modifiers == Qt.KeyboardModifier.NoModifier:
            project = self._timeline_controller.active_project()
            end_time = project.timeline.total_duration() if project is not None else 0.0
            self._playback_controller.seek(end_time)
            event.accept()
            return

        super().keyPressEvent(event)

    def _playhead_nudge_step(self, modifiers: Qt.KeyboardModifier) -> float:
        project = self._timeline_controller.active_project()
        fps = project.fps if project is not None and project.fps > 0 else 30.0
        frame_duration = 1.0 / fps
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            return max(frame_duration, 1.0)
        if modifiers == Qt.KeyboardModifier.NoModifier:
            return frame_duration
        return 0.0

    def _is_ruler_scene_y(self, scene_y: float) -> bool:
        return 0.0 <= scene_y <= self._timeline_scene.ruler_height

    def _seek_to_scene_x(self, scene_x: float) -> None:
        pps = self._timeline_scene.pixels_per_second
        if pps <= 0:
            return
        time_seconds = max(0.0, (scene_x - self._timeline_scene.left_gutter) / pps)
        self._playback_controller.seek(round(time_seconds, 4))

    def _maybe_hover_scrub(self, event: QMouseEvent, scene_pos) -> None:
        """Move the playhead to follow the cursor when hover-scrub is on.

        Only fires when no mouse button is held (so it doesn't fight the
        existing scrub/drag/marquee handlers) and the pointer is over the
        ruler or clip area — never over the track-header gutter. Throttled
        with a wall-clock timestamp so a fast sweep doesn't decode every
        intermediate pixel.
        """

        if not self._hover_scrub_enabled:
            return
        if event.buttons() != Qt.MouseButton.NoButton:
            return
        viewport_x = event.position().x()
        if viewport_x <= self._timeline_scene.left_gutter:
            return
        # Skip frames within the throttle window. ``time.monotonic`` would
        # also work but ``event.timestamp`` matches Qt's own clock and lets
        # tests drive synthetic timestamps deterministically.
        now_ms = int(event.timestamp())
        if now_ms == 0:
            # Fall back to a process-monotonic clock when the event carries
            # no timestamp (synthesised events in tests, etc.).
            now_ms = monotonic_ns() // 1_000_000
        if now_ms - self._hover_scrub_last_seek_ms < self._HOVER_SCRUB_THROTTLE_MS:
            return
        self._hover_scrub_last_seek_ms = now_ms
        self._seek_to_scene_x(scene_pos.x())

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            scene_pos = self.mapToScene(event.position().toPoint())
            delta = event.angleDelta().y()
            if delta > 0:
                self._perform_zoom(self._timeline_controller.zoom_in, anchor_scene_x=scene_pos.x())
            else:
                self._perform_zoom(self._timeline_controller.zoom_out, anchor_scene_x=scene_pos.x())
            event.accept()
        else:
            super().wheelEvent(event)

    @staticmethod
    def _clip_item_from_item(item: QGraphicsItem | None) -> ClipItem | None:
        current = item
        while current is not None:
            if isinstance(current, ClipItem):
                return current
            current = current.parentItem()
        return None

    def _find_clip_item_by_id(self, clip_id: str) -> ClipItem | None:
        for item in self._timeline_scene.items():
            if isinstance(item, ClipItem) and item.clip.clip_id == clip_id:
                return item
        return None

    def _update_hover_cursor(self, event: QMouseEvent) -> None:
        scene_pos = self.mapToScene(event.position().toPoint())
        if self._timeline_scene.hit_test_playhead(scene_pos.x(), scene_pos.y()):
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            return

        viewport_x = float(event.position().x())
        if viewport_x <= self._timeline_scene.left_gutter:
            hit = self._timeline_scene.header_hit_test(viewport_x, scene_pos.y())
            if hit is not None and hit[1] == "resize":
                self.setCursor(Qt.CursorShape.SizeVerCursor)
                return
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        scene_item = self.itemAt(event.position().toPoint())
        clip_item = self._clip_item_from_item(scene_item)
        if clip_item is None:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        if clip_item.hit_test_fade_handle(scene_pos.x(), scene_pos.y()) is not None:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
            return
        if clip_item.hit_test_edge(scene_pos.x(), self._trim_handle_pixels) is not None:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
            return
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def _cancel_drag(self) -> None:
        if self._is_playhead_dragging:
            self._is_playhead_dragging = False
            if QWidget.mouseGrabber() is self.viewport():
                self.viewport().releaseMouse()
        self._is_dragging = False
        self._drag_mode = None
        self._drag_clip_id = None
        self._pending_fade_seconds = None
        self._timeline_scene.hide_snap_guide()
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._marquee_pending = False
        self._marquee_active = False

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawForeground(painter, rect)
        if not self._marquee_active:
            return
        selection_rect = self._marquee_scene_rect()
        if selection_rect.width() < 1.0 and selection_rect.height() < 1.0:
            return
        painter.save()
        painter.setPen(QPen(QColor("#00bcd4"), 1.0, Qt.PenStyle.DashLine))
        # Keep marquee as outline-only so lane separators stay visible while dragging.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(selection_rect)
        painter.restore()

    def _marquee_scene_rect(self) -> QRectF:
        x1, y1 = self._marquee_start_scene
        x2, y2 = self._marquee_current_scene
        return QRectF(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))

    def _clip_ids_intersecting_scene_rect(self, scene_rect: QRectF) -> list[str]:
        if scene_rect.width() <= 0.0 and scene_rect.height() <= 0.0:
            return []
        hits: list[str] = []
        for item in self._timeline_scene.items(scene_rect):
            if not isinstance(item, ClipItem):
                continue
            if item.clip.clip_id in hits:
                continue
            clip_rect = item.sceneBoundingRect()
            if clip_rect.intersects(scene_rect):
                hits.append(item.clip.clip_id)
        return hits

    @staticmethod
    def _fade_seconds_from_pointer(clip_item: ClipItem, scene_x: float, mode: str) -> float:
        local_x = max(0.0, min(scene_x - clip_item.scenePos().x(), clip_item.rect().width()))
        if clip_item.rect().width() <= 1e-6 or clip_item.clip.duration <= 1e-6:
            return 0.0

        ratio = local_x / clip_item.rect().width()
        if mode == "fade_in":
            return max(0.0, min(clip_item.clip.duration, clip_item.clip.duration * ratio))
        if mode == "fade_out":
            return max(0.0, min(clip_item.clip.duration, clip_item.clip.duration * (1.0 - ratio)))
        return 0.0

    def _find_clip_pair_near_scene_x(
        self,
        scene_x: float,
        scene_y: float,
        edge_tolerance_px: float,
    ) -> tuple[str, str, str] | None:
        track = self._track_at_scene_y(scene_y)
        if track is None:
            return None

        sorted_clips = list(track.sorted_clips())
        best_pair: tuple[str, str, str] | None = None
        best_distance = edge_tolerance_px + 1.0
        for index in range(len(sorted_clips) - 1):
            clip_a = sorted_clips[index]
            clip_b = sorted_clips[index + 1]
            edge_x = self._scene_x_for_time(clip_a.timeline_end)
            distance = abs(scene_x - edge_x)
            if distance <= edge_tolerance_px and distance < best_distance:
                best_pair = (track.track_id, clip_a.clip_id, clip_b.clip_id)
                best_distance = distance
        return best_pair

    def _track_at_scene_y(self, scene_y: float):
        timeline = self._timeline_controller.active_timeline()
        if timeline is None:
            return None
        track_id = self._timeline_scene.track_id_at_scene_y(scene_y)
        if track_id is None:
            return None
        for track in timeline.tracks:
            if track.track_id == track_id:
                return track
        return None

    def _scene_x_for_time(self, time_seconds: float) -> float:
        return (
            self._timeline_scene.left_gutter
            + max(0.0, float(time_seconds)) * self._timeline_scene.pixels_per_second
        )

    def _last_mouse_scene_pos(self) -> QPoint:
        cursor = QCursor.pos()
        viewport_point = self.viewport().mapFromGlobal(cursor)
        return self.mapToScene(viewport_point).toPoint()
