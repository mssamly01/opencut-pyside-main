"""Lane backgrounds must stay attached to the scene after render_timeline.

Symptom (manual repro): when the user sweeps the mouse over the timeline,
the horizontal lines that border each track lane (top + bottom border of
the lane background rect) vanish and only come back after a click forces
a re-render. ``QGraphicsScene.items()`` confirms the rect is genuinely
removed from the scene between two paint events — not just hidden.

Cause: ``self.addRect(...)`` returns a Python wrapper that was kept only in
a local ``lane_item`` variable inside ``_draw_track_background``. After the
function returned, PySide6 was eligible to garbage-collect the wrapper, and
in a few real-app event-loop iterations Qt then dropped the underlying C++
item from the scene. Other ``addRect`` callers (ruler) survived in
practice but had the same latent issue.

Fix: keep wrapper references on the scene in ``_decoration_items`` so the
Python side cannot release them while the scene owns the C++ items. This
test pins that invariant.
"""

from __future__ import annotations

from app.bootstrap import create_application
from app.domain.project import build_demo_project
from app.services.thumbnail_service import ThumbnailService
from app.ui.timeline.timeline_scene import TimelineScene
from PySide6.QtWidgets import QGraphicsRectItem


def _lane_rects(scene: TimelineScene) -> list[QGraphicsRectItem]:
    """Return lane-background rects (z=-10, anchored below the ruler)."""
    return [
        item
        for item in scene.items()
        if isinstance(item, QGraphicsRectItem)
        and item.zValue() == -10
        and item.rect().y() >= scene.ruler_height
    ]


def test_render_timeline_retains_lane_background_references() -> None:
    create_application(["pytest"])
    scene = TimelineScene(
        project=build_demo_project(),
        project_path=None,
        thumbnail_service=ThumbnailService(),
        waveform_service=None,
    )

    lanes = _lane_rects(scene)
    assert lanes, "demo project should produce at least one lane rect"

    # Each lane rect added via addRect() must be retained by the scene
    # itself, not only by Python local variables. Otherwise the wrapper is
    # released after the addRect() call returns and Qt later drops the C++
    # item from the scene during normal event-loop iterations.
    retained = scene._decoration_items  # noqa: SLF001
    for lane in lanes:
        assert lane in retained, (
            "lane background rect must be referenced by scene._decoration_items"
        )


def test_re_render_clears_stale_decoration_references() -> None:
    create_application(["pytest"])
    scene = TimelineScene(
        project=build_demo_project(),
        project_path=None,
        thumbnail_service=ThumbnailService(),
        waveform_service=None,
    )

    first_pass = list(scene._decoration_items)  # noqa: SLF001
    assert first_pass, "first render should populate _decoration_items"

    scene.render_timeline()
    second_pass = scene._decoration_items  # noqa: SLF001

    # render_timeline calls scene.clear() which destroys the prior items;
    # _decoration_items must be reset so we don't hold dangling wrappers.
    assert all(item not in second_pass for item in first_pass), (
        "stale references from previous render must be cleared"
    )
    assert second_pass, "fresh render should repopulate _decoration_items"
