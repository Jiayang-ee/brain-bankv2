"""Wave 1 review queue and quality gap report generation."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from faculty_spider_v3.storage import FacultySpiderV3Store

# ---------------------------------------------------------------------------
# Field definitions
# ---------------------------------------------------------------------------

# People-review CSV fields (P10 evidence fields + open issue + decision + notes)
WAVE1_REVIEW_FIELDS = [
    # Priority / sorting keys
    "priority_score",
    "priority_tier",          # high / medium / low / deferred
    # Person identity
    "person_id",
    "name",
    "school",
    "department",
    "title",
    "email",
    "personal_homepage",
    # Classification signals
    "primary_source_type",
    "confidence_score",
    "review_status",
    "discipline_score",
    "discipline_is_relevant",
    "discipline_review_status",
    # Publication stats (parsed from JSON columns)
    "pub_last_5_year_total",
    "pub_a_plus_total",
    "pub_a_total",
    "pub_a1_total",
    "pub_a2_total",
    "pub_top_total",
    "pub_first_author_total",
    "pub_corresponding_author_total",
    "pub_journals",
    "pub_years",
    # Evidence
    "source_url",
    "paper_links",
    # Open issues
    "open_issue_types",
    "open_issue_messages",
    "open_issue_source_urls",
    # Quality gap flags (for filtering / sorting)
    "gap_missing_school",
    "gap_missing_homepage",
    "gap_missing_email",
    "gap_low_confidence",
    "gap_name_conflict",
    "gap_discipline_uncertain",
    "gap_high_output_no_affiliation",
    # Write-back fields (empty on export, filled by human reviewer)
    "review_decision",
    "review_decision_note",
    "resolved_issue_types",
    "created_at",
    "updated_at",
]

# Quality gap summary report fields
QUALITY_GAP_FIELDS = [
    "gap_category",
    "gap_category_label",
    "severity",
    "count",
    "examples",
    "recommendation",
]


# ---------------------------------------------------------------------------
# Priority scoring
# ---------------------------------------------------------------------------

def _severity_weight(issue_type: str) -> int:
    """Map issue type to a severity weight (higher = more severe)."""
    weights = {
        "high_output_no_affiliation": 10,
        "missing_affiliation": 8,
        "low_confidence": 7,
        "name_filter_uncertain": 6,
        "publication_only_needs_review": 5,
        "weak_chinese_name_score": 4,
        "llm_used": 2,
    }
    return weights.get(issue_type, 1)


def _compute_priority_score(
    confidence_score: float,
    open_issue_types: list[str],
    missing_school: bool,
    missing_homepage: bool,
    missing_email: bool,
    discipline_review_status: str,
) -> float:
    """Compute a priority score for sorting (higher = more urgent to review)."""
    base = confidence_score * 10
    issue_penalty = sum(_severity_weight(t) for t in open_issue_types) * 0.5
    missing_penalty = (
        (2.0 if missing_school else 0)
        + (1.0 if missing_homepage else 0)
        + (1.5 if missing_email else 0)
    )
    discipline_penalty = 0 if discipline_review_status == "accepted" else 1.5
    return max(0, base - issue_penalty - missing_penalty - discipline_penalty)


def _tier_from_score(score: float) -> str:
    if score >= 8:
        return "high"
    if score >= 5:
        return "medium"
    if score >= 2:
        return "low"
    return "deferred"


def _parse_pub_stats(pub_stats_json: str) -> dict:
    try:
        return json.loads(pub_stats_json or "{}")
    except json.JSONDecodeError:
        return {}


def _gap_flags(person: dict, open_issue_types: list[str]) -> dict:
    return {
        "gap_missing_school": 1 if not (person.get("school") or "").strip() else 0,
        "gap_missing_homepage": 1 if not (person.get("personal_homepage") or "").strip() else 0,
        "gap_missing_email": 1 if not (person.get("email") or "").strip() else 0,
        "gap_low_confidence": 1 if float(person.get("confidence_score") or 0) < 0.6 else 0,
        "gap_name_conflict": 1 if "name_filter_uncertain" in open_issue_types else 0,
        "gap_discipline_uncertain": 1 if person.get("discipline_review_status") == "needs_review" and float(person.get("discipline_score") or 0) < 0.5 else 0,
        "gap_high_output_no_affiliation": 1 if "high_output_no_affiliation" in open_issue_types else 0,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def export_wave1_review_queue(
    people_rows: list,
    review_issue_rows: list,
    path: str | Path,
) -> dict:
    """
    Export the Wave 1 review queue CSV.

    Sorts by priority_score descending so highest-urgency records come first.
    Includes quality-gap flag columns so reviewers can filter in their tool.
    Returns a summary dict for the run record.
    """
    # Group open issues by person_id
    issue_buckets: dict[int, dict[str, list[str]]] = {}
    for row in review_issue_rows:
        pid = row["person_id"]
        if pid is None:
            continue
        bucket = issue_buckets.setdefault(pid, {"issue_types": [], "messages": [], "source_urls": []})
        bucket["issue_types"].append(row["issue_type"])
        bucket["messages"].append(row["message"])
        if row["source_url"]:
            bucket["source_urls"].append(row["source_url"])

    # Name conflict detection (name + school collisions)
    name_school_groups: dict[tuple[str, str], list] = {}
    for person in people_rows:
        key = (person.get("name", "") or "").strip().casefold(), (person.get("school", "") or "").strip().casefold()
        name_school_groups.setdefault(key, []).append(person["id"])

    # Sort people by priority_score descending
    scored = []
    for person in people_rows:
        pid = person["id"]
        bucket = issue_buckets.get(pid, {})
        issue_types = bucket.get("issue_types", [])
        gap = _gap_flags(person, issue_types)
        pub_stats = _parse_pub_stats(person.get("publication_stats_json", "{}"))
        score = _compute_priority_score(
            float(person.get("confidence_score") or 0),
            issue_types,
            bool(gap["gap_missing_school"]),
            bool(gap["gap_missing_homepage"]),
            bool(gap["gap_missing_email"]),
            person.get("discipline_review_status", ""),
        )
        scored.append((score, person, bucket, gap, pub_stats))

    scored.sort(key=lambda x: x[0], reverse=True)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    rows_written = 0
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=WAVE1_REVIEW_FIELDS, extrasaction="ignore")
        writer.writeheader()

        for score, person, bucket, gap, pub_stats in scored:
            issue_types = bucket.get("issue_types", [])
            journals = pub_stats.get("journals", [])
            years = pub_stats.get("years", [])

            row = {
                "priority_score": round(score, 3),
                "priority_tier": _tier_from_score(score),
                "person_id": person["id"],
                "name": person.get("name", ""),
                "school": person.get("school", ""),
                "department": person.get("department", ""),
                "title": person.get("title", ""),
                "email": person.get("email", ""),
                "personal_homepage": person.get("personal_homepage", ""),
                "primary_source_type": person.get("primary_source_type", ""),
                "confidence_score": person.get("confidence_score", ""),
                "review_status": person.get("review_status", ""),
                "discipline_score": person.get("discipline_score", ""),
                "discipline_is_relevant": person.get("discipline_is_relevant", ""),
                "discipline_review_status": person.get("discipline_review_status", ""),
                "pub_last_5_year_total": pub_stats.get("last_5_year_total", ""),
                "pub_a_plus_total": pub_stats.get("a_plus_total", ""),
                "pub_a_total": pub_stats.get("a_total", ""),
                "pub_a1_total": pub_stats.get("a1_total", ""),
                "pub_a2_total": pub_stats.get("a2_total", ""),
                "pub_top_total": pub_stats.get("top_total", ""),
                "pub_first_author_total": pub_stats.get("first_author_total", ""),
                "pub_corresponding_author_total": pub_stats.get("corresponding_author_total", ""),
                "pub_journals": " | ".join(journals[:5]) if journals else "",
                "pub_years": " | ".join(str(y) for y in years[:10]) if years else "",
                "source_url": person.get("source_url", ""),
                "paper_links": _format_paper_links(person.get("paper_links_json", "[]")),
                "open_issue_types": " | ".join(_uniq(issue_types)),
                "open_issue_messages": " || ".join(_uniq(bucket.get("messages", []))),
                "open_issue_source_urls": " | ".join(_uniq(bucket.get("source_urls", []))),
                "review_decision": person.get("review_decision", ""),
                "review_decision_note": person.get("review_decision_note", ""),
                "resolved_issue_types": "",
                "created_at": person.get("created_at", ""),
                "updated_at": person.get("updated_at", ""),
                **gap,
            }
            writer.writerow(row)
            rows_written += 1

    return {
        "review_queue_rows": rows_written,
        "review_queue_path": str(path),
    }


def _format_paper_links(paper_links_json: str) -> str:
    try:
        links = json.loads(paper_links_json or "[]")
    except json.JSONDecodeError:
        links = []
    return " | ".join(links[:20]) if links else ""


def _uniq(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for v in values:
        cleaned = " ".join(v.split())
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def export_wave1_quality_gap_report(
    people_rows: list,
    review_issue_rows: list,
    path: str | Path,
) -> dict:
    """
    Export the Wave 1 quality gap summary report.

    Covers the 7 gap categories required by P10:
    - 机构缺失 (missing school)
    - homepage/email 缺失
    - 低置信度 (low confidence)
    - 同名冲突 (name+school collisions)
    - 学科不确定 (discipline uncertain)
    - source_errors (from review_issues table)
    - abstract 缺失 (not applicable; stub kept for schema completeness)
    """
    # Build person lookup
    person_by_id = {p["id"]: p for p in people_rows}

    # Group issues by type
    issue_type_buckets: dict[str, list] = {}
    for row in review_issue_rows:
        itype = row["issue_type"] or "unknown"
        issue_type_buckets.setdefault(itype, []).append(row)

    # Name conflict detection
    name_school_groups: dict[tuple[str, str], list[int]] = {}
    for person in people_rows:
        key = (person.get("name", "") or "").strip().casefold(), (person.get("school", "") or "").strip().casefold()
        if key[0]:  # skip empty names
            name_school_groups.setdefault(key, []).append(person["id"])

    gaps = []

    # 1. 机构缺失
    missing_school = [p for p in people_rows if not (p.get("school") or "").strip()]
    gaps.append({
        "gap_category": "missing_school",
        "gap_category_label": "机构缺失",
        "severity": "high",
        "count": len(missing_school),
        "examples": "; ".join(f"{p['name']} ({p.get('source_url','')[:50]})" for p in missing_school[:3]),
        "recommendation": "补强机构信息：优先通过论文作者页、ORCID、Semantic Scholar 查找机构",
    })

    # 2. homepage/email 缺失
    missing_homepage = [p for p in people_rows if not (p.get("personal_homepage") or "").strip()]
    missing_email = [p for p in people_rows if not (p.get("email") or "").strip()]
    gaps.append({
        "gap_category": "missing_homepage_email",
        "gap_category_label": "homepage/email 缺失",
        "severity": "medium",
        "count": len(missing_homepage) + len(missing_email),
        "examples": f"homepage缺失: {len(missing_homepage)}, email缺失: {len(missing_email)}",
        "recommendation": "通过官网或 LinkedIn 补全 contact 信息，P12 优先级处理",
    })

    # 3. 低置信度
    low_conf = [p for p in people_rows if float(p.get("confidence_score") or 0) < 0.6]
    gaps.append({
        "gap_category": "low_confidence",
        "gap_category_label": "低置信度",
        "severity": "medium",
        "count": len(low_conf),
        "examples": "; ".join(f"{p['name']} (conf={p.get('confidence_score','')})" for p in low_conf[:3]),
        "recommendation": "低置信度记录人工复核时优先确认身份唯一性，避免同名误归并",
    })

    # 4. 同名冲突
    name_conflicts = [(k, v) for k, v in name_school_groups.items() if len(v) > 1]
    gaps.append({
        "gap_category": "name_conflict",
        "gap_category_label": "同名冲突",
        "severity": "high",
        "count": len(name_conflicts),
        "examples": "; ".join(f"{k[0]}@{k[1]} ({len(v)} records)" for k, v in name_conflicts[:3]),
        "recommendation": "同名冲突需人工确认是否为同一人，避免错误合并",
    })

    # 5. 学科不确定
    disc_uncertain = [
        p for p in people_rows
        if p.get("discipline_review_status") == "needs_review"
        and float(p.get("discipline_score") or 0) < 0.5
    ]
    gaps.append({
        "gap_category": "discipline_uncertain",
        "gap_category_label": "学科不确定",
        "severity": "medium",
        "count": len(disc_uncertain),
        "examples": "; ".join(f"{p['name']} (score={p.get('discipline_score','')})" for p in disc_uncertain[:3]),
        "recommendation": "学科评分低于 0.5 且状态为 needs_review 需人工确认相关性",
    })

    # 6. source_errors (from review_issues with severity high/medium)
    source_errors = [r for r in review_issue_rows if r.get("severity") in ("high", "medium")]
    gaps.append({
        "gap_category": "source_errors",
        "gap_category_label": "数据质量问题",
        "severity": "medium",
        "count": len(source_errors),
        "examples": "; ".join(f"{r['issue_type']}: {str(r.get('message',''))[:40]}" for r in source_errors[:3]),
        "recommendation": "高/中严重度数据问题优先修复，尤其是 affiliation 相关问题",
    })

    # 7. abstract 缺失 (not directly applicable; stub)
    gaps.append({
        "gap_category": "abstract_missing",
        "gap_category_label": "abstract 缺失",
        "severity": "low",
        "count": 0,
        "examples": "当前 pipeline 不采集 abstract，此项暂无数据",
        "recommendation": "如需 abstract 字段，后续可从 Crossref 或 Semantic Scholar 补充",
    })

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=QUALITY_GAP_FIELDS)
        writer.writeheader()
        for g in gaps:
            writer.writerow(g)

    return {
        "quality_gap_rows": len(gaps),
        "quality_gap_path": str(path),
    }


def generate_run_record(
    review_queue_result: dict,
    quality_gap_result: dict,
    run_id: str,
    git_commit: str,
    input_files: list[str],
    command: str,
    output_dir: str,
) -> dict:
    """Generate a run metadata JSON file next to the outputs."""
    record = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit,
        "command": command,
        "input_files": input_files,
        "outputs": {
            "review_queue": review_queue_result["review_queue_path"],
            "quality_gap_report": quality_gap_result["quality_gap_path"],
        },
        "summary": {
            "review_queue_rows": review_queue_result["review_queue_rows"],
            "quality_gap_categories": quality_gap_result["quality_gap_rows"],
        },
    }
    record_path = Path(output_dir) / "wave1_run_record.json"
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    record["run_record_path"] = str(record_path)
    return record


# Roster export fields (minimal identity + decision summary for downstream use)
ROSTER_FIELDS = [
    "person_id",
    "name",
    "school",
    "department",
    "title",
    "email",
    "personal_homepage",
    "primary_source_type",
    "review_status",
    "review_decision",
    "review_decision_note",
    "resolved_issue_types",
]


def _build_issue_buckets(review_issue_rows: list) -> dict:
    """Group resolved review issues by person_id for roster export."""
    buckets: dict = {}
    for row in review_issue_rows:
        pid = row["person_id"]
        if pid is None:
            continue
        # Only include resolved issues in the roster resolved_issue_types field
        if row.get("status") != "resolved":
            continue
        bucket = buckets.setdefault(pid, {"issue_types": [], "messages": [], "source_urls": []})
        bucket["issue_types"].append(row["issue_type"])
        bucket["messages"].append(row["message"])
        if row.get("source_url"):
            bucket["source_urls"].append(row["source_url"])
    return buckets


def export_review_roster(
    people_rows: list,
    review_issue_rows: list,
    output_dir: str | Path,
    batch_name: str,
) -> dict:
    """
    Export confirmed / deferred / rejected rosters from reviewed people.

    confirmed : review_status in ('accepted', 'approved')
    deferred  : review_status == 'needs_review'
    rejected : review_status == 'rejected'
    Empty / new review_status is excluded from all rosters.

    Roster files are named: <output_dir>/<batch_name>_confirmed.csv (etc.)
    Returns a summary dict with counts per roster type.
    """
    buckets = _build_issue_buckets(review_issue_rows)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rosters = {"confirmed": [], "deferred": [], "rejected": []}

    for person in people_rows:
        pid = person["id"]
        status = (person.get("review_status") or "").strip().lower()
        bucket = buckets.get(pid, {})
        resolved = bucket.get("issue_types", [])

        if status in ("accepted", "approved"):
            rosters["confirmed"].append(_roster_row(person, resolved))
        elif status == "needs_review":
            rosters["deferred"].append(_roster_row(person, resolved))
        elif status == "rejected":
            rosters["rejected"].append(_roster_row(person, resolved))

    result = {}
    for roster_name, rows in rosters.items():
        filename = f"{batch_name}_{roster_name}.csv"
        filepath = output_dir / filename
        with filepath.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=ROSTER_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        result[roster_name] = {"path": str(filepath), "count": len(rows)}

    return result


def _roster_row(person: dict, resolved_issue_types: list[str]) -> dict:
    return {
        "person_id": person["id"],
        "name": person.get("name", ""),
        "school": person.get("school", ""),
        "department": person.get("department", ""),
        "title": person.get("title", ""),
        "email": person.get("email", ""),
        "personal_homepage": person.get("personal_homepage", ""),
        "primary_source_type": person.get("primary_source_type", ""),
        "review_status": person.get("review_status", ""),
        "review_decision": person.get("review_decision", ""),
        "review_decision_note": person.get("review_decision_note", ""),
        "resolved_issue_types": " | ".join(resolved_issue_types),
    }


def get_git_commit(cwd: str | Path | None = None) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=cwd,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"