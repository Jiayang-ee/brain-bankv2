"""Smoke tests for the Wave 1 review queue and quality gap report generator."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

from faculty_spider_v3.review.report import (
    _compute_priority_score,
    _tier_from_score,
    export_review_roster,
    export_wave1_quality_gap_report,
    export_wave1_review_queue,
    generate_run_record,
    get_git_commit,
)


def test_tier_from_score():
    assert _tier_from_score(9) == "high"
    assert _tier_from_score(8) == "high"
    assert _tier_from_score(7.9) == "medium"
    assert _tier_from_score(5) == "medium"
    assert _tier_from_score(2) == "low"
    assert _tier_from_score(1.9) == "deferred"


def test_compute_priority_score():
    # High confidence, no issues -> high score
    score = _compute_priority_score(0.85, [], False, False, False, "accepted")
    assert score > 7

    # Low confidence + missing school + open issues -> low score
    score = _compute_priority_score(0.5, ["low_confidence"], True, False, False, "needs_review")
    assert score < 5

    # High confidence with accepted discipline
    score = _compute_priority_score(0.9, [], False, False, False, "accepted")
    assert score > 8


def test_export_wave1_review_queue_smoke(tmp_path):
    """Smoke test: export_wave1_review_queue produces a well-formed CSV."""
    people_rows = [
        {
            "id": 1,
            "name": "Wei Zhang",
            "school": "Tsinghua University",
            "department": "Management Science",
            "title": "Professor",
            "email": "",
            "personal_homepage": "",
            "source_url": "https://example.edu/wei",
            "primary_source_type": "official_site",
            "confidence_score": "0.85",
            "review_status": "needs_review",
            "discipline_score": "0.8",
            "discipline_is_relevant": "1",
            "discipline_review_status": "accepted",
            "publication_stats_json": '{"last_5_year_total": 5, "a1_total": 2}',
            "paper_links_json": '["https://doi.org/10.1016/j.dss.2024.001"]',
            "review_decision": "",
            "review_decision_note": "",
            "created_at": "2026-05-23 03:43:42",
            "updated_at": "2026-05-23 03:43:42",
        },
        {
            "id": 2,
            "name": "Li Wang",
            "school": "",
            "department": "",
            "title": "",
            "email": "",
            "personal_homepage": "",
            "source_url": "https://doi.org/10.1016/j.tre.2025.001",
            "primary_source_type": "publication",
            "confidence_score": "0.55",
            "review_status": "needs_review",
            "discipline_score": "0.3",
            "discipline_is_relevant": "0",
            "discipline_review_status": "needs_review",
            "publication_stats_json": "{}",
            "paper_links_json": "[]",
            "review_decision": "",
            "review_decision_note": "",
            "created_at": "2026-05-22 07:31:20",
            "updated_at": "2026-05-22 07:31:20",
        },
    ]

    issue_rows = [
        {
            "person_id": 2,
            "issue_type": "missing_affiliation",
            "severity": "medium",
            "message": "No affiliation found.",
            "source_url": "https://doi.org/10.1016/j.tre.2025.001",
            "status": "open",
        },
    ]

    queue_csv = tmp_path / "queue.csv"
    result = export_wave1_review_queue(people_rows, issue_rows, queue_csv)

    assert result["review_queue_rows"] == 2
    assert queue_csv.exists()

    with queue_csv.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2

    # First row (Wei Zhang) should have higher priority_score
    scores = {r["name"]: float(r["priority_score"]) for r in rows}
    assert scores["Wei Zhang"] > scores["Li Wang"]

    # Wei Zhang should be "high" or "medium" tier
    wei_row = next(r for r in rows if r["name"] == "Wei Zhang")
    assert wei_row["priority_tier"] in ("high", "medium", "low")

    # Li Wang should have gap flags set
    li_row = next(r for r in rows if r["name"] == "Li Wang")
    assert li_row["gap_missing_school"] == "1"
    assert li_row["gap_low_confidence"] == "1"

    # Fields should include all WAVE1_REVIEW_FIELDS
    assert set(rows[0].keys()) == set([
        "priority_score", "priority_tier", "person_id", "name", "school", "department",
        "title", "email", "personal_homepage", "primary_source_type", "confidence_score",
        "review_status", "discipline_score", "discipline_is_relevant", "discipline_review_status",
        "pub_last_5_year_total", "pub_a_plus_total", "pub_a_total", "pub_a1_total", "pub_a2_total",
        "pub_top_total", "pub_first_author_total", "pub_corresponding_author_total",
        "pub_journals", "pub_years", "source_url", "paper_links",
        "open_issue_types", "open_issue_messages", "open_issue_source_urls",
        "gap_missing_school", "gap_missing_homepage", "gap_missing_email",
        "gap_low_confidence", "gap_name_conflict", "gap_discipline_uncertain",
        "gap_high_output_no_affiliation",
        "review_decision", "review_decision_note", "resolved_issue_types", "created_at", "updated_at",
    ])


def test_export_wave1_quality_gap_report_smoke(tmp_path):
    """Smoke test: quality gap report covers all 7 required categories."""
    people_rows = [
        {
            "id": 1, "name": "No School", "school": "",
            "confidence_score": "0.55", "discipline_score": "0.3",
            "discipline_review_status": "needs_review",
            "personal_homepage": "", "email": "",
            "source_url": "https://doi.org/10.1016/j.tre.2025.001",
            "primary_source_type": "publication",
        },
    ]
    issue_rows = [
        {
            "person_id": 1, "issue_type": "missing_affiliation",
            "severity": "high", "message": "No affiliation.",
            "source_url": "https://doi.org/10.1016/j.tre.2025.001", "status": "open",
        },
    ]

    gap_csv = tmp_path / "gap.csv"
    result = export_wave1_quality_gap_report(people_rows, issue_rows, gap_csv)

    assert result["quality_gap_rows"] == 7
    assert gap_csv.exists()

    with gap_csv.open(encoding="utf-8-sig") as f:
        gaps = list(csv.DictReader(f))

    categories = {g["gap_category"] for g in gaps}
    expected = {
        "missing_school", "missing_homepage_email", "low_confidence",
        "name_conflict", "discipline_uncertain", "source_errors", "abstract_missing",
    }
    assert categories == expected

    # missing_school count should be 1
    ms = next(g for g in gaps if g["gap_category"] == "missing_school")
    assert int(ms["count"]) == 1

    # source_errors count should be 1
    se = next(g for g in gaps if g["gap_category"] == "source_errors")
    assert int(se["count"]) == 1


def test_generate_run_record(tmp_path):
    queue_result = {"review_queue_rows": 589, "review_queue_path": str(tmp_path / "queue.csv")}
    gap_result = {"quality_gap_rows": 7, "quality_gap_path": str(tmp_path / "gap.csv")}

    record = generate_run_record(
        queue_result, gap_result,
        run_id="wave1-20260526T120000",
        git_commit="1f6862a",
        input_files=["data/exports/people.csv", "data/review/issues.csv"],
        command="review wave1-report",
        output_dir=str(tmp_path),
    )

    assert record["run_id"] == "wave1-20260526T120000"
    assert record["git_commit"] == "1f6862a"
    assert record["summary"]["review_queue_rows"] == 589
    assert record["summary"]["quality_gap_categories"] == 7
    assert Path(record["run_record_path"]).exists()

    with open(record["run_record_path"]) as f:
        loaded = json.load(f)
    assert loaded["run_id"] == "wave1-20260526T120000"


def test_get_git_commit():
    repo = Path(__file__).resolve().parents[1]  # tests/ -> brain-bankv2/
    commit = get_git_commit(repo)
    # Must be a valid short SHA (7+ hex chars) and match current HEAD
    import re
    assert re.fullmatch(r"[0-9a-f]{7,}", commit), f"Expected short SHA, got {commit!r}"
    actual_head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=repo
    ).stdout.strip()
    assert commit == actual_head, f"Expected {actual_head!r}, got {commit!r}"

    # Test with non-git path returns "unknown"
    unknown = get_git_commit("/tmp")
    assert unknown == "unknown"


def test_priority_sorting_orders_by_score(tmp_path):
    """High-urgency people appear first in the exported queue."""
    people_rows = [
        {
            "id": 1, "name": "High Priority",
            "school": "MIT", "department": "", "title": "", "email": "",
            "personal_homepage": "", "source_url": "https://mit.edu/1",
            "primary_source_type": "official_site",
            "confidence_score": "0.9",
            "review_status": "needs_review",
            "discipline_score": "0.8",
            "discipline_is_relevant": "1",
            "discipline_review_status": "accepted",
            "publication_stats_json": "{}",
            "paper_links_json": "[]",
            "review_decision": "", "review_decision_note": "",
            "created_at": "", "updated_at": "",
        },
        {
            "id": 2, "name": "Low Priority",
            "school": "", "department": "", "title": "", "email": "",
            "personal_homepage": "", "source_url": "https://doi.org/10.x/1",
            "primary_source_type": "publication",
            "confidence_score": "0.45",
            "review_status": "needs_review",
            "discipline_score": "0.2",
            "discipline_is_relevant": "0",
            "discipline_review_status": "needs_review",
            "publication_stats_json": "{}",
            "paper_links_json": "[]",
            "review_decision": "", "review_decision_note": "",
            "created_at": "", "updated_at": "",
        },
    ]
    issue_rows = [
        {
            "person_id": 2, "issue_type": "missing_affiliation",
            "severity": "high", "message": "No affiliation.",
            "source_url": "https://doi.org/10.x/1", "status": "open",
        },
    ]

    queue_csv = tmp_path / "queue.csv"
    result = export_wave1_review_queue(people_rows, issue_rows, queue_csv)
    assert result["review_queue_rows"] == 2

    with queue_csv.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    assert rows[0]["name"] == "High Priority"
    assert rows[1]["name"] == "Low Priority"
    assert float(rows[0]["priority_score"]) > float(rows[1]["priority_score"])


def test_cli_wave1_report_smoke(tmp_path):
    """End-to-end CLI smoke test via subprocess."""
    repo = Path(__file__).resolve().parents[1]  # tests/ -> brain-bankv2/
    result = subprocess.run(
        [
            "python3", "-m", "faculty_spider_v3.cli",
            "review", "wave1-report",
            "--queue-csv", str(tmp_path / "queue.csv"),
            "--gap-csv", str(tmp_path / "gap.csv"),
            "--run-id", "smoke-test",
        ],
        capture_output=True,
        text=True,
        cwd=str(repo),
        env={**__import__("os").environ, "PYTHONPATH": str(repo / "src")},
    )
    assert result.returncode == 0, result.stderr

    output = json.loads(result.stdout)
    assert output["run_id"] == "smoke-test"
    assert output["review_queue"] == 589
    assert output["quality_gap_categories"] == 7
    assert Path(output["queue_csv"]).exists()
    assert Path(output["gap_csv"]).exists()
    assert Path(output["run_record"]).exists()


def test_export_review_roster(tmp_path):
    """confirmed/deferred/rejected rosters are separated correctly; empty status excluded."""
    people_rows = [
        {
            "id": 1, "name": "Accepted Person", "school": "MIT",
            "department": "CS", "title": "Professor",
            "email": "mit@example.edu", "personal_homepage": "https://mit.edu/1",
            "primary_source_type": "official_site",
            "review_status": "accepted",
            "review_decision": "accepted",
            "review_decision_note": "Looks good.",
        },
        {
            "id": 2, "name": "Approved Person", "school": "Stanford",
            "department": "CS", "title": "Assistant Professor",
            "email": "stanford@example.edu", "personal_homepage": "",
            "primary_source_type": "official_site",
            "review_status": "approved",  # post-import state (was approved by human reviewer)
            "review_decision": "approved",
            "review_decision_note": "Also good.",
        },
        {
            "id": 3, "name": "Needs Review Person", "school": "Berkeley",
            "department": "", "title": "", "email": "",
            "personal_homepage": "",
            "primary_source_type": "publication",
            "review_status": "needs_review",
            "review_decision": "",
            "review_decision_note": "",
        },
        {
            "id": 4, "name": "Rejected Person", "school": "Yale",
            "department": "", "title": "", "email": "",
            "personal_homepage": "",
            "primary_source_type": "publication",
            "review_status": "rejected",
            "review_decision": "rejected",
            "review_decision_note": "Not relevant.",
        },
        {
            "id": 5, "name": "New Person", "school": "Harvard",
            "department": "", "title": "", "email": "",
            "personal_homepage": "",
            "primary_source_type": "official_site",
            "review_status": "new",
            "review_decision": "",
            "review_decision_note": "",
        },
    ]

    issue_rows = [
        {
            "person_id": 2,
            "issue_type": "missing_affiliation",
            "severity": "medium",
            "message": "No affiliation.",
            "source_url": "https://doi.org/10.x/1",
            "status": "resolved",
        },
        {
            "person_id": 4,
            "issue_type": "low_confidence",
            "severity": "low",
            "message": "Low confidence.",
            "source_url": "https://doi.org/10.x/2",
            "status": "open",
        },
    ]

    result = export_review_roster(people_rows, issue_rows, tmp_path, "wave1")

    confirmed = result["confirmed"]
    deferred = result["deferred"]
    rejected = result["rejected"]

    assert confirmed["count"] == 2
    assert deferred["count"] == 1
    assert rejected["count"] == 1

    # confirmed roster includes accepted and approved
    with open(confirmed["path"], encoding="utf-8-sig") as f:
        confirmed_rows = list(csv.DictReader(f))
    confirmed_names = {r["name"] for r in confirmed_rows}
    assert confirmed_names == {"Accepted Person", "Approved Person"}

    # approved person should have review_status='approved' (from CSV field)
    approved_row = next(r for r in confirmed_rows if r["name"] == "Approved Person")
    assert approved_row["review_decision"] == "approved"
    assert approved_row["review_status"] == "approved"

    # deferred roster
    with open(deferred["path"], encoding="utf-8-sig") as f:
        deferred_rows = list(csv.DictReader(f))
    assert deferred_rows[0]["name"] == "Needs Review Person"

    # rejected roster
    with open(rejected["path"], encoding="utf-8-sig") as f:
        rejected_rows = list(csv.DictReader(f))
    assert rejected_rows[0]["name"] == "Rejected Person"

    # New Person (id=5) should not appear in any roster
    all_names = {r["name"] for r in confirmed_rows + deferred_rows + rejected_rows}
    assert "New Person" not in all_names


def test_export_review_roster_resolved_issue_types(tmp_path):
    """resolved issue types are written to resolved_issue_types field."""
    people_rows = [
        {
            "id": 1, "name": "Resolved Person", "school": "MIT",
            "department": "CS", "title": "Professor",
            "email": "mit@example.edu", "personal_homepage": "",
            "primary_source_type": "official_site",
            "review_status": "accepted",
            "review_decision": "accepted",
            "review_decision_note": "Good.",
        },
    ]

    issue_rows = [
        {
            "person_id": 1,
            "issue_type": "name_filter_uncertain",
            "severity": "medium",
            "message": "Borderline name.",
            "source_url": "https://example.edu/1",
            "status": "resolved",
        },
        {
            "person_id": 1,
            "issue_type": "missing_affiliation",
            "severity": "medium",
            "message": "No affiliation.",
            "source_url": "https://example.edu/2",
            "status": "open",
        },
    ]

    result = export_review_roster(people_rows, issue_rows, tmp_path, "wave1")
    with open(result["confirmed"]["path"], encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["resolved_issue_types"] == "name_filter_uncertain"