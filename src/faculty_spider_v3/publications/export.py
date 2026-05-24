from __future__ import annotations

import csv
import sqlite3
import re
from pathlib import Path
from typing import Iterable

from faculty_spider_v3.names.chinese_name import score_chinese_name

PAPER_FIELDS = [
    "id",
    "title",
    "journal",
    "achievement_level",
    "talent_pool_use",
    "year",
    "doi",
    "paper_url",
    "url",
    "source",
    "source_api_url",
    "first_author_name",
    "corresponding_author_names_json",
    "authors_json",
    "affiliations_json",
    "created_at",
    "updated_at",
]

CANDIDATE_FIELDS = [
    "name",
    "author_role",
    "paper_id",
    "title",
    "journal",
    "achievement_level",
    "year",
    "doi",
    "paper_url",
    "source",
    "affiliations",
    "is_likely_chinese_name",
    "chinese_name_score",
    "name_filter_reason",
]

PEOPLE_CANDIDATE_FIELDS = [
    "name",
    "affiliations",
    "last_5_year_total",
    "first_author_total",
    "corresponding_author_total",
    "top_total",
    "a_plus_total",
    "a_total",
    "a1_total",
    "a2_total",
    "level_counts_json",
    "paper_links",
    "paper_titles",
    "journals",
    "years",
    "author_roles",
    "is_likely_chinese_name",
    "chinese_name_score",
    "name_filter_reason",
    "review_status",
]

QUALITY_REPORT_FIELDS = [
    "journal",
    "achievement_level",
    "papers_count",
    "openalex_count",
    "crossref_count",
    "merged_count",
    "candidates_count",
    "chinese_candidates_count",
    "missing_author_count",
    "missing_affiliation_count",
    "source_errors",
]


def export_papers_csv(rows: Iterable[sqlite3.Row], path: str | Path) -> int:
    return _export_rows(rows, path, PAPER_FIELDS)


def export_publication_candidates_csv(
    rows: Iterable[dict[str, object]],
    path: str | Path,
    chinese_only: bool = False,
    accept_threshold: float = 0.7,
    review_threshold: float = 0.45,
) -> int:
    scored_rows = []
    for row in rows:
        score = score_chinese_name(str(row["name"]), context=str(row.get("affiliations", "")), accept_threshold=accept_threshold)
        if chinese_only and score.score < review_threshold:
            continue
        enriched = dict(row)
        enriched["is_likely_chinese_name"] = 1 if score.is_likely_chinese_name else 0
        enriched["chinese_name_score"] = score.score
        enriched["name_filter_reason"] = score.reason
        scored_rows.append(enriched)
    return _export_rows(scored_rows, path, CANDIDATE_FIELDS)


def export_publication_people_candidates_csv(
    rows: Iterable[dict[str, object]],
    path: str | Path,
    chinese_only: bool = True,
    accept_threshold: float = 0.7,
    review_threshold: float = 0.45,
) -> int:
    materialized = aggregate_publication_people_candidates(rows, chinese_only=chinese_only, accept_threshold=accept_threshold, review_threshold=review_threshold)
    return _export_rows(materialized, path, PEOPLE_CANDIDATE_FIELDS)


def export_publication_quality_report_csv(
    journals: Iterable[sqlite3.Row],
    paper_rows: Iterable[sqlite3.Row],
    candidate_rows: Iterable[dict[str, object]],
    review_issue_rows: Iterable[sqlite3.Row],
    path: str | Path,
) -> int:
    report = _publication_quality_report_rows(journals, paper_rows, candidate_rows, review_issue_rows)
    return _export_rows(report, path, QUALITY_REPORT_FIELDS)


def aggregate_publication_people_candidates(
    rows: Iterable[dict[str, object]],
    chinese_only: bool = True,
    accept_threshold: float = 0.7,
    review_threshold: float = 0.45,
) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        name = str(row["name"]).strip()
        if not name:
            continue
        score = score_chinese_name(name, context=str(row.get("affiliations", "")), accept_threshold=accept_threshold)
        if chinese_only and score.score < review_threshold:
            continue
        candidate = grouped.setdefault(name.casefold(), _empty_people_candidate(name, score))
        _merge_people_candidate_row(candidate, row)
        if score.score > float(candidate["chinese_name_score"]):
            candidate["chinese_name_score"] = score.score
            candidate["is_likely_chinese_name"] = 1 if score.is_likely_chinese_name else 0
            candidate["name_filter_reason"] = score.reason

    return _materialize_people_candidates(grouped.values())


def _materialize_people_candidates(candidates: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    materialized = []
    for candidate in candidates:
        candidate = dict(candidate)
        levels = candidate.pop("_level_counts")
        candidate["level_counts_json"] = _json_dumps(levels)
        candidate["affiliations"] = "; ".join(candidate.pop("_affiliations"))
        candidate["paper_links"] = " | ".join(candidate.pop("_paper_links"))
        candidate["paper_titles"] = " | ".join(candidate.pop("_paper_titles"))
        candidate["journals"] = " | ".join(candidate.pop("_journals"))
        candidate["years"] = " | ".join(candidate.pop("_years"))
        candidate["author_roles"] = " | ".join(candidate.pop("_author_roles"))
        candidate["review_status"] = _candidate_review_status(candidate)
        materialized.append(candidate)

    materialized.sort(
        key=lambda row: (
            -int(row["top_total"]),
            -int(row["a_plus_total"]),
            -int(row["last_5_year_total"]),
            str(row["name"]).casefold(),
        )
    )
    return materialized


def _publication_quality_report_rows(
    journals: Iterable[sqlite3.Row],
    paper_rows: Iterable[sqlite3.Row],
    candidate_rows: Iterable[dict[str, object]],
    review_issue_rows: Iterable[sqlite3.Row],
) -> list[dict[str, object]]:
    by_journal = {
        str(journal["journal_name"]): {
            "journal": journal["journal_name"],
            "achievement_level": journal["achievement_level"],
            "papers_count": 0,
            "openalex_count": 0,
            "crossref_count": 0,
            "merged_count": 0,
            "candidates_count": 0,
            "chinese_candidates_count": 0,
            "missing_author_count": 0,
            "missing_affiliation_count": 0,
            "source_errors": 0,
        }
        for journal in journals
    }
    aliases = {normalize_publication_name(name): name for name in by_journal}
    for paper in paper_rows:
        journal = aliases.get(normalize_publication_name(str(paper["journal"])))
        if not journal:
            continue
        row = by_journal[journal]
        row["papers_count"] += 1
        source = str(paper["source"] or "")
        if "openalex" in source:
            row["openalex_count"] += 1
        if "crossref" in source:
            row["crossref_count"] += 1
        if "openalex" in source and "crossref" in source:
            row["merged_count"] += 1
        if not paper["first_author_name"]:
            row["missing_author_count"] += 1
    for candidate in candidate_rows:
        journal = aliases.get(normalize_publication_name(str(candidate.get("journal", ""))))
        if not journal:
            continue
        row = by_journal[journal]
        row["candidates_count"] += 1
        score = score_chinese_name(str(candidate.get("name", "")), context=str(candidate.get("affiliations", "")))
        if score.score >= 0.45:
            row["chinese_candidates_count"] += 1
        if not str(candidate.get("affiliations", "")).strip():
            row["missing_affiliation_count"] += 1
    for issue in review_issue_rows:
        message = str(issue["message"])
        for normalized, journal in aliases.items():
            if normalized and normalized in normalize_publication_name(message):
                by_journal[journal]["source_errors"] += 1
                break
    return [
        row
        for row in by_journal.values()
        if row["papers_count"] or row["candidates_count"] or row["source_errors"]
    ]


def _export_rows(rows: Iterable, path: str | Path, fieldnames: list[str]) -> int:
    materialized = list(rows)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in materialized:
            writer.writerow({field: row[field] for field in fieldnames})
    return len(materialized)


def _empty_people_candidate(name: str, score) -> dict[str, object]:
    return {
        "name": name,
        "last_5_year_total": 0,
        "first_author_total": 0,
        "corresponding_author_total": 0,
        "top_total": 0,
        "a_plus_total": 0,
        "a_total": 0,
        "a1_total": 0,
        "a2_total": 0,
        "is_likely_chinese_name": 1 if score.is_likely_chinese_name else 0,
        "chinese_name_score": score.score,
        "name_filter_reason": score.reason,
        "_level_counts": {},
        "_affiliations": [],
        "_paper_links": [],
        "_paper_titles": [],
        "_journals": [],
        "_years": [],
        "_author_roles": [],
    }


def _merge_people_candidate_row(candidate: dict[str, object], row: dict[str, object]) -> None:
    candidate["last_5_year_total"] = int(candidate["last_5_year_total"]) + 1
    role = str(row.get("author_role", ""))
    if role == "first_author":
        candidate["first_author_total"] = int(candidate["first_author_total"]) + 1
    if role == "corresponding_author":
        candidate["corresponding_author_total"] = int(candidate["corresponding_author_total"]) + 1

    level = str(row.get("achievement_level", "")).strip()
    level_key = _level_key(level)
    if level_key:
        candidate["_level_counts"][level_key] = candidate["_level_counts"].get(level_key, 0) + 1
    if "TOP" in level.upper():
        candidate["top_total"] = int(candidate["top_total"]) + 1
    if level.startswith("A+"):
        candidate["a_plus_total"] = int(candidate["a_plus_total"]) + 1
    elif level == "A":
        candidate["a_total"] = int(candidate["a_total"]) + 1
    elif level == "A1":
        candidate["a1_total"] = int(candidate["a1_total"]) + 1
    elif level == "A2":
        candidate["a2_total"] = int(candidate["a2_total"]) + 1

    _append_unique(candidate["_affiliations"], str(row.get("affiliations", "")))
    _append_unique(candidate["_paper_links"], str(row.get("paper_url", "")))
    _append_unique(candidate["_paper_titles"], str(row.get("title", "")))
    _append_unique(candidate["_journals"], str(row.get("journal", "")))
    _append_unique(candidate["_years"], str(row.get("year", "")))
    _append_unique(candidate["_author_roles"], role)


def _append_unique(values: list[str], value: str) -> None:
    cleaned = " ".join(value.split())
    if cleaned and cleaned not in values:
        values.append(cleaned)


def _level_key(level: str) -> str:
    if not level:
        return ""
    if "TOP" in level.upper():
        return "TOP"
    return level


def _candidate_review_status(candidate: dict[str, object]) -> str:
    if int(candidate["is_likely_chinese_name"]) and (int(candidate["top_total"]) or int(candidate["a_plus_total"]) or int(candidate["last_5_year_total"]) >= 2):
        return "strong_candidate"
    if float(candidate["chinese_name_score"]) >= 0.45:
        return "needs_review"
    return "rejected"


def _json_dumps(value: dict[str, int]) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def normalize_publication_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
