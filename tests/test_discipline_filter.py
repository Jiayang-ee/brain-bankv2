from faculty_spider_v3.discipline.filter import score_discipline_relevance


def test_management_science_profile_is_accepted():
    score = score_discipline_relevance(
        department="Department of Management Science and Engineering",
        research_interests="Operations research, optimization, supply chain analytics, and decision analytics.",
        publications="Management Science; Operations Research",
    )

    assert score.is_relevant
    assert score.review_status == "accepted"
    assert score.score >= 0.75
    assert "management_science" in score.matched_disciplines
    assert "operations research" in score.matched_keywords


def test_information_systems_profile_is_accepted():
    score = score_discipline_relevance(
        department="School of Business",
        research_interests="Information systems, digital platforms, business analytics, and artificial intelligence.",
    )

    assert score.is_relevant
    assert "information_systems" in score.matched_disciplines
    assert "business_management" in score.matched_disciplines


def test_weak_single_signal_needs_review():
    score = score_discipline_relevance(biography="Her work sometimes applies machine learning to education data.")

    assert not score.is_relevant
    assert score.review_status == "needs_review"
    assert 0.45 <= score.score < 0.75


def test_unrelated_medical_profile_is_rejected():
    score = score_discipline_relevance(
        department="Medical School",
        research_interests="Clinical psychology, medicine, and biology.",
    )

    assert not score.is_relevant
    assert score.review_status == "rejected"
    assert score.negative_keywords


def test_chinese_keywords_match():
    score = score_discipline_relevance(
        department="管理科学与工程学院",
        research_interests="研究方向包括运筹优化、供应链管理和数据分析。",
    )

    assert score.is_relevant
    assert "management_science" in score.matched_disciplines
    assert "运筹" in score.matched_keywords
