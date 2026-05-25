from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from faculty_spider_v3.config import EXPORT_DIR, SEED_DIR
from faculty_spider_v3.publications.crossref import CrossrefClient
from faculty_spider_v3.publications.export import (
    export_papers_csv,
    export_publication_candidates_csv,
    export_publication_people_candidates_csv,
    export_publication_quality_report_csv,
)
from faculty_spider_v3.publications.openalex import OpenAlexClient, default_from_year
from faculty_spider_v3.publications.pipeline import search_publications_for_journal
from faculty_spider_v3.storage import FacultySpiderV3Store, normalize_text

DEFAULT_GROUPS_CSV = SEED_DIR / "publication_journal_groups.csv"


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


def export_publication_batch_outputs(store: FacultySpiderV3Store, run_id: int, export_dir: str | Path = EXPORT_DIR) -> dict[str, int]:
    export_dir = Path(export_dir)
    items = store.publication_run_items(run_id)
    journal_names = [str(item["journal_name"]) for item in items]
    journals = store.list_journals(journal_names=journal_names)
    paper_rows = store.paper_rows()
    candidate_rows = store.paper_candidate_rows()
    counts = {
        "papers": export_papers_csv(paper_rows, export_dir / "papers.csv"),
        "publication_candidates": export_publication_candidates_csv(candidate_rows, export_dir / "publication_candidates.csv"),
        "publication_candidates_chinese": export_publication_candidates_csv(
            candidate_rows,
            export_dir / "publication_candidates_chinese.csv",
            chinese_only=True,
        ),
        "publication_people_candidates": export_publication_people_candidates_csv(
            candidate_rows,
            export_dir / "publication_people_candidates.csv",
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
        ),
    }
    return counts


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