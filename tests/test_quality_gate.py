from faculty_spider_v3.publications.batch import (
    QualityGateThresholds,
    JournalGateResult,
    check_quality_gate,
)


def test_quality_gate_passes_good_journal():
    """高数据量、高华人候选比例的期刊应通过门禁。"""
    thresholds = QualityGateThresholds(
        chinese_candidate_min_ratio=0.10,
        missing_author_max_ratio=0.30,
        missing_affiliation_max_ratio=0.50,
        source_errors_max=5,
        min_papers_per_journal=3,
    )
    journals = [
        {"id": 1, "journal_name": "Management Science", "achievement_level": "A+"},
    ]
    papers = [
        {"journal": "Management Science", "first_author_name": "Wei Zhang"},
        {"journal": "Management Science", "first_author_name": "Li Wang"},
        {"journal": "Management Science", "first_author_name": "Fan Chen"},
        {"journal": "Management Science", "first_author_name": ""},  # missing author
    ]
    candidates = [
        {"journal": "Management Science", "name": "Wei Zhang", "affiliations": "Tsinghua University", "chinese_name_score": 0.80},
        {"journal": "Management Science", "name": "Li Wang", "affiliations": "Peking University", "chinese_name_score": 0.75},
        {"journal": "Management Science", "name": "Fan Chen", "affiliations": "Fudan University", "chinese_name_score": 0.70},
        {"journal": "Management Science", "name": "Hao Liu", "affiliations": "", "chinese_name_score": 0.50},
    ]
    review_issues = []

    results = check_quality_gate(journals, papers, candidates, review_issues, thresholds)

    assert 1 in results
    result = results[1]
    assert result.passed is True
    assert result.papers_count == 4
    assert len(result.failures) == 0


def test_quality_gate_fails_low_chinese_ratio():
    """华人候选比例低于阈值应标记为 needs_review。"""
    thresholds = QualityGateThresholds(
        chinese_candidate_min_ratio=0.20,
        missing_author_max_ratio=0.30,
        missing_affiliation_max_ratio=0.50,
        source_errors_max=5,
        min_papers_per_journal=3,
    )
    journals = [
        {"id": 1, "journal_name": "Operations Research", "achievement_level": "A+"},
    ]
    papers = [
        {"journal": "Operations Research", "first_author_name": "John Smith"},
        {"journal": "Operations Research", "first_author_name": "Jane Doe"},
        {"journal": "Operations Research", "first_author_name": "Bob Wilson"},
    ]
    candidates = [
        {"journal": "Operations Research", "name": "John Smith", "affiliations": "MIT", "chinese_name_score": 0.10},
        {"journal": "Operations Research", "name": "Jane Doe", "affiliations": "Stanford", "chinese_name_score": 0.05},
        {"journal": "Operations Research", "name": "Bob Wilson", "affiliations": "Harvard", "chinese_name_score": 0.05},
    ]
    review_issues = []

    results = check_quality_gate(journals, papers, candidates, review_issues, thresholds)

    assert 1 in results
    result = results[1]
    assert result.passed is False
    assert "chinese_ratio_low" in result.review_reason


def test_quality_gate_fails_high_missing_author_ratio():
    """缺作者比例过高的期刊应失败。"""
    thresholds = QualityGateThresholds(
        chinese_candidate_min_ratio=0.10,
        missing_author_max_ratio=0.30,
        missing_affiliation_max_ratio=0.50,
        source_errors_max=5,
        min_papers_per_journal=3,
    )
    journals = [
        {"id": 1, "journal_name": "Test Journal", "achievement_level": "A"},
    ]
    papers = [
        {"journal": "Test Journal", "first_author_name": ""},
        {"journal": "Test Journal", "first_author_name": ""},
        {"journal": "Test Journal", "first_author_name": ""},
        {"journal": "Test Journal", "first_author_name": ""},
        {"journal": "Test Journal", "first_author_name": "Li Wang"},  # only 1 has author
    ]
    candidates = []
    review_issues = []

    results = check_quality_gate(journals, papers, candidates, review_issues, thresholds)

    assert 1 in results
    result = results[1]
    assert result.passed is False
    assert "missing_author_ratio_high" in result.review_reason


def test_quality_gate_fails_low_papers():
    """论文数低于最低要求的期刊应失败。"""
    thresholds = QualityGateThresholds(
        chinese_candidate_min_ratio=0.10,
        missing_author_max_ratio=0.30,
        missing_affiliation_max_ratio=0.50,
        source_errors_max=5,
        min_papers_per_journal=3,
    )
    journals = [
        {"id": 1, "journal_name": "Small Journal", "achievement_level": "A"},
    ]
    papers = [
        {"journal": "Small Journal", "first_author_name": "Wei Zhang"},
        {"journal": "Small Journal", "first_author_name": "Li Wang"},
    ]
    candidates = []
    review_issues = []

    results = check_quality_gate(journals, papers, candidates, review_issues, thresholds)

    assert 1 in results
    result = results[1]
    assert result.passed is False
    assert "papers_below_min" in result.review_reason


def test_quality_gate_fails_high_source_errors():
    """source_errors 超过上限的期刊应失败。"""
    thresholds = QualityGateThresholds(
        chinese_candidate_min_ratio=0.10,
        missing_author_max_ratio=0.30,
        missing_affiliation_max_ratio=0.50,
        source_errors_max=5,
        min_papers_per_journal=3,
    )
    journals = [
        {"id": 1, "journal_name": "Error Journal", "achievement_level": "A"},
    ]
    papers = [
        {"journal": "Error Journal", "first_author_name": "Wei Zhang"},
    ]
    candidates = [
        {"journal": "Error Journal", "name": "Wei Zhang", "affiliations": "Tsinghua", "chinese_name_score": 0.80},
    ]
    # 模拟 6 条 source error
    review_issues = [
        {"message": "openalex error for Error Journal"},
        {"message": "openalex error for Error Journal"},
        {"message": "openalex error for Error Journal"},
        {"message": "openalex error for Error Journal"},
        {"message": "openalex error for Error Journal"},
        {"message": "openalex error for Error Journal"},
    ]

    results = check_quality_gate(journals, papers, candidates, review_issues, thresholds)

    assert 1 in results
    result = results[1]
    assert result.passed is False
    assert "source_errors_high" in result.review_reason


def test_quality_gate_fails_high_missing_affiliation_ratio():
    """缺机构比例超过上限的期刊应失败。"""
    thresholds = QualityGateThresholds(
        chinese_candidate_min_ratio=0.10,
        missing_author_max_ratio=0.30,
        missing_affiliation_max_ratio=0.30,
        source_errors_max=5,
        min_papers_per_journal=3,
    )
    journals = [
        {"id": 1, "journal_name": "Affiliation Journal", "achievement_level": "A"},
    ]
    papers = [
        {"journal": "Affiliation Journal", "first_author_name": "Wei Zhang"},
        {"journal": "Affiliation Journal", "first_author_name": "Li Wang"},
        {"journal": "Affiliation Journal", "first_author_name": "Fan Chen"},
    ]
    candidates = [
        {"journal": "Affiliation Journal", "name": "Wei Zhang", "affiliations": "Tsinghua", "chinese_name_score": 0.80},
        {"journal": "Affiliation Journal", "name": "Li Wang", "affiliations": "", "chinese_name_score": 0.70},
        {"journal": "Affiliation Journal", "name": "Fan Chen", "affiliations": "", "chinese_name_score": 0.70},
        {"journal": "Affiliation Journal", "name": "Hao Liu", "affiliations": "", "chinese_name_score": 0.50},
    ]
    review_issues = []

    results = check_quality_gate(journals, papers, candidates, review_issues, thresholds)

    assert 1 in results
    result = results[1]
    assert result.passed is False
    assert "missing_affiliation_ratio_high" in result.review_reason


def test_quality_gate_multiple_journals():
    """多期刊同时检查，部分通过部分失败。"""
    thresholds = QualityGateThresholds(
        chinese_candidate_min_ratio=0.10,
        missing_author_max_ratio=0.30,
        missing_affiliation_max_ratio=0.50,
        source_errors_max=5,
        min_papers_per_journal=3,
    )
    journals = [
        {"id": 1, "journal_name": "Good Journal", "achievement_level": "A+"},
        {"id": 2, "journal_name": "Bad Journal", "achievement_level": "A"},
    ]
    papers = [
        {"journal": "Good Journal", "first_author_name": "Wei Zhang"},
        {"journal": "Good Journal", "first_author_name": "Li Wang"},
        {"journal": "Good Journal", "first_author_name": "Fan Chen"},
        {"journal": "Bad Journal", "first_author_name": ""},
        {"journal": "Bad Journal", "first_author_name": ""},
    ]
    candidates = [
        {"journal": "Good Journal", "name": "Wei Zhang", "affiliations": "Tsinghua", "chinese_name_score": 0.80},
        {"journal": "Good Journal", "name": "Li Wang", "affiliations": "Peking", "chinese_name_score": 0.75},
        {"journal": "Good Journal", "name": "Fan Chen", "affiliations": "Fudan", "chinese_name_score": 0.70},
        {"journal": "Bad Journal", "name": "John", "affiliations": "MIT", "chinese_name_score": 0.05},
        {"journal": "Bad Journal", "name": "Jane", "affiliations": "Stanford", "chinese_name_score": 0.05},
    ]
    review_issues = []

    results = check_quality_gate(journals, papers, candidates, review_issues, thresholds)

    assert 1 in results
    assert 2 in results
    assert results[1].passed is True
    assert results[2].passed is False