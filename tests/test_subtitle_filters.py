from services.subtitle_filters import (
    CHINESE_INTERJECTIONS,
    find_adjacent_duplicate_indices,
    find_interjection_indices,
    find_ocr_error_indices,
    find_reading_speed_outlier_indices,
    is_chinese_interjection_only,
    is_ocr_error,
    is_reading_speed_outlier,
    normalize_whitespace,
)


def _seg(start: float, end: float, text: str) -> tuple[float, float, str]:
    return (start, end, text)


def test_normalize_whitespace_handles_nbsp_fullwidth_tab():
    assert normalize_whitespace("a\xa0b\u3000c\td") == "a b c d"


def test_normalize_whitespace_empty_inputs():
    assert normalize_whitespace(None) == ""
    assert normalize_whitespace("") == ""


def test_is_ocr_error_empty_and_digits_only():
    assert is_ocr_error("") is True
    assert is_ocr_error("   ") is True
    assert is_ocr_error("123") is True
    assert is_ocr_error("12 34") is True


def test_is_ocr_error_only_punctuation():
    assert is_ocr_error("...") is True
    assert is_ocr_error("，。！") is True


def test_is_ocr_error_invalid_latin_letters():
    # Latin letters are NOT allow-listed (the source app targets Chinese OCR).
    assert is_ocr_error("hello") is True


def test_is_ocr_error_clean_chinese():
    assert is_ocr_error("你好世界") is False
    assert is_ocr_error("你好，世界！") is False


def test_find_ocr_error_indices_picks_only_problem_rows():
    segments = [
        _seg(0.0, 1.0, "你好"),
        _seg(1.0, 2.0, ""),
        _seg(2.0, 3.0, "123"),
        _seg(3.0, 4.0, "正常"),
        _seg(4.0, 5.0, "abc"),
    ]
    assert find_ocr_error_indices(segments) == [1, 2, 4]


def test_is_reading_speed_outlier_below_threshold():
    # 2 CJK chars over 5 seconds = 0.4 cps -> below the 3.0 default.
    assert is_reading_speed_outlier(_seg(0.0, 5.0, "你好")) is True


def test_is_reading_speed_outlier_above_threshold():
    # 6 letters over 0.5 seconds = 12 cps -> above threshold.
    assert is_reading_speed_outlier(_seg(0.0, 0.5, "abcdef")) is False


def test_is_reading_speed_outlier_empty_returns_false():
    # Empty rows are reported by the OCR filter instead, not here.
    assert is_reading_speed_outlier(_seg(0.0, 5.0, "")) is False
    assert is_reading_speed_outlier(_seg(0.0, 5.0, "   ")) is False


def test_is_reading_speed_outlier_zero_duration_safe():
    # Duration is floored to 1ms so we never divide by zero. A single char in
    # 1ms reads "fast", so it should NOT be flagged as a slow-reading outlier.
    assert is_reading_speed_outlier(_seg(1.0, 1.0, "你")) is False


def test_find_reading_speed_outlier_indices_respects_custom_threshold():
    segments = [
        _seg(0.0, 1.0, "你好世界"),  # 4 cps -> ok at default, outlier at 5
        _seg(0.0, 10.0, "你好"),  # 0.2 cps -> outlier
    ]
    assert find_reading_speed_outlier_indices(segments) == [1]
    assert find_reading_speed_outlier_indices(segments, min_cps=5.0) == [0, 1]


def test_find_adjacent_duplicate_indices_marks_both_rows():
    segments = [
        _seg(0.0, 1.0, "Hello"),
        _seg(1.0, 2.0, "hello"),
        _seg(2.0, 3.0, "World"),
        _seg(3.0, 4.0, "world  "),
        _seg(4.0, 5.0, "world"),
    ]
    # Duplicates compare lower-cased + collapsed-whitespace; rows 0/1 and 2/3/4.
    assert find_adjacent_duplicate_indices(segments) == [0, 1, 2, 3, 4]


def test_find_adjacent_duplicate_indices_ignores_empty_rows():
    segments = [
        _seg(0.0, 1.0, ""),
        _seg(1.0, 2.0, ""),
        _seg(2.0, 3.0, "你好"),
    ]
    assert find_adjacent_duplicate_indices(segments) == []


def test_find_adjacent_duplicate_indices_non_consecutive_match_skipped():
    segments = [
        _seg(0.0, 1.0, "A"),
        _seg(1.0, 2.0, "B"),
        _seg(2.0, 3.0, "A"),
    ]
    assert find_adjacent_duplicate_indices(segments) == []


def test_is_chinese_interjection_only_basic():
    assert is_chinese_interjection_only("啊") is True
    assert is_chinese_interjection_only("啊啊啊") is True
    # Real word should not match even if it starts with an interjection char.
    assert is_chinese_interjection_only("啊我们走吧") is False
    # Pure punctuation has no clean chars -> False (OCR filter handles it).
    assert is_chinese_interjection_only("...") is False
    assert is_chinese_interjection_only("") is False
    assert is_chinese_interjection_only(None) is False


def test_is_chinese_interjection_only_strips_punctuation_and_whitespace():
    assert is_chinese_interjection_only("啊， 啊！") is True


def test_find_interjection_indices_returns_only_matches():
    segments = [
        _seg(0.0, 1.0, "啊"),
        _seg(1.0, 2.0, "你好"),
        _seg(2.0, 3.0, "嗯哼"),  # 嗯 not in interjection list -> stays
        _seg(3.0, 4.0, "嘿哈"),
    ]
    assert find_interjection_indices(segments) == [0, 3]


def test_chinese_interjections_constant_is_frozen_set():
    assert isinstance(CHINESE_INTERJECTIONS, frozenset)
    assert "啊" in CHINESE_INTERJECTIONS
