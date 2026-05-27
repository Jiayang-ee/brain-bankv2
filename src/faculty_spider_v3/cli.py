from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import DEFAULT_DB, ensure_runtime_dirs
from .discipline.filter import score_discipline_relevance
from .official.entrypoints import read_school_entrypoints
from .official.export import export_page_audit_csv, export_people_csv
from .official.pipeline import (
    crawl_candidate_links,
    discover_from_school_entrypoints,
    discover_from_school_seeds,
    extract_html_profiles,
    fetch_candidate_links,
    mark_llm_triggers,
)
from .official.seeds import read_school_seeds, write_school_seeds_csv
from .publications.export import (
    aggregate_publication_people_candidates,
    export_papers_csv,
    export_publication_candidates_csv,
    export_publication_people_candidates_csv,
    export_publication_quality_report_csv,
)
from .publications.batch import create_publication_batch, publication_batch_status, run_publication_batch
from .publications.affiliation_backfill import backfill_missing_affiliations
from .publications.journal_list import read_journals_csv
from .publications.pipeline import search_publications
from .review.issues import export_review_issues_csv, export_people_review_csv
from .review.report import (
    export_review_roster,
    export_wave1_quality_gap_report,
    export_wave1_review_queue,
    generate_run_record,
    get_git_commit,
)
from .enrichment.pipeline import enrich_publication_only_people
from .storage import FacultySpiderV3Store


def _store(path: str | Path) -> FacultySpiderV3Store:
    ensure_runtime_dirs()
    store = FacultySpiderV3Store(path)
    store.init_db()
    return store


def init_db_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    print(json.dumps({"db": str(store.db_path), "status": "initialized"}, ensure_ascii=False, indent=2))


def import_journals_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    journals = read_journals_csv(args.csv)
    source_id = store.upsert_source("journal_list", Path(args.csv).name)
    count = store.upsert_journals(journals)
    print(json.dumps({"source_id": source_id, "journals": count, "db_total": store.count("journals")}, ensure_ascii=False, indent=2))


def publications_search_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    sources = tuple(source.strip() for source in args.sources.split(",") if source.strip())
    result = search_publications(
        store,
        journals_limit=args.journals_limit,
        works_per_journal=args.works_per_journal,
        from_year=args.from_year,
        sources=sources,
        journal_names=args.journal,
    )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


def publications_export_papers_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    count = export_papers_csv(store.paper_rows(), args.csv)
    print(json.dumps({"papers": count, "csv": args.csv}, ensure_ascii=False, indent=2))


def publications_export_candidates_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    count = export_publication_candidates_csv(store.paper_candidate_rows(), args.csv, chinese_only=args.chinese_only)
    print(json.dumps({"publication_candidates": count, "csv": args.csv}, ensure_ascii=False, indent=2))


def publications_export_people_candidates_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    count = export_publication_people_candidates_csv(store.paper_candidate_rows(), args.csv, chinese_only=not args.include_all_names)
    print(json.dumps({"publication_people_candidates": count, "csv": args.csv}, ensure_ascii=False, indent=2))


def publications_import_people_candidates_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    candidates = aggregate_publication_people_candidates(store.paper_candidate_rows(), chinese_only=not args.include_all_names)
    result = store.upsert_publication_people_candidates(candidates)
    print(json.dumps({"publication_people_candidates": len(candidates), **result}, ensure_ascii=False, indent=2))


def publications_export_quality_report_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    count = export_publication_quality_report_csv(
        store.list_journals(),
        store.paper_rows(),
        store.paper_candidate_rows(),
        store.review_issue_rows(),
        args.csv,
    )
    print(json.dumps({"publication_quality_rows": count, "csv": args.csv}, ensure_ascii=False, indent=2))


def publications_batch_create_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    sources = tuple(source.strip() for source in args.sources.split(",") if source.strip())
    run_id = create_publication_batch(
        store,
        journal_group=args.journal_group,
        from_year=args.from_year,
        works_per_journal=args.works_per_journal,
        sources=sources,
        groups_csv=args.groups_csv,
        run_name=args.run_name,
        max_journals=args.max_journals,
    )
    print(json.dumps(publication_batch_status(store, run_id), ensure_ascii=False, indent=2))


def publications_batch_run_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    sources = tuple(source.strip() for source in args.sources.split(",") if source.strip())
    result = run_publication_batch(
        store,
        journal_group=args.journal_group,
        from_year=args.from_year,
        works_per_journal=args.works_per_journal,
        sources=sources,
        groups_csv=args.groups_csv,
        run_id=args.run_id,
        resume=args.resume,
        run_name=args.run_name,
        max_journals=args.max_journals,
        refresh_exports=not args.no_export,
    )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


def publications_batch_resume_command(args: argparse.Namespace) -> None:
    args.resume = True
    publications_batch_run_command(args)


def publications_batch_status_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    print(json.dumps(publication_batch_status(store, args.run_id), ensure_ascii=False, indent=2))


def publications_backfill_affiliations_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    result = backfill_missing_affiliations(
        store,
        limit=args.limit,
        journal_names=args.journal,
        use_landing_pages=args.use_landing_pages,
        refresh_exports=not args.no_export,
        export_run_id=args.export_run_id,
    )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


def import_seeds_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    seeds = read_school_seeds(args.input, limit=args.limit)
    if args.output_csv:
        write_school_seeds_csv(seeds, args.output_csv)
    source_id = store.upsert_source("official_site", "us_top50_schools" if args.limit == 50 else Path(args.input).stem)
    count = store.upsert_school_seeds(seeds)
    print(
        json.dumps(
            {
                "source_id": source_id,
                "school_seeds": count,
                "db_total": store.count("school_seeds"),
                "output_csv": args.output_csv,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def import_entrypoints_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    entrypoints = read_school_entrypoints(args.csv)
    source_id = store.upsert_source("official_entrypoint", Path(args.csv).name)
    count = store.upsert_school_entrypoints(entrypoints)
    print(
        json.dumps(
            {
                "source_id": source_id,
                "school_entrypoints": count,
                "db_total": store.count("school_entrypoints"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def official_discover_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    result = discover_from_school_seeds(store, limit=args.limit, links_per_school=args.links_per_school, school_names=args.school)
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


def official_discover_entrypoints_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    result = discover_from_school_entrypoints(
        store,
        limit=args.limit,
        links_per_entrypoint=args.links_per_entrypoint,
        school_names=args.school,
        statuses=args.status,
    )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


def official_fetch_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    result = fetch_candidate_links(store, limit=args.limit)
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


def official_crawl_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    result = crawl_candidate_links(store, max_pages=args.max_pages, batch_size=args.batch_size)
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


def official_extract_html_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    result = extract_html_profiles(store, limit=args.limit)
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


def official_extract_llm_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    if not args.trigger_only:
        raise SystemExit("v3 currently supports only --trigger-only for local LLM extraction")
    result = mark_llm_triggers(store, limit=args.limit)
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


def official_export_people_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    count = export_people_csv(store.people_rows(), args.csv)
    print(json.dumps({"people": count, "csv": args.csv}, ensure_ascii=False, indent=2))


def official_audit_pages_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    count = export_page_audit_csv(store.page_audit_rows(), args.csv)
    print(json.dumps({"pages": count, "csv": args.csv}, ensure_ascii=False, indent=2))


def export_review_issues_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    rows = store.review_issue_rows(status=args.status or None)
    count = export_review_issues_csv(rows, args.csv)
    print(json.dumps({"review_issues": count, "csv": args.csv}, ensure_ascii=False, indent=2))


def export_people_review_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    people = store.people_rows()
    open_issues = store.review_issue_rows(status="open")
    count = export_people_review_csv(people, open_issues, args.csv)
    print(json.dumps({"people_review": count, "csv": args.csv}, ensure_ascii=False, indent=2))


def maintenance_dedupe_people_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    result = store.deduplicate_people_by_canonical_url()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def maintenance_rescore_discipline_command(args: argparse.Namespace) -> None:
    store = _store(args.db)
    rows = store.people_rows()
    counts = {"accepted": 0, "needs_review": 0, "rejected": 0}
    for row in rows:
        discipline_score = score_discipline_relevance(
            department=row["department"],
            title=row["title"],
            field=row["field"],
            research_direction=row["research_direction"],
            research_interests=row["research_interests"],
            biography=row["biography"],
            publications=row["publications_json"],
            source_url=row["source_url"],
        )
        store.update_person_discipline_score(row["id"], discipline_score)
        counts[discipline_score.review_status] = counts.get(discipline_score.review_status, 0) + 1
    print(json.dumps({"people_scored": len(rows), **counts}, ensure_ascii=False, indent=2))


def review_roster_command(args: argparse.Namespace) -> None:
    """Export confirmed / deferred / rejected rosters from people_review CSV."""
    import csv

    # Load people from CSV export
    people_csv = Path(__file__).resolve().parents[2] / "data" / "exports" / "people.csv"
    people_rows = []
    if people_csv.exists():
        with people_csv.open(encoding="utf-8-sig") as f:
            people_rows = list(csv.DictReader(f))

    # Load all review issues
    issues_csv = Path(__file__).resolve().parents[2] / "data" / "review" / "issues.csv"
    review_issue_rows = []
    if issues_csv.exists():
        with issues_csv.open(encoding="utf-8-sig") as f:
            review_issue_rows = list(csv.DictReader(f))

    output_dir = Path(__file__).resolve().parents[2] / args.output_dir
    batch_name = args.batch_name

    roster_result = export_review_roster(
        people_rows, review_issue_rows, output_dir, batch_name
    )

    print(json.dumps({
        "batch_name": batch_name,
        "rosters": roster_result,
    }, ensure_ascii=False, indent=2))


def review_import_command(args: argparse.Namespace) -> None:
    """Apply review decisions from a people_review CSV write-back file."""
    store = _store(args.db)
    count = store.import_review_decisions(args.csv)
    print(json.dumps({"review_decisions_applied": count}, ensure_ascii=False, indent=2))


def review_wave1_report_command(args: argparse.Namespace) -> None:
    """Generate Wave 1 review queue and quality gap report.

    Reads from the CSV exports in data/exports/ (the actual data store)
    so that this command works standalone without a populated SQLite DB.
    """
    import csv
    from datetime import datetime, timezone

    # Load people from the CSV export (source of truth for M7 data)
    people_csv = Path(__file__).resolve().parents[2] / "data" / "exports" / "people.csv"
    people_rows = []
    if people_csv.exists():
        with people_csv.open(encoding="utf-8-sig") as f:
            people_rows = list(csv.DictReader(f))

    # Load open issues from the review issues CSV
    issues_csv = Path(__file__).resolve().parents[2] / "data" / "review" / "issues.csv"
    open_issues = []
    if issues_csv.exists():
        with issues_csv.open(encoding="utf-8-sig") as f:
            open_issues = [row for row in csv.DictReader(f) if row.get("status") == "open"]

    # Generate run_id if not provided
    run_id = args.run_id
    if not run_id:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        run_id = f"wave1-{ts}"

    # Resolve output paths relative to repo root
    repo_root = Path(__file__).resolve().parents[2]
    queue_csv_path = (Path(args.queue_csv) if Path(args.queue_csv).is_absolute()
                      else repo_root / args.queue_csv)
    gap_csv_path = (Path(args.gap_csv) if Path(args.gap_csv).is_absolute()
                    else repo_root / args.gap_csv)

    # Capture git commit and command
    git_commit = get_git_commit(repo_root)
    command = f"review wave1-report --queue-csv {args.queue_csv} --gap-csv {args.gap_csv}"

    # Export review queue
    queue_result = export_wave1_review_queue(people_rows, open_issues, queue_csv_path)

    # Export quality gap report
    gap_result = export_wave1_quality_gap_report(people_rows, open_issues, gap_csv_path)

    # Generate run record
    output_dir = repo_root / args.output_dir
    run_record = generate_run_record(
        queue_result,
        gap_result,
        run_id=run_id,
        git_commit=git_commit,
        input_files=[str(people_csv), str(issues_csv)],
        command=command,
        output_dir=str(output_dir),
    )

    print(json.dumps({
        "run_id": run_id,
        "git_commit": git_commit,
        "review_queue": queue_result["review_queue_rows"],
        "queue_csv": queue_result["review_queue_path"],
        "quality_gap_categories": gap_result["quality_gap_rows"],
        "gap_csv": gap_result["quality_gap_path"],
        "run_record": run_record["run_record_path"],
    }, ensure_ascii=False, indent=2))


def enrichment_run_command(args: argparse.Namespace) -> None:
    """Enrich publication-only people with supplemental fields from Semantic Scholar, DBLP, Crossref, and OpenAlex."""
    store = _store(args.db)
    result = enrich_publication_only_people(store, dry_run=args.dry_run, limit=args.limit)
    print(json.dumps({
        "persons_processed": result.persons_processed,
        "persons_updated": result.persons_updated,
        "fields_written": result.fields_written,
        "needs_review": result.needs_review,
        "errors": result.errors,
        "dry_run": args.dry_run,
    }, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="faculty-spider-v3")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-db")
    init_parser.set_defaults(func=init_db_command)

    official_parser = subparsers.add_parser("official")
    official_subparsers = official_parser.add_subparsers(dest="official_command", required=True)
    import_seeds_parser = official_subparsers.add_parser("import-seeds")
    import_seeds_parser.add_argument("input", help="CSV or Excel seed file")
    import_seeds_parser.add_argument("--limit", type=int, default=None)
    import_seeds_parser.add_argument("--output-csv", default="")
    import_seeds_parser.set_defaults(func=import_seeds_command)
    import_entrypoints_parser = official_subparsers.add_parser("import-entrypoints")
    import_entrypoints_parser.add_argument("csv", help="CSV file containing verified faculty directory entrypoints")
    import_entrypoints_parser.set_defaults(func=import_entrypoints_command)
    discover_parser = official_subparsers.add_parser("discover")
    discover_parser.add_argument("--limit", type=int, default=50)
    discover_parser.add_argument("--links-per-school", type=int, default=20)
    discover_parser.add_argument("--school", action="append", help="Limit discovery to a school name; can be repeated")
    discover_parser.set_defaults(func=official_discover_command)
    discover_entrypoints_parser = official_subparsers.add_parser("discover-entrypoints")
    discover_entrypoints_parser.add_argument("--limit", type=int, default=200)
    discover_entrypoints_parser.add_argument("--links-per-entrypoint", type=int, default=100)
    discover_entrypoints_parser.add_argument("--school", action="append", help="Limit discovery to a school name; can be repeated")
    discover_entrypoints_parser.add_argument(
        "--status",
        action="append",
        default=["verified"],
        help="Entrypoint status to include; defaults to verified. Can be repeated.",
    )
    discover_entrypoints_parser.set_defaults(func=official_discover_entrypoints_command)
    fetch_parser = official_subparsers.add_parser("fetch")
    fetch_parser.add_argument("--limit", type=int, default=100)
    fetch_parser.set_defaults(func=official_fetch_command)
    crawl_parser = official_subparsers.add_parser("crawl")
    crawl_parser.add_argument("--max-pages", type=int, default=100)
    crawl_parser.add_argument("--batch-size", type=int, default=25)
    crawl_parser.set_defaults(func=official_crawl_command)
    extract_html_parser = official_subparsers.add_parser("extract-html")
    extract_html_parser.add_argument("--limit", type=int, default=100)
    extract_html_parser.set_defaults(func=official_extract_html_command)
    extract_llm_parser = official_subparsers.add_parser("extract-llm")
    extract_llm_parser.add_argument("--limit", type=int, default=50)
    extract_llm_parser.add_argument("--trigger-only", action="store_true")
    extract_llm_parser.set_defaults(func=official_extract_llm_command)
    export_people_parser = official_subparsers.add_parser("export-people")
    export_people_parser.add_argument("--csv", default="data/exports/people.csv")
    export_people_parser.set_defaults(func=official_export_people_command)
    audit_pages_parser = official_subparsers.add_parser("audit-pages")
    audit_pages_parser.add_argument("--csv", default="data/exports/page_audit.csv")
    audit_pages_parser.set_defaults(func=official_audit_pages_command)

    publications_parser = subparsers.add_parser("publications")
    publications_subparsers = publications_parser.add_subparsers(dest="publications_command", required=True)
    import_journals_parser = publications_subparsers.add_parser("import-journals")
    import_journals_parser.add_argument("csv")
    import_journals_parser.set_defaults(func=import_journals_command)
    search_publications_parser = publications_subparsers.add_parser("search")
    search_publications_parser.add_argument("--journals-limit", type=int, default=5)
    search_publications_parser.add_argument("--works-per-journal", type=int, default=20)
    search_publications_parser.add_argument("--from-year", type=int, default=None)
    search_publications_parser.add_argument("--sources", default="openalex,crossref", help="Comma-separated: openalex,crossref")
    search_publications_parser.add_argument("--journal", action="append", help="Limit to an exact journal name; can be repeated")
    search_publications_parser.set_defaults(func=publications_search_command)
    export_papers_parser = publications_subparsers.add_parser("export-papers")
    export_papers_parser.add_argument("--csv", default="data/exports/papers.csv")
    export_papers_parser.set_defaults(func=publications_export_papers_command)
    export_candidates_parser = publications_subparsers.add_parser("export-candidates")
    export_candidates_parser.add_argument("--csv", default="data/exports/publication_candidates.csv")
    export_candidates_parser.add_argument("--chinese-only", action="store_true", help="Keep candidates in the Chinese-name review/accept bands only")
    export_candidates_parser.set_defaults(func=publications_export_candidates_command)
    export_people_candidates_parser = publications_subparsers.add_parser("export-people-candidates")
    export_people_candidates_parser.add_argument("--csv", default="data/exports/publication_people_candidates.csv")
    export_people_candidates_parser.add_argument("--include-all-names", action="store_true", help="Include non-Chinese-name candidates too")
    export_people_candidates_parser.set_defaults(func=publications_export_people_candidates_command)
    import_people_candidates_parser = publications_subparsers.add_parser("import-people-candidates")
    import_people_candidates_parser.add_argument("--include-all-names", action="store_true", help="Import non-Chinese-name candidates too")
    import_people_candidates_parser.set_defaults(func=publications_import_people_candidates_command)
    export_quality_report_parser = publications_subparsers.add_parser("export-quality-report")
    export_quality_report_parser.add_argument("--csv", default="data/exports/publication_quality_report.csv")
    export_quality_report_parser.set_defaults(func=publications_export_quality_report_command)
    batch_create_parser = publications_subparsers.add_parser("batch-create")
    _add_publication_batch_args(batch_create_parser)
    batch_create_parser.set_defaults(func=publications_batch_create_command)
    batch_run_parser = publications_subparsers.add_parser("batch-run")
    _add_publication_batch_args(batch_run_parser)
    batch_run_parser.add_argument("--run-id", type=int, default=None)
    batch_run_parser.add_argument("--resume", action="store_true")
    batch_run_parser.add_argument("--no-export", action="store_true", help="Do not refresh publication export CSV files after the run")
    batch_run_parser.set_defaults(func=publications_batch_run_command)
    batch_resume_parser = publications_subparsers.add_parser("batch-resume")
    _add_publication_batch_args(batch_resume_parser)
    batch_resume_parser.add_argument("--run-id", type=int, default=None)
    batch_resume_parser.add_argument("--no-export", action="store_true", help="Do not refresh publication export CSV files after the run")
    batch_resume_parser.set_defaults(func=publications_batch_resume_command)
    batch_status_parser = publications_subparsers.add_parser("batch-status")
    batch_status_parser.add_argument("run_id", type=int)
    batch_status_parser.set_defaults(func=publications_batch_status_command)
    backfill_affiliations_parser = publications_subparsers.add_parser("backfill-affiliations")
    backfill_affiliations_parser.add_argument("--limit", type=int, default=None)
    backfill_affiliations_parser.add_argument("--journal", action="append", help="Limit to an exact journal name; can be repeated")
    backfill_affiliations_parser.add_argument("--use-landing-pages", action="store_true", help="Also try publisher landing pages after OpenAlex DOI lookup")
    backfill_affiliations_parser.add_argument("--export-run-id", type=int, default=None, help="Run id for the run-scoped quality report export")
    backfill_affiliations_parser.add_argument("--no-export", action="store_true", help="Do not refresh publication export CSV files after backfill")
    backfill_affiliations_parser.set_defaults(func=publications_backfill_affiliations_command)

    review_parser = subparsers.add_parser("review")
    review_subparsers = review_parser.add_subparsers(dest="review_command", required=True)
    review_issues_parser = review_subparsers.add_parser("issues")
    review_issues_parser.add_argument("--csv", default="data/review/issues.csv")
    review_issues_parser.add_argument("--status", default="")
    review_issues_parser.set_defaults(func=export_review_issues_command)

    people_review_parser = review_subparsers.add_parser("people-review")
    people_review_parser.add_argument("--csv", default="data/review/people_review.csv")
    people_review_parser.set_defaults(func=export_people_review_command)

    review_import_parser = review_subparsers.add_parser("import")
    review_import_parser.add_argument("csv", help="Path to the reviewed people_review.csv with write-back columns")
    review_import_parser.set_defaults(func=review_import_command)

    wave1_report_parser = review_subparsers.add_parser("wave1-report")
    wave1_report_parser.add_argument(
        "--queue-csv",
        default="data/review/wave1_review_queue.csv",
        help="Output path for the Wave 1 review queue CSV",
    )
    wave1_report_parser.add_argument(
        "--gap-csv",
        default="data/review/wave1_quality_gap_report.csv",
        help="Output path for the Wave 1 quality gap summary CSV",
    )
    wave1_report_parser.add_argument(
        "--output-dir",
        default="data/review",
        help="Directory for the run record JSON",
    )
    wave1_report_parser.add_argument(
        "--run-id",
        default="",
        help="Run identifier; auto-generated if not provided",
    )
    wave1_report_parser.set_defaults(func=review_wave1_report_command)

    roster_parser = review_subparsers.add_parser("roster")
    roster_parser.add_argument(
        "--batch-name",
        default="wave1",
        help="Batch name prefix for output files (default: wave1)",
    )
    roster_parser.add_argument(
        "--output-dir",
        default="data/review",
        help="Directory for roster CSV files (default: data/review)",
    )
    roster_parser.set_defaults(func=review_roster_command)

    maintenance_parser = subparsers.add_parser("maintenance")
    maintenance_subparsers = maintenance_parser.add_subparsers(dest="maintenance_command", required=True)
    dedupe_people_parser = maintenance_subparsers.add_parser("dedupe-people")
    dedupe_people_parser.set_defaults(func=maintenance_dedupe_people_command)
    rescore_discipline_parser = maintenance_subparsers.add_parser("rescore-discipline")
    rescore_discipline_parser.set_defaults(func=maintenance_rescore_discipline_command)

    enrichment_parser = subparsers.add_parser("enrichment")
    enrichment_subparsers = enrichment_parser.add_subparsers(dest="enrichment_command", required=True)
    enrichment_run_parser = enrichment_subparsers.add_parser("run")
    enrichment_run_parser.add_argument("--dry-run", action="store_true", help="Show what would be updated without writing to the database")
    enrichment_run_parser.add_argument("--limit", type=int, default=None, help="Limit the number of publication-only people to process")
    enrichment_run_parser.set_defaults(func=enrichment_run_command)

    return parser


def _add_publication_batch_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--journal-group", default="default_batch")
    parser.add_argument("--works-per-journal", type=int, default=50)
    parser.add_argument("--from-year", type=int, default=None)
    parser.add_argument("--sources", default="openalex,crossref", help="Comma-separated: openalex,crossref")
    parser.add_argument("--groups-csv", default="data/seeds/publication_journal_groups.csv")
    parser.add_argument("--run-name", default="")
    parser.add_argument("--max-journals", type=int, default=None, help="Limit items added to a newly created run")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
