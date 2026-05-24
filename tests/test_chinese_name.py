from faculty_spider_v3.names.chinese_name import score_chinese_name


def test_score_chinese_character_name_is_strong_signal():
    score = score_chinese_name("张伟")

    assert score.is_likely_chinese_name
    assert score.score == 0.98
    assert score.reason == "contains_chinese_character"


def test_score_pinyin_name_with_chinese_context():
    score = score_chinese_name("Yifan Chen", context="PhD, Tsinghua University")

    assert score.is_likely_chinese_name
    assert score.score >= 0.7
    assert "chinese_surname" in score.reason


def test_score_non_person_title_is_low():
    score = score_chinese_name("Faculty Directory")

    assert not score.is_likely_chinese_name
    assert score.score < 0.45
