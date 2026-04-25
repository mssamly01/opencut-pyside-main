from __future__ import annotations

from app.domain.clips.base_clip import BaseClip
from app.domain.track import Track
from app.domain.transition import MAX_TRANSITION_DURATION, Transition


def find_transition(track: Track, transition_id: str) -> Transition | None:
    for transition in track.transitions:
        if transition.transition_id == transition_id:
            return transition
    return None


def transition_for_clip_pair(
    track: Track,
    clip_a_id: str,
    clip_b_id: str,
) -> Transition | None:
    for transition in track.transitions:
        if transition.from_clip_id == clip_a_id and transition.to_clip_id == clip_b_id:
            return transition
    return None


def is_pair_adjacent(track: Track, clip_a_id: str, clip_b_id: str) -> bool:
    sorted_clips = list(track.sorted_clips())
    for index in range(len(sorted_clips) - 1):
        left = sorted_clips[index]
        right = sorted_clips[index + 1]
        if left.clip_id == clip_a_id and right.clip_id == clip_b_id:
            return True
    return False


def max_transition_duration(track: Track, clip_a_id: str, clip_b_id: str) -> float:
    if not is_pair_adjacent(track, clip_a_id, clip_b_id):
        return 0.0

    clip_a = _clip_by_id(track, clip_a_id)
    clip_b = _clip_by_id(track, clip_b_id)
    if clip_a is None or clip_b is None:
        return 0.0

    shortest = min(float(clip_a.duration), float(clip_b.duration))
    max_by_clip = max(0.0, shortest * 0.5)
    return min(MAX_TRANSITION_DURATION, max_by_clip)


def _clip_by_id(track: Track, clip_id: str) -> BaseClip | None:
    for clip in track.clips:
        if clip.clip_id == clip_id:
            return clip
    return None
