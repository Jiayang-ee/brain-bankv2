from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from faculty_spider_v3.config import EXPORT_DIR, SEED_DIR
from faculty_spider_v3.publications.crossref import CrossrefClient
from faculty_spider_v3.publications.export import (
    export_papers_csv,
    export_publication_candidates_csv,
    export_publication_people_candidates_csv,
    export_publication_quality_report_csv,
    normalize_publication_name,
)
from faculty_spider_v3.publications.openalex import OpenAlexClient, default_from_year
from faculty_spider_v3.publications.pipeline import search_publications_for_journal
from faculty_spider_v3.storage import FacultySpiderV3Store, normalize_text

DEFAULT_GROUPS_CSV = SEED_DIR / "publication_journal_groups.csv"


@dataclass(frozen=True)
class QualityGateThresholds:
    """可配置的期刊级质量门禁阈值。"""

    # 华人候选比例门禁（低于此值标记 needs_review）
    chinese_candidate_min_ratio: float = 0.10
    # 缺第一作者姓名的论文比例上限（超过此值标记 needs_review）
    missing_author_max_ratio: float = 0.30
    # 缺机构的候选人比例上限（超过此值标记 needs_review）
    missing_affiliation_max_ratio: float = 0.50
    # source error 次数上限（超过此值标记 needs_review）
    source_errors_max: int = 5
    # 单期刊最少论文数（低于此值标记 needs_review）
    min_papers_per_journal: int = 3


# 默认阈值（default_batch 使用）
DEFAULT_GATE_THRESHOLDS = QualityGateThresholds()


@dataclass
class JournalGateResult:
    """单个期刊的质量门禁检查结果。"""

    journal_name: str
    passed: bool
    chinese_candidate_ratio: float = 0.0
    missing_author_ratio: float = 0.0
    missing_affiliation_ratio: float = 0.0
    source_errors: int = 0
    papers_count: int = 0
    failures: tuple[str, ...] = ()
    review_reason: str = ""


def check_quality_gate(
    journals: list[dict[str, object]],
    paper_rows: list[dict[str, object]],
    candidate_rows: list[dict[str, object]],
    review_issue_rows: list[dict[str, object]],
    thresholds: QualityGateThresholds = DEFAULT_GATE_THRESHOLDS,
) -> dict[int, JournalGateResult]:
    """
    对一批期刊执行质量门禁检查。

    返回值：{journal_id: JournalGateResult}
    """
    # 按期刊名建立索引
    aliases = {normalize_publication_name(str(j["journal_name"])): str(j["journal_name"]) for j in journals}
    name_to_id = {str(j["journal_name"]): int(j["id"]) for j in journals}

    # 汇总论文和候选人统计
    stats: dict[str, dict[str, int]] = {name: {"papers": 0, "missing_author": 0, "candidates": 0, "missing_affiliation": 0, "chinese_candidates": 0} for name in aliases.values()}
    error_count: dict[str, int] = {name: 0 for name in aliases.values()}

    for paper in paper_rows:
        journal = aliases.get(normalize_publication_name(str(paper.get("journal", ""))))
        if not journal:
            continue
        stats[journal]["papers"] += 1
        if not str(paper.get("first_author_name", "")).strip():
            stats[journal]["missing_author"] += 1

    for candidate in candidate_rows:
        journal = aliases.get(normalize_publication_name(str(candidate.get("journal", ""))))
        if not journal:
            continue
        stats[journal]["candidates"] += 1
        if not str(candidate.get("affiliations", "")).strip():
            stats[journal]["missing_affiliation"] += 1
        score = _chinese_name_score(candidate)
        if score >= 0.45:
            stats[journal]["chinese_candidates"] += 1

    for issue in review_issue_rows:
        message = str(issue["message"])
        for normalized, journal in aliases.items():
            if normalized and normalized in normalize_publication_name(message):
                error_count[journal] += 1
                break

    results: dict[int, JournalGateResult] = {}
    for journal_name, s in stats.items():
        papers = s["papers"]
        candidates = s["candidates"]
        failures: list[str] = []

        # 论文数检查
        if papers < thresholds.min_papers_per_journal:
            failures.append(f"papers_below_min({papers}<{thresholds.min_papers_per_journal})")

        # 华人候选比例检查
        if candidates > 0:
            ratio = s["chinese_candidates"] / candidates
            if ratio < thresholds.chinese_candidate_min_ratio:
                failures.append(f"chinese_ratio_low({ratio:.2f}<{thresholds.chinese_candidate_min_ratio})")
        elif papers > 0:
            # 有论文但无候选（极端情况）
            failures.append("no_candidates")

        # 缺作者比例检查
        if papers > 0:
            ratio = s["missing_author"] / papers
            if ratio > thresholds.missing_author_max_ratio:
                failures.append(f"missing_author_ratio_high({ratio:.2f}>{thresholds.missing_author_max_ratio})")

        # 缺机构比例检查
        if candidates > 0:
            ratio = s["missing_affiliation"] / candidates
            if ratio > thresholds.missing_affiliation_max_ratio:
                failures.append(f"missing_affiliation_ratio_high({ratio:.2f}>{thresholds.missing_affiliation_max_ratio})")

        # source error 检查
        errors = error_count.get(journal_name, 0)
        if errors > thresholds.source_errors_max:
            failures.append(f"source_errors_high({errors}>{thresholds.source_errors_max})")

        passed = len(failures) == 0
        journal_id = name_to_id.get(journal_name, 0)

        candidates_count = max(candidates, 1)
        results[journal_id] = JournalGateResult(
            journal_name=journal_name,
            passed=passed,
            chinese_candidate_ratio=s["chinese_candidates"] / candidates_count,
            missing_author_ratio=s["missing_author"] / max(papers, 1),
            missing_affiliation_ratio=s["missing_affiliation"] / candidates_count,
            source_errors=errors,
            papers_count=papers,
            failures=tuple(failures),
            review_reason="; ".join(failures) if failures else "passed",
        )

    return results


def _chinese_name_score(candidate: dict[str, object]) -> float:
    """从候选人行中提取或计算中文姓名评分。"""
    return float(candidate.get("chinese_name_score", 0.0))


@dataclass(frozen=True)
class PublicationBatchResult:
    run_id: int
    status: str
    items_processed: int
    items_skipped: int
    papers_seen: int
    papers_saved: int
    errors: int


def create_publication_batch(
    store: FacultySpiderV3Store,
    journal_group: str,
    from_year: int | None = None,
    works_per_journal: int = 50,
    sources: tuple[str, ...] = ("openalex", "crossref"),
    groups_csv: str | Path = DEFAULT_GROUPS_CSV,
    run_name: str = "",
    max_journals: int | None = None,
) -> int:
    from_year = from_year or default_from_year(date.today())
    source_text = ",".join(sources)
    run_name = run_name or f"{journal_group}-{from_year}-{works_per_journal}"
    journals = journals_for_group(store, groups_csv, journal_group, max_journals=max_journals)
    run_id = store.create_publication_run(run_name, journal_group, from_year, works_per_journal, source_text)
    store.add_publication_run_items(run_id, journals)
    return run_id


def run_publication_batch(
    store: FacultySpiderV3Store,
    journal_group: str,
    from_year: int | None = None,
    works_per_journal: int = 50,
    sources: tuple[str, ...] = ("openalex", "crossref"),
    groups_csv: str | Path = DEFAULT_GROUPS_CSV,
    run_id: int | None = None,
    resume: bool = False,
    run_name: str = "",
    max_journals: int | None = None,
    refresh_exports: bool = True,
) -> PublicationBatchResult:
    from_year = from_year or default_from_year(date.today())
    source_text = ",".join(sources)
    if run_id is None and resume:
        existing = store.latest_resumable_publication_run(journal_group, from_year, works_per_journal, source_text)
        run_id = int(existing["id"]) if existing else None
    if run_id is None:
        run_id = create_publication_batch(
            store,
            journal_group=journal_group,
            from_year=from_year,
            works_per_journal=works_per_journal,
            sources=sources,
            groups_csv=groups_csv,
            run_name=run_name,
            max_journals=max_journals,
        )

    run = store.get_publication_run(run_id)
    if run is None:
        raise ValueError(f"Publication run not found: {run_id}")
    sources = tuple(source.strip() for source in str(run["sources"]).split(",") if source.strip())

    store.update_publication_run_status(run_id, "running", started=True)
    items = store.publication_run_items(run_id, include_completed=False)
    openalex = OpenAlexClient() if "openalex" in sources else None
    crossref = CrossrefClient() if "crossref" in sources else None
    processed = 0
    skipped = 0
    papers_seen = 0
    papers_saved = 0
    errors = 0
    source_count = max(len(sources), 1)

    for item in items:
        if item["status"] == "completed":
            skipped += 1
            continue
        journal = store.get_journal(int(item["journal_id"]))
        if journal is None:
            store.finish_publication_run_item(item["id"], "failed", 0, 0, "journal row missing")
            errors += 1
            processed += 1
            continue
        store.start_publication_run_item(item["id"])
        result = search_publications_for_journal(
            store,
            journal,
            works_per_journal=int(run["works_per_journal"]),
            from_year=int(run["from_year"]),
            sources=sources,
            openalex=openalex,
            crossref=crossref,
        )
        item_status = "failed" if result.errors >= source_count else "completed"
        store.finish_publication_run_item(item["id"], item_status, result.papers_seen, result.papers_saved, result.last_error)
        processed += 1
        papers_seen += result.papers_seen
        papers_saved += result.papers_saved
        errors += result.errors

    counts = store.publication_run_item_counts(run_id)
    final_status = "completed" if counts.get("failed", 0) == 0 and counts.get("running", 0) == 0 and counts.get("pending", 0) == 0 else "partial"
    store.update_publication_run_status(run_id, final_status, finished=final_status == "completed")
    if refresh_exports:
        export_publication_batch_outputs(store, run_id)
    return PublicationBatchResult(run_id, final_status, processed, skipped, papers_seen, papers_saved, errors)


def publication_batch_status(store: FacultySpiderV3Store, run_id: int) -> dict[str, object]:
    run = store.get_publication_run(run_id)
    if run is None:
        raise ValueError(f"Publication run not found: {run_id}")
    return {
        "id": run["id"],
        "run_name": run["run_name"],
        "journal_group": run["journal_group"],
        "from_year": run["from_year"],
        "works_per_journal": run["works_per_journal"],
        "sources": run["sources"],
        "status": run["status"],
        "items": store.publication_run_item_counts(run_id),
        "started_at": run["started_at"],
        "finished_at": run["finished_at"],
    }


def journals_for_group(
    store: FacultySpiderV3Store,
    groups_csv: str | Path,
    journal_group: str,
    max_journals: int | None = None,
):
    names = _journal_names_for_group(groups_csv, journal_group)
    selected = []
    remaining = {normalize_text(name) for name in names}
    for journal in store.list_journals():
        if normalize_text(str(journal["journal_name"])) in remaining:
            selected.append(journal)
    if max_journals is not None:
        selected = selected[:max_journals]
    return selected


def export_publication_batch_outputs(
    store: FacultySpiderV3Store,
    run_id: int,
    export_dir: str | Path = EXPORT_DIR,
    gate_thresholds: QualityGateThresholds = DEFAULT_GATE_THRESHOLDS,
    default_batch_only: bool = True,
) -> dict[str, int]:
    export_dir = Path(export_dir)
    items = store.publication_run_items(run_id)
    journal_names = [str(item["journal_name"]) for item in items]
    journals = store.list_journals(journal_names=journal_names)

    # 检查是否为 default_batch（质量门禁只对 default_batch 执行）
    run = store.get_publication_run(run_id)
    is_default_batch = run and str(run.get("journal_group", "")) == "default_batch"

    paper_rows = store.paper_rows()
    candidate_rows = store.paper_candidate_rows()
    review_rows = store.review_issue_rows()

    # 对 default_batch 执行质量门禁
    gate_results: dict[int, JournalGateResult] = {}
    if is_default_batch and default_batch_only:
        journals_dict = [dict(j) for j in journals]
        gate_results = check_quality_gate(journals_dict, [dict(r) for r in paper_rows], list(candidate_rows), [dict(r) for r in review_rows], gate_thresholds)

    counts = {
        "papers": export_papers_csv(paper_rows, export_dir / "papers.csv"),
        "publication_candidates": export_publication_candidates_csv(candidate_rows, export_dir / "publication_candidates.csv"),
        "publication_candidates_chinese": export_publication_candidates_csv(
            candidate_rows,
            export_dir / "publication_candidates_chinese.csv",
            chinese_only=True,
        ),
        "publication_quality_report": export_publication_quality_report_csv(
            store.list_journals(),
            paper_rows,
            candidate_rows,
            store.review_issue_rows(),
            export_dir / "publication_quality_report.csv",
        ),
        "publication_quality_report_run": export_publication_quality_report_csv(
            journals,
            paper_rows,
            candidate_rows,
            store.review_issue_rows(),
            export_dir / f"publication_quality_report_{run_id}.csv",
            gate_results if gate_results else None,
        ),
    }

    # 只对通过门禁的期刊导出 people_candidates（default_batch）
    if gate_results:
        name_to_id = _journal_name_to_id(journals_dict)
        passed_journal_names = [name for name, result in zip(journal_names, [gate_results.get(name_to_id.get(name)) for name in journal_names]) if result and result.passed]
        if passed_journal_names:
            passed_journals = store.list_journals(journal_names=passed_journal_names)
            passed_journal_dicts = [dict(j) for j in passed_journals]
            passed_candidates = _filter_candidates_for_journals(list(candidate_rows), passed_journal_dicts)
            counts["publication_people_candidates"] = export_publication_people_candidates_csv(
                passed_candidates,
                export_dir / "publication_people_candidates.csv",
            )
        else:
            counts["publication_people_candidates"] = 0
    else:
        counts["publication_people_candidates"] = export_publication_people_candidates_csv(
            candidate_rows,
            export_dir / "publication_people_candidates.csv",
        )

    return counts


def _filter_candidates_for_journals(candidate_rows: list[dict[str, object]], journals: list[dict[str, object]]) -> list[dict[str, object]]:
    """过滤出仅属于指定期刊的候选人。"""
    normalized_names = {normalize_publication_name(str(j["journal_name"])) for j in journals}
    filtered = []
    for row in candidate_rows:
        if normalize_publication_name(str(row.get("journal", ""))) in normalized_names:
            filtered.append(row)
    return filtered


def _journal_name_to_id(journals: list[dict[str, object]]) -> dict[str, int]:
    """从期刊字典列表构建 journal_name -> journal_id 映射。"""
    return {str(j["journal_name"]): int(j["id"]) for j in journals}


def _journal_names_for_group(groups_csv: str | Path, journal_group: str) -> list[str]:
    path = Path(groups_csv)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        names = [
            str(row.get("journal_name", "")).strip()
            for row in reader
            if str(row.get("collection_group", "")).strip() == journal_group
        ]
    if not names:
        raise ValueError(f"No journals found for group {journal_group!r} in {path}")
    return names
