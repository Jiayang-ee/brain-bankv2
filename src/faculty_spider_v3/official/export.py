from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Iterable


PEOPLE_FIELDS = [
    "id",
    "name",
    "age",
    "career_stage",
    "email",
    "school",
    "department",
    "field",
    "research_direction",
    "title",
    "source_url",
    "primary_source_type",
    "personal_homepage",
    "research_interests",
    "biography",
    "publications_json",
    "publication_stats_json",
    "paper_links_json",
    "photo_url",
    "photo_path",
    "education",
    "advisor",
    "confidence_score",
    "review_status",
    "is_likely_chinese_name",
    "chinese_name_score",
    "name_filter_reason",
    "discipline_score",
    "discipline_is_relevant",
    "discipline_review_status",
    "discipline_matched_disciplines_json",
    "discipline_matched_keywords_json",
    "discipline_negative_keywords_json",
    "discipline_reason",
    "created_at",
    "updated_at",
]

PAGE_AUDIT_FIELDS = [
    "id",
    "school",
    "department",
    "page_type",
    "status_code",
    "fetch_error",
    "parser_status",
    "llm_status",
    "raw_html_path",
    "url",
    "source_url",
    "fetched_at",
    "updated_at",
]


def export_people_csv(rows: Iterable[sqlite3.Row], path: str | Path) -> int:
    return _export_rows(rows, path, PEOPLE_FIELDS)


def export_page_audit_csv(rows: Iterable[sqlite3.Row], path: str | Path) -> int:
    return _export_rows(rows, path, PAGE_AUDIT_FIELDS)


def _export_rows(rows: Iterable[sqlite3.Row], path: str | Path, fieldnames: list[str]) -> int:
    materialized = list(rows)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in materialized:
            writer.writerow({field: row[field] for field in fieldnames})
    return len(materialized)
