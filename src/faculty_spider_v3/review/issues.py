from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Iterable


ISSUE_FIELDS = [
    "id",
    "person_id",
    "related_table",
    "related_id",
    "issue_type",
    "severity",
    "message",
    "source_url",
    "status",
    "created_at",
    "resolved_at",
]

# Fields for the people_review CSV (human-review-oriented export).
PEOPLE_REVIEW_FIELDS = [
    # person identity
    "person_id",
    "name",
    "school",
    "department",
    "title",
    "email",
    "personal_homepage",
    # classification signals
    "review_status",
    "is_likely_chinese_name",
    "chinese_name_score",
    "name_filter_reason",
    "discipline_score",
    "discipline_is_relevant",
    "discipline_review_status",
    "discipline_reason",
    # publication stats
    "publication_stats_json",
    "paper_links_json",
    # evidence
    "source_url",
    "primary_source_type",
    "confidence_score",
    # open review issues for this person
    "open_issue_types",
    "open_issue_messages",
    "open_issue_source_urls",
    "created_at",
    "updated_at",
]


def export_review_issues_csv(rows: Iterable[sqlite3.Row], path: str | Path) -> int:
    materialized = list(rows)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ISSUE_FIELDS)
        writer.writeheader()
        for row in materialized:
            writer.writerow({field: row[field] for field in ISSUE_FIELDS})
    return len(materialized)


def _open_issue_buckets(rows: Iterable[sqlite3.Row]) -> dict[int, dict[str, list[str]]]:
    """Group open review issues by person_id."""
    buckets: dict[int, dict[str, list[str]]] = {}
    for row in rows:
        pid = row["person_id"]
        if pid is None:
            continue
        issue_types = buckets.setdefault(pid, {}).setdefault("issue_types", [])
        issue_messages = buckets.setdefault(pid, {}).setdefault("messages", [])
        issue_urls = buckets.setdefault(pid, {}).setdefault("source_urls", [])
        issue_types.append(row["issue_type"])
        issue_messages.append(row["message"])
        if row["source_url"]:
            issue_urls.append(row["source_url"])
    return buckets


def export_people_review_csv(
    people_rows: Iterable[sqlite3.Row],
    review_issue_rows: Iterable[sqlite3.Row],
    path: str | Path,
) -> int:
    """
    Export a people-review CSV with fields suitable for human judgment,
    sorting, and annotated write-back.

    - ``people_rows`` emit all person fields from the people table.
    - ``review_issue_rows`` are filtered to *open* issues; they are grouped
      by ``person_id`` to populate the per-row issue summary columns.
    """
    materialized = list(people_rows)
    issue_buckets = _open_issue_buckets(review_issue_rows)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PEOPLE_REVIEW_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for person in materialized:
            pid = person["id"]
            bucket = issue_buckets.get(pid, {})
            person_dict = dict(person)

            paper_links = person_dict.get("paper_links_json", "[]")
            try:
                paper_links_parsed = json.loads(paper_links) if paper_links else []
            except json.JSONDecodeError:
                paper_links_parsed = []

            row = {
                "person_id": pid,
                "name": person_dict.get("name", ""),
                "school": person_dict.get("school", ""),
                "department": person_dict.get("department", ""),
                "title": person_dict.get("title", ""),
                "email": person_dict.get("email", ""),
                "personal_homepage": person_dict.get("personal_homepage", ""),
                "review_status": person_dict.get("review_status", ""),
                "is_likely_chinese_name": person_dict.get("is_likely_chinese_name", 0),
                "chinese_name_score": person_dict.get("chinese_name_score", 0.0),
                "name_filter_reason": person_dict.get("name_filter_reason", ""),
                "discipline_score": person_dict.get("discipline_score", 0.0),
                "discipline_is_relevant": person_dict.get("discipline_is_relevant", 0),
                "discipline_review_status": person_dict.get("discipline_review_status", ""),
                "discipline_reason": person_dict.get("discipline_reason", ""),
                "publication_stats_json": person_dict.get("publication_stats_json", "{}"),
                "paper_links_json": json.dumps(paper_links_parsed),
                "source_url": person_dict.get("source_url", ""),
                "primary_source_type": person_dict.get("primary_source_type", ""),
                "confidence_score": person_dict.get("confidence_score", 0.0),
                "open_issue_types": " | ".join(_uniq(bucket.get("issue_types", []))),
                "open_issue_messages": " || ".join(_uniq(bucket.get("messages", []))),
                "open_issue_source_urls": " | ".join(_uniq(bucket.get("source_urls", []))),
                "created_at": person_dict.get("created_at", ""),
                "updated_at": person_dict.get("updated_at", ""),
            }
            writer.writerow(row)

    return len(materialized)


def _uniq(values: list[str]) -> list[str]:
    """Preserve order, remove empties."""
    seen: set[str] = set()
    result = []
    for v in values:
        cleaned = " ".join(v.split())
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result