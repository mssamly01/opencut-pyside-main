from services.subtitle_text_ops import (
    replace_all_in_segments,
    replace_all_in_text,
)


def test_replace_all_in_text_case_sensitive_basic():
    assert replace_all_in_text("ABC abc ABC", "abc", "X", case_sensitive=True) == ("ABC X ABC", 1)


def test_replace_all_in_text_case_insensitive_preserves_surrounding_case():
    new_text, count = replace_all_in_text(
        "Hello WORLD! World? world.", "world", "Earth", case_sensitive=False
    )
    # Each occurrence is replaced regardless of original case; surrounding
    # characters keep their case ("Hello "/"! "/"? "/"." stay untouched).
    assert new_text == "Hello Earth! Earth? Earth."
    assert count == 3


def test_replace_all_in_text_no_match_returns_original():
    text = "你好世界"
    assert replace_all_in_text(text, "abc", "x", case_sensitive=True) == (text, 0)
    assert replace_all_in_text(text, "abc", "x", case_sensitive=False) == (text, 0)


def test_replace_all_in_text_empty_find_returns_zero():
    assert replace_all_in_text("hello", "", "x", case_sensitive=False) == ("hello", 0)
    assert replace_all_in_text("hello", "", "x", case_sensitive=True) == ("hello", 0)


def test_replace_all_in_text_overlapping_pattern_consumes_match_length():
    # Replace consumes the full match length so we don't double-count
    # overlapping windows.
    new_text, count = replace_all_in_text("aaaa", "aa", "b", case_sensitive=True)
    assert new_text == "bb"
    assert count == 2


def test_replace_all_in_segments_collects_only_changed_indices():
    segments = [
        (0.0, 1.0, "你好世界"),
        (1.0, 2.0, "Hello World"),
        (2.0, 3.0, "no match here"),
        (3.0, 4.0, "world WORLD world"),
    ]
    changes = replace_all_in_segments(
        segments, "world", "Earth", case_sensitive=False
    )
    assert changes == [
        (1, "Hello Earth", 1),
        (3, "Earth Earth Earth", 3),
    ]


def test_replace_all_in_segments_empty_find_is_noop():
    segments = [(0.0, 1.0, "abc")]
    assert replace_all_in_segments(segments, "", "x", case_sensitive=True) == []


def test_replace_all_in_segments_case_sensitive_distinguishes_case():
    segments = [(0.0, 1.0, "Apple apple APPLE")]
    changes = replace_all_in_segments(
        segments, "apple", "X", case_sensitive=True
    )
    assert changes == [(0, "Apple X APPLE", 1)]
