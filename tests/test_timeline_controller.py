from __future__ import annotations

import pytest
from app.controllers.project_controller import ProjectController
from app.controllers.selection_controller import SelectionController
from app.controllers.timeline_controller import TimelineController
from app.domain.media_asset import MediaAsset
from app.domain.project import build_demo_project, build_empty_project


def _build_timeline_controller() -> tuple[TimelineController, SelectionController]:
    project_controller = ProjectController()
    project_controller.set_active_project(build_demo_project())
    selection_controller = SelectionController()
    timeline_controller = TimelineController(
        project_controller=project_controller,
        selection_controller=selection_controller,
    )
    return timeline_controller, selection_controller


def test_set_snapping_enabled_affects_snap_result() -> None:
    timeline_controller, _selection_controller = _build_timeline_controller()
    timeline_controller.configure_timeline_metrics(
        pixels_per_second=90.0,
        snap_threshold_pixels=10.0,
        playhead_seconds=0.0,
        minimum_clip_duration_seconds=0.2,
    )

    project = timeline_controller.active_project()
    assert project is not None
    first_clip = project.timeline.tracks[1].clips[0]
    neighbour_clip = project.timeline.tracks[1].clips[1]
    proposed_start = neighbour_clip.timeline_start + 0.02

    snapped_start, _snapped_duration, snap_target = timeline_controller.get_snap_position(
        first_clip.clip_id,
        proposed_start,
        first_clip.duration,
        "move",
    )
    assert snap_target is not None
    assert snapped_start == pytest.approx(neighbour_clip.timeline_start, abs=0.1) or snapped_start == pytest.approx(
        neighbour_clip.timeline_end, abs=0.1
    )

    timeline_controller.set_snapping_enabled(False)
    unsnapped_start, _duration, unsnapped_target = timeline_controller.get_snap_position(
        first_clip.clip_id,
        proposed_start,
        first_clip.duration,
        "move",
    )
    assert unsnapped_target is None
    assert unsnapped_start == pytest.approx(proposed_start)


def test_add_caption_segments_creates_text_clips_and_selects_last() -> None:
    timeline_controller, selection_controller = _build_timeline_controller()
    timeline_controller.set_playhead_seconds(0.0)

    project = timeline_controller.active_project()
    assert project is not None
    initial_total_captions = len(timeline_controller.caption_clips())

    imported_count = timeline_controller.add_caption_segments(
        [
            (0.5, 1.25, "Caption one"),
            (2.0, 3.0, "Caption two"),
        ]
    )

    assert imported_count == 2
    captions_after = timeline_controller.caption_clips()
    assert len(captions_after) == initial_total_captions + 2
    assert selection_controller.selected_clip_id() == captions_after[-1].clip_id


def test_caption_clips_lists_only_text_track_clips() -> None:
    timeline_controller, _selection_controller = _build_timeline_controller()
    baseline = len(timeline_controller.caption_clips())
    timeline_controller.add_caption_segments([(10.5, 11.5, "Alpha"), (12.0, 13.0, "Bravo")])

    captions = timeline_controller.caption_clips()
    assert len(captions) == baseline + 2
    contents = [clip.content for clip in captions]
    assert "Alpha" in contents
    assert "Bravo" in contents


def test_duplicate_caption_clip_creates_shifted_copy() -> None:
    timeline_controller, _selection_controller = _build_timeline_controller()
    timeline_controller.add_caption_segments([(10.5, 11.5, "Original caption")])

    original = next(
        clip for clip in timeline_controller.caption_clips() if clip.content == "Original caption"
    )
    new_clip_id = timeline_controller.duplicate_caption_clip(original.clip_id)

    assert new_clip_id is not None
    duplicates = [c for c in timeline_controller.caption_clips() if c.clip_id == new_clip_id]
    assert len(duplicates) == 1
    duplicate = duplicates[0]
    assert duplicate.content == original.content
    assert duplicate.timeline_start == pytest.approx(original.timeline_start + original.duration)
    assert duplicate.duration == pytest.approx(original.duration)


def test_merge_caption_with_next_joins_text_and_deletes_second() -> None:
    timeline_controller, _selection_controller = _build_timeline_controller()
    total_before_add = len(timeline_controller.caption_clips())
    timeline_controller.add_caption_segments([(10.5, 11.0, "First"), (11.5, 12.0, "Second")])

    captions_after_add = timeline_controller.caption_clips()
    first = next(clip for clip in captions_after_add if clip.content == "First")
    second = next(clip for clip in captions_after_add if clip.content == "Second")

    merged = timeline_controller.merge_caption_with_next(first.clip_id)
    assert merged is True

    captions_after = timeline_controller.caption_clips()
    assert len(captions_after) == total_before_add + 1
    remaining = next(clip for clip in captions_after if clip.clip_id == first.clip_id)
    assert "First" in remaining.content and "Second" in remaining.content
    assert remaining.timeline_start == pytest.approx(first.timeline_start)
    assert remaining.timeline_start + remaining.duration == pytest.approx(
        second.timeline_start + second.duration
    )
    assert not any(clip.clip_id == second.clip_id for clip in captions_after)


def test_update_caption_text_changes_content() -> None:
    timeline_controller, _selection_controller = _build_timeline_controller()
    timeline_controller.add_caption_segments([(10.5, 11.5, "BeforeUnique")])
    clip = next(c for c in timeline_controller.caption_clips() if c.content == "BeforeUnique")

    assert timeline_controller.update_caption_text(clip.clip_id, "AfterUnique") is True
    assert clip.content == "AfterUnique"
    assert timeline_controller.update_caption_text(clip.clip_id, "AfterUnique") is False


def test_track_controls_add_toggle_and_resize() -> None:
    timeline_controller, _selection_controller = _build_timeline_controller()

    new_track_id = timeline_controller.add_track("audio")
    assert new_track_id is not None

    project = timeline_controller.active_project()
    assert project is not None
    track = next(track for track in project.timeline.tracks if track.track_id == new_track_id)
    assert track.track_type == "audio"

    assert timeline_controller.set_track_muted(new_track_id, True) is True
    assert timeline_controller.set_track_locked(new_track_id, True) is True
    assert timeline_controller.set_track_hidden(new_track_id, True) is True
    assert timeline_controller.set_track_height(new_track_id, 120.0) is True

    assert track.is_muted is True
    assert track.is_locked is True
    assert track.is_hidden is True
    assert track.height == pytest.approx(120.0)


def test_clipboard_copy_paste_and_duplicate() -> None:
    timeline_controller, selection_controller = _build_timeline_controller()
    project = timeline_controller.active_project()
    assert project is not None

    source_clip = project.timeline.tracks[1].clips[0]
    selection_controller.select_clip(source_clip.clip_id)
    assert timeline_controller.copy_clip_to_clipboard() is True

    pasted_clip_id = timeline_controller.paste_clipboard_at(timeline_start=12.0)
    assert pasted_clip_id is not None
    pasted_clip = timeline_controller._find_clip_by_id(pasted_clip_id)
    assert pasted_clip is not None
    assert pasted_clip.timeline_start == pytest.approx(12.0)
    assert pasted_clip.track_id == source_clip.track_id

    duplicated_clip_id = timeline_controller.duplicate_clip(source_clip.clip_id)
    assert duplicated_clip_id is not None
    duplicated_clip = timeline_controller._find_clip_by_id(duplicated_clip_id)
    assert duplicated_clip is not None
    assert duplicated_clip.timeline_start == pytest.approx(source_clip.timeline_start + source_clip.duration)


def test_ripple_delete_shifts_following_clips_in_same_track() -> None:
    timeline_controller, selection_controller = _build_timeline_controller()
    project = timeline_controller.active_project()
    assert project is not None

    first_clip = project.timeline.tracks[1].clips[0]
    second_clip = project.timeline.tracks[1].clips[1]
    selection_controller.select_clip(first_clip.clip_id)

    deleted = timeline_controller.ripple_delete_clip()
    assert deleted is True
    assert timeline_controller._find_clip_by_id(first_clip.clip_id) is None
    assert second_clip.timeline_start == pytest.approx(4.1 - first_clip.duration)


def test_main_track_layout_keeps_main_video_track() -> None:
    timeline_controller, _selection_controller = _build_timeline_controller()
    project = timeline_controller.active_project()
    assert project is not None

    main_tracks = [track for track in project.timeline.tracks if track.is_main]
    assert len(main_tracks) == 1
    main_track = main_tracks[0]
    assert main_track.track_type == "video"
    assert main_track.name == "Main"


def test_move_clip_on_main_ripples_following_clips() -> None:
    timeline_controller, _selection_controller = _build_timeline_controller()
    project = timeline_controller.active_project()
    assert project is not None

    main_track = next(track for track in project.timeline.tracks if track.is_main)
    first_clip = main_track.clips[0]
    second_clip = main_track.clips[1]
    original_track_count = len(project.timeline.tracks)
    original_second_start = second_clip.timeline_start

    moved = timeline_controller.move_clip(first_clip.clip_id, second_clip.timeline_start + 0.1)
    assert moved is True
    # The moving clip stays on main, and the second clip is pushed right by the moved clip's duration.
    assert first_clip.track_id == main_track.track_id
    assert len(project.timeline.tracks) == original_track_count
    assert second_clip.timeline_start == pytest.approx(original_second_start + first_clip.duration)
    assert first_clip.timeline_end <= second_clip.timeline_start + 1e-6


def test_add_clip_from_media_on_main_with_overlap_ripples_subsequent() -> None:
    timeline_controller, _selection_controller = _build_timeline_controller()
    project = timeline_controller.active_project()
    assert project is not None

    main_track = next(track for track in project.timeline.tracks if track.is_main)
    second_clip_before = main_track.clips[1]
    original_second_start = second_clip_before.timeline_start
    original_track_count = len(project.timeline.tracks)

    created_clip_id = timeline_controller.add_clip_from_media(
        "media_intro",
        timeline_start=1.0,
        preferred_track_id=main_track.track_id,
    )
<<<<<<< HEAD
    assert created_clip_id is not None
    created_clip = timeline_controller._find_clip_by_id(created_clip_id)
    assert created_clip is not None
    # New clip stays on main and existing later clip is rippled forward.
    assert created_clip.track_id == main_track.track_id
    assert len(project.timeline.tracks) == original_track_count
    assert second_clip_before.timeline_start == pytest.approx(
        original_second_start + created_clip.duration
    )


def test_delete_clip_on_main_auto_ripples() -> None:
    timeline_controller, _selection_controller = _build_timeline_controller()
    project = timeline_controller.active_project()
    assert project is not None

    main_track = next(track for track in project.timeline.tracks if track.is_main)
    first_clip = main_track.clips[0]
    second_clip = main_track.clips[1]
    deleted_duration = first_clip.duration
    original_second_start = second_clip.timeline_start

    deleted = timeline_controller.delete_clip(first_clip.clip_id)
    assert deleted is True
    assert timeline_controller._find_clip_by_id(first_clip.clip_id) is None
    assert second_clip.timeline_start == pytest.approx(original_second_start - deleted_duration)


def test_add_audio_media_auto_creates_audio_track_when_dropped_on_main() -> None:
    project_controller = ProjectController()
    project = build_empty_project()
    project.media_items.append(
        MediaAsset(
            media_id="media_audio_drop",
            name="Audio Drop",
            file_path="demo/audio_drop.wav",
            media_type="audio",
            duration_seconds=2.5,
        )
    )
    project_controller.set_active_project(project)
    selection_controller = SelectionController()
    timeline_controller = TimelineController(
        project_controller=project_controller,
        selection_controller=selection_controller,
    )

    main_track = next(track for track in project.timeline.tracks if track.is_main)
    created_clip_id = timeline_controller.add_clip_from_media(
        "media_audio_drop",
        timeline_start=0.5,
        preferred_track_id=main_track.track_id,
    )

    assert created_clip_id is not None
    created_clip = timeline_controller._find_clip_by_id(created_clip_id)
    assert created_clip is not None
    audio_tracks = [track for track in project.timeline.tracks if track.track_type == "audio"]
    assert len(audio_tracks) == 1
    assert created_clip.track_id == audio_tracks[0].track_id


def test_add_clip_from_media_can_force_new_track_creation() -> None:
    timeline_controller, _selection_controller = _build_timeline_controller()
    project = timeline_controller.active_project()
    assert project is not None

    main_track = next(track for track in project.timeline.tracks if track.is_main)
    original_track_count = len(project.timeline.tracks)
    created_clip_id = timeline_controller.add_clip_from_media(
        "media_intro",
        timeline_start=10.0,
        force_new_track=True,
    )

    assert created_clip_id is not None
    created_clip = timeline_controller._find_clip_by_id(created_clip_id)
    assert created_clip is not None
    assert len(project.timeline.tracks) == original_track_count + 1
    created_track = next(track for track in project.timeline.tracks if track.track_id == created_clip.track_id)
    assert created_track.track_type == "video"
    assert created_track.is_main is False
    assert created_track.track_id != main_track.track_id


def test_build_empty_project_has_only_main_track() -> None:
=======
    assert created_clip_id is not None
    created_clip = timeline_controller._find_clip_by_id(created_clip_id)
    assert created_clip is not None
    # New clip stays on main and existing later clip is rippled forward.
    assert created_clip.track_id == main_track.track_id
    assert len(project.timeline.tracks) == original_track_count
    assert second_clip_before.timeline_start == pytest.approx(
        original_second_start + created_clip.duration
    )


def test_delete_clip_on_main_auto_ripples() -> None:
    timeline_controller, _selection_controller = _build_timeline_controller()
    project = timeline_controller.active_project()
    assert project is not None

    main_track = next(track for track in project.timeline.tracks if track.is_main)
    first_clip = main_track.clips[0]
    second_clip = main_track.clips[1]
    deleted_duration = first_clip.duration
    original_second_start = second_clip.timeline_start

    deleted = timeline_controller.delete_clip(first_clip.clip_id)
    assert deleted is True
    assert timeline_controller._find_clip_by_id(first_clip.clip_id) is None
    assert second_clip.timeline_start == pytest.approx(original_second_start - deleted_duration)


def test_build_empty_project_has_only_main_track() -> None:
    from app.domain.project import build_empty_project

>>>>>>> 782f8ec6801ae58e198c32db52018999baab2572
    project = build_empty_project()
    assert len(project.timeline.tracks) == 1
    track = project.timeline.tracks[0]
    assert track.is_main is True
    assert track.track_type == "video"
    assert track.clips == []
