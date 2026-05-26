import csv

import pytest

from faculty_spider_v3.review.issues import export_people_review_csv, export_review_issues_csv
from faculty_spider_v3.storage import FacultySpiderV3Store


def test_export_review_issues_csv(tmp_path):
    store = FacultySpiderV3Store(tmp_path / "test.sqlite")
    store.init_db()
    issue_id = store.add_review_issue(
        issue_type="name_filter_uncertain",
        severity="medium",
        message="Chinese-name score is in review band.",
        related_table="people",
        related_id=12,
        source_url="https://example.edu/profile",
    )

    rows = store.review_issue_rows()
    assert rows[0]["id"] == issue_id

    csv_path = tmp_path / "issues.csv"
    assert export_review_issues_csv(rows, csv_path) == 1

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        exported = list(csv.DictReader(handle))
    assert exported[0]["issue_type"] == "name_filter_uncertain"
    assert exported[0]["source_url"] == "https://example.edu/profile"


def test_export_people_review_csv(tmp_path):
    store = FacultySpiderV3Store(tmp_path / "test.sqlite")
    store.init_db()
    store.upsert_publication_people_candidates([
        {
            "name": "Wei Zhang",
            "affiliations": "Zhejiang University",
            "author_role": "first_author",
            "title": "Deep Learning for Optimization",
            "journal": "Transportation Research Part E",
            "year": 2025,
            "doi": "10.1016/j.tre.2025.001",
            "paper_url": "https://doi.org/10.1016/j.tre.2025.001",
            "source": "openalex",
            "achievement_level": "A2",
            "is_likely_chinese_name": 1,
            "chinese_name_score": 0.8,
            "name_filter_reason": "chinese_surname,pinyin_given_name",
            "paper_titles": "Deep Learning for Optimization",
            "journals": "Transportation Research Part E",
            "years": "2025",
            "author_roles": "first_author",
            "last_5_year_total": 1,
            "first_author_total": 1,
            "corresponding_author_total": 0,
            "top_total": 0,
            "a_plus_total": 0,
            "a_total": 0,
            "a1_total": 0,
            "a2_total": 1,
            "level_counts": {"A2": 1},
        },
    ])

    store.add_review_issue(
        issue_type="publication_only_needs_review",
        severity="medium",
        message="Publication-only candidate pending enrichment.",
        person_id=1,
        related_table="people",
        related_id=1,
        source_url="https://doi.org/10.1016/j.tre.2025.001",
    )

    people = store.people_rows()
    open_issues = store.review_issue_rows(status="open")
    csv_path = tmp_path / "people_review.csv"
    count = export_people_review_csv(people, open_issues, csv_path)
    assert count == 1

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        exported = list(csv.DictReader(handle))
    assert exported[0]["name"] == "Wei Zhang"
    assert exported[0]["review_status"] == "needs_review"
    assert "publication_only_needs_review" in exported[0]["open_issue_types"]


def test_update_person_review_status_resolves_issues(tmp_path):
    store = FacultySpiderV3Store(tmp_path / "test.sqlite")
    store.init_db()
    store.upsert_publication_people_candidates([
        {
            "name": "Li Wang",
            "affiliations": "Tsinghua University",
            "author_role": "first_author",
            "title": "Network Analysis",
            "journal": "Decision Support Systems",
            "year": 2024,
            "doi": "10.1016/j.dss.2024.001",
            "paper_url": "https://doi.org/10.1016/j.dss.2024.001",
            "source": "openalex",
            "achievement_level": "A1",
            "is_likely_chinese_name": 1,
            "chinese_name_score": 0.9,
            "name_filter_reason": "chinese_surname,pinyin_given_name",
            "paper_titles": "Network Analysis",
            "journals": "Decision Support Systems",
            "years": "2024",
            "author_roles": "first_author",
            "last_5_year_total": 1,
            "first_author_total": 1,
            "corresponding_author_total": 0,
            "top_total": 0,
            "a_plus_total": 0,
            "a_total": 0,
            "a1_total": 1,
            "a2_total": 0,
            "level_counts": {"A1": 1},
        },
    ])
    issue_id = store.add_review_issue(
        issue_type="publication_only_needs_review",
        severity="medium",
        message="Pending enrichment.",
        person_id=1,
        related_table="people",
        related_id=1,
        source_url="https://doi.org/10.1016/j.dss.2024.001",
    )

    store.update_person_review_status(1, "accepted", resolved_issue_types=["publication_only_needs_review"])

    people = store.people_rows()
    assert people[0]["review_status"] == "accepted"

    issues = store.review_issue_rows()
    assert issues[0]["status"] == "resolved"
    assert issues[0]["resolved_at"] is not None


def test_import_review_decisions(tmp_path):
    store = FacultySpiderV3Store(tmp_path / "test.sqlite")
    store.init_db()
    store.upsert_publication_people_candidates([
        {
            "name": "Hua Liu",
            "affiliations": "Fudan University",
            "author_role": "first_author",
            "title": "Supply Chain Analytics",
            "journal": "International Journal of Production Economics",
            "year": 2025,
            "doi": "10.1016/j.ijpe.2025.002",
            "paper_url": "https://doi.org/10.1016/j.ijpe.2025.002",
            "source": "openalex",
            "achievement_level": "A2",
            "is_likely_chinese_name": 1,
            "chinese_name_score": 0.75,
            "name_filter_reason": "chinese_surname,pinyin_given_name",
            "paper_titles": "Supply Chain Analytics",
            "journals": "International Journal of Production Economics",
            "years": "2025",
            "author_roles": "first_author",
            "last_5_year_total": 1,
            "first_author_total": 1,
            "corresponding_author_total": 0,
            "top_total": 0,
            "a_plus_total": 0,
            "a_total": 0,
            "a1_total": 0,
            "a2_total": 1,
            "level_counts": {"A2": 1},
        },
    ])
    store.add_review_issue(
        issue_type="publication_only_needs_review",
        severity="medium",
        message="Pending.",
        person_id=1,
        related_table="people",
        related_id=1,
        source_url="https://doi.org/10.1016/j.ijpe.2025.002",
    )

    decisions_csv = tmp_path / "decisions.csv"
    with decisions_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["person_id", "review_status", "resolved_issue_types"])
        writer.writeheader()
        writer.writerow({
            "person_id": "1",
            "review_status": "rejected",
            "resolved_issue_types": "publication_only_needs_review",
        })

    applied = store.import_review_decisions(decisions_csv)
    assert applied == 1

    people = store.people_rows()
    assert people[0]["review_status"] == "rejected"

    issues = store.review_issue_rows()
    assert issues[0]["status"] == "resolved"
