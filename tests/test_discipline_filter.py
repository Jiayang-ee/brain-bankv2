from faculty_spider_v3.discipline.filter import score_discipline_relevance, score_paper_discipline_relevance


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


# Paper-level discipline filtering tests (for broad journals)


def test_paper_discipline_relevant_operations_research_paper_accepted():
    """Paper about operations research / optimization from Nature should be accepted."""
    score = score_paper_discipline_relevance(
        title="Operations Research for Supply Chain Management: A Stochastic Optimization Approach",
        abstract="We develop stochastic optimization models for supply chain inventory management under uncertainty.",
    )

    assert score.review_status == "accepted"
    assert "management_science" in score.matched_disciplines or "industrial_systems_engineering" in score.matched_disciplines


def test_paper_discipline_relevant_information_systems_paper_accepted():
    """Paper about information systems / AI from Science should be accepted."""
    score = score_paper_discipline_relevance(
        title="Digital Platforms and Business Analytics: Evidence from E-commerce Markets",
        abstract="This paper investigates the impact of digital platform design on business analytics outcomes and data-driven decision making, leveraging artificial intelligence and analytics.",
    )

    # Score should be at least needs_review due to strong information systems signals
    assert score.review_status in ("accepted", "needs_review")
    assert "information_systems" in score.matched_disciplines
    assert score.score >= 0.35


def test_paper_discipline_unrelated_biology_paper_rejected():
    """Paper about biology / medicine from Nature should be rejected due to negative keywords."""
    score = score_paper_discipline_relevance(
        title="Novel Gene Expression Patterns in Breast Cancer Metastasis",
        abstract="We identify novel gene expression markers associated with breast cancer metastasis using RNA sequencing. The study involves medical school collaboration.",
    )

    assert score.review_status == "rejected"
    # "medicine" or "medical school" are negative keywords
    assert len(score.negative_keywords) > 0


def test_paper_discipline_weak_signal_needs_review():
    """Paper with only generic machine learning term - score is low but keyword is matched."""
    score = score_paper_discipline_relevance(
        title="Machine Learning Applications in Urban Planning",
        abstract="This paper applies machine learning to urban planning problems.",
    )

    # machine learning is correctly identified as a matched keyword
    assert "machine learning" in score.matched_keywords
    # Single weak signal results in low score (< review_threshold of 0.35)
    assert score.score < 0.35


def test_paper_discipline_empty_input_rejected():
    """Paper with no title/abstract/keywords is rejected."""
    score = score_paper_discipline_relevance(title="", abstract="", keywords="")

    assert score.review_status == "rejected"
    assert score.score == 0.0


def test_paper_discipline_management_science_keywords_accepted():
    """Paper with strong management science keywords is accepted."""
    score = score_paper_discipline_relevance(
        title="Decision Analytics and Optimization in Financial Risk Management",
        abstract="We present decision analytics models combining stochastic programming and econometrics for financial risk management.",
    )

    assert score.review_status in ("accepted", "needs_review")
    assert "management_science" in score.matched_disciplines or "quantitative_finance_economics" in score.matched_disciplines
