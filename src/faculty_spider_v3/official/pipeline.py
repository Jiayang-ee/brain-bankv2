from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from faculty_spider_v3.config import FACULTY_PHOTO_DIR, RAW_HTML_DIR
from faculty_spider_v3.discipline.filter import score_discipline_relevance
from faculty_spider_v3.models import LinkCandidate
from faculty_spider_v3.names.chinese_name import score_chinese_name
from faculty_spider_v3.storage import FacultySpiderV3Store

from .discover import classify_page, discover_links, useful_candidates
from .fetch import StaticFetcher, content_hash, save_raw_html
from .media import save_photo
from .parse_html import extract_people_from_list_page, extract_person_profile, is_probable_person_profile, should_trigger_llm


@dataclass(frozen=True)
class OfficialDiscoverResult:
    schools_processed: int
    root_pages_saved: int
    candidate_links_saved: int
    errors: int


@dataclass(frozen=True)
class OfficialFetchResult:
    links_processed: int
    pages_saved: int
    new_candidate_links_saved: int
    errors: int


@dataclass(frozen=True)
class OfficialCrawlResult:
    batches: int
    links_processed: int
    pages_saved: int
    new_candidate_links_saved: int
    errors: int


@dataclass(frozen=True)
class OfficialExtractResult:
    pages_processed: int
    people_saved: int
    review_issues: int
    skipped_non_chinese_name: int


@dataclass(frozen=True)
class LlmTriggerResult:
    pages_processed: int
    pages_marked: int
    review_issues: int


def discover_from_school_seeds(
    store: FacultySpiderV3Store,
    limit: int = 50,
    links_per_school: int = 20,
    fetcher: StaticFetcher | None = None,
    raw_html_dir: str | Path = RAW_HTML_DIR,
    school_names: list[str] | None = None,
) -> OfficialDiscoverResult:
    fetcher = fetcher or StaticFetcher()
    source_id = store.upsert_source("official_site", "us_top50_schools")
    schools = store.list_school_seeds(limit=limit, school_names=school_names)
    root_pages_saved = 0
    candidate_links_saved = 0
    errors = 0

    for school in schools:
        fetch = fetcher.fetch(school["homepage_url"])
        raw_path = str(save_raw_html(fetch, raw_html_dir)) if fetch.html else ""
        root_page_type = "school_home"
        root_parser_status = "skipped"
        if fetch.html:
            classified_type, _ = classify_page(fetch.html, school["homepage_url"])
            if classified_type == "faculty_profile":
                root_page_type = "faculty_candidate"
                root_parser_status = "pending"
            elif classified_type == "faculty_list":
                root_page_type = "faculty_list"
                root_parser_status = "pending"
        store.save_page(
            fetch,
            source_id=source_id,
            source_url=school["homepage_url"],
            school=school["school_name_en"],
            page_type=root_page_type,
            content_hash=content_hash(fetch.html) if fetch.html else "",
            raw_html_path=raw_path,
            parser_status=root_parser_status,
        )
        root_pages_saved += 1
        if fetch.error and not fetch.html:
            store.add_review_issue(
                issue_type="source_error",
                severity="medium",
                message=f"Failed to fetch school homepage: {fetch.error}",
                source_url=school["homepage_url"],
                related_table="school_seeds",
                related_id=school["id"],
            )
            errors += 1
            continue
        candidates = useful_candidates(discover_links(fetch.html, school["homepage_url"]), links_per_school)
        candidate_links_saved += store.upsert_candidate_links(source_id, candidates, school=school["school_name_en"])
    return OfficialDiscoverResult(len(schools), root_pages_saved, candidate_links_saved, errors)


def discover_from_school_entrypoints(
    store: FacultySpiderV3Store,
    limit: int = 200,
    links_per_entrypoint: int = 100,
    fetcher: StaticFetcher | None = None,
    raw_html_dir: str | Path = RAW_HTML_DIR,
    school_names: list[str] | None = None,
    statuses: list[str] | None = None,
) -> OfficialDiscoverResult:
    fetcher = fetcher or StaticFetcher()
    source_id = store.upsert_source("official_entrypoint", "school_entrypoints")
    entrypoints = store.list_school_entrypoints(limit=limit, school_names=school_names, statuses=statuses)
    root_pages_saved = 0
    candidate_links_saved = 0
    errors = 0

    for entrypoint in entrypoints:
        fetch = fetcher.fetch(entrypoint["entry_url"])
        raw_path = str(save_raw_html(fetch, raw_html_dir)) if fetch.html else ""
        page_type = _entrypoint_page_type(entrypoint["entry_type"])
        parser_status = "pending" if page_type in {"faculty_list", "faculty_candidate"} and fetch.html else "skipped"
        if fetch.html and not page_type:
            page_type, _ = classify_page(fetch.html, entrypoint["entry_url"])
            parser_status = "pending" if page_type in {"faculty_list", "faculty_candidate"} else "skipped"
        elif not page_type:
            page_type = "faculty_list"
        store.save_page(
            fetch,
            source_id=source_id,
            source_url=entrypoint["entry_url"],
            school=entrypoint["school"],
            department=entrypoint["unit"],
            page_type=page_type,
            content_hash=content_hash(fetch.html) if fetch.html else "",
            raw_html_path=raw_path,
            parser_status=parser_status,
        )
        root_pages_saved += 1
        if fetch.error and not fetch.html:
            store.add_review_issue(
                issue_type="source_error",
                severity="medium",
                message=f"Failed to fetch school entrypoint: {fetch.error}",
                source_url=entrypoint["entry_url"],
                related_table="school_entrypoints",
                related_id=entrypoint["id"],
            )
            errors += 1
            continue
        candidates = useful_candidates(discover_links(fetch.html, entrypoint["entry_url"]), links_per_entrypoint)
        candidate_links_saved += store.upsert_candidate_links(
            source_id,
            candidates,
            school=entrypoint["school"],
            department=entrypoint["unit"],
        )
    return OfficialDiscoverResult(len(entrypoints), root_pages_saved, candidate_links_saved, errors)


def _entrypoint_page_type(entry_type: str) -> str:
    normalized = entry_type.casefold()
    if "profile" in normalized and "list" not in normalized:
        return "faculty_candidate"
    if "list" in normalized or "directory" in normalized or "api" in normalized:
        return "faculty_list"
    return ""


def fetch_candidate_links(
    store: FacultySpiderV3Store,
    limit: int = 100,
    fetcher: StaticFetcher | None = None,
    raw_html_dir: str | Path = RAW_HTML_DIR,
) -> OfficialFetchResult:
    fetcher = fetcher or StaticFetcher()
    rows = store.candidate_link_rows(status="queued", limit=limit)
    pages_saved = 0
    new_links_saved = 0
    errors = 0

    for row in rows:
        fetch = fetcher.fetch(row["url"])
        raw_path = str(save_raw_html(fetch, raw_html_dir)) if fetch.html else ""
        page_type = row["page_type"]
        if fetch.html:
            classified_type, _ = classify_page(fetch.html, row["url"])
            if classified_type == "faculty_profile":
                page_type = "faculty_candidate"
        store.save_page(
            fetch,
            source_id=row["source_id"],
            source_url=row["source_url"],
            page_type=page_type,
            content_hash=content_hash(fetch.html) if fetch.html else "",
            raw_html_path=raw_path,
            parser_status="pending" if page_type in {"faculty_candidate", "faculty_list"} and fetch.html else "skipped",
            school=row["school"],
            department=row["department"],
        )
        pages_saved += 1
        if fetch.error and not fetch.html:
            store.mark_candidate_status(row["url"], "failed")
            store.add_review_issue(issue_type="source_error", severity="low", message=fetch.error, source_url=row["url"], related_table="candidate_links", related_id=row["id"])
            errors += 1
            continue
        store.mark_candidate_status(row["url"], "fetched")
        if page_type in {"faculty_list", "organization"} and fetch.html:
            children = [candidate for candidate in discover_links(fetch.html, row["url"]) if candidate.page_type != "noise"]
            new_links_saved += store.upsert_candidate_links(row["source_id"], children, school=row["school"], department=row["department"])
    return OfficialFetchResult(len(rows), pages_saved, new_links_saved, errors)


def crawl_candidate_links(
    store: FacultySpiderV3Store,
    max_pages: int = 100,
    batch_size: int = 25,
    fetcher: StaticFetcher | None = None,
    raw_html_dir: str | Path = RAW_HTML_DIR,
) -> OfficialCrawlResult:
    fetcher = fetcher or StaticFetcher()
    batches = 0
    links_processed = 0
    pages_saved = 0
    new_links_saved = 0
    errors = 0
    while links_processed < max_pages:
        remaining = max_pages - links_processed
        result = fetch_candidate_links(store, limit=min(batch_size, remaining), fetcher=fetcher, raw_html_dir=raw_html_dir)
        if result.links_processed == 0:
            break
        batches += 1
        links_processed += result.links_processed
        pages_saved += result.pages_saved
        new_links_saved += result.new_candidate_links_saved
        errors += result.errors
    return OfficialCrawlResult(batches, links_processed, pages_saved, new_links_saved, errors)


def extract_html_profiles(store: FacultySpiderV3Store, limit: int = 100, accept_threshold: float = 0.70, review_low: float = 0.45) -> OfficialExtractResult:
    rows = store.page_rows_for_extraction(limit=limit)
    people_saved = 0
    review_issues = 0
    skipped_non_chinese = 0

    for row in rows:
        html = Path(row["raw_html_path"]).read_text(encoding="utf-8", errors="replace")
        profiles = []
        if row["page_type"] == "faculty_list":
            profiles = extract_people_from_list_page(html, row["url"], school=row["school"])
        if not profiles:
            profile = extract_person_profile(html, row["url"], school=row["school"])
            if is_probable_person_profile(profile):
                profiles = [profile]
        if not profiles:
            profiles = extract_people_from_list_page(html, row["url"], school=row["school"])
        if not profiles:
            store.update_page_status(row["url"], parser_status="no_profile")
            continue
        saved_on_page = 0
        for profile in profiles:
            saved, issue_count, skipped = _save_profile_with_review(
                store,
                profile,
                page_id=row["id"],
                accept_threshold=accept_threshold,
                review_low=review_low,
            )
            people_saved += saved
            review_issues += issue_count
            skipped_non_chinese += skipped
            saved_on_page += saved
        store.update_page_status(row["url"], parser_status="parsed" if saved_on_page else "skipped_non_chinese_name")
    return OfficialExtractResult(len(rows), people_saved, review_issues, skipped_non_chinese)


def _save_profile_with_review(
    store: FacultySpiderV3Store,
    profile,
    page_id: int,
    accept_threshold: float,
    review_low: float,
) -> tuple[int, int, int]:
    name_score = score_chinese_name(profile.name, context=profile.source_text, accept_threshold=accept_threshold)
    if name_score.score < review_low:
        return 0, 0, 1
    if profile.photo_url and not profile.photo_path:
        profile = replace(profile, photo_path=save_photo(profile.photo_url, FACULTY_PHOTO_DIR))
    discipline_score = score_discipline_relevance(
        department=profile.department,
        title=profile.title,
        research_interests=profile.research_interests,
        biography=profile.biography,
        publications=profile.publications,
        source_url=profile.source_url,
    )
    review_status = "needs_review" if name_score.score < accept_threshold or profile.confidence_score < 0.65 else "new"
    if discipline_score.review_status == "needs_review" and review_status == "new":
        review_status = "needs_review"
    person_id = store.upsert_person_profile(
        profile,
        is_likely_chinese_name=name_score.is_likely_chinese_name,
        chinese_name_score=name_score.score,
        name_filter_reason=name_score.reason,
        review_status=review_status,
        discipline_score=discipline_score,
    )
    issue_count = 0
    if name_score.score < accept_threshold:
        store.add_review_issue(
            person_id=person_id,
            issue_type="name_filter_uncertain",
            severity="medium",
            message=f"Chinese-name score in review band: {name_score.score} ({name_score.reason})",
            source_url=profile.source_url,
            related_table="pages",
            related_id=page_id,
        )
        issue_count += 1
    if profile.confidence_score < 0.65:
        store.add_review_issue(
            person_id=person_id,
            issue_type="low_confidence",
            severity="medium",
            message=f"HTML extraction confidence below threshold: {profile.confidence_score}",
            source_url=profile.source_url,
            related_table="pages",
            related_id=page_id,
        )
        issue_count += 1
    if discipline_score.review_status == "needs_review":
        store.add_review_issue(
            person_id=person_id,
            issue_type="discipline_uncertain",
            severity="medium",
            message=f"Discipline relevance needs review: {discipline_score.score} ({discipline_score.reason})",
            source_url=profile.source_url,
            related_table="pages",
            related_id=page_id,
        )
        issue_count += 1
    return 1, issue_count, 0


def mark_llm_triggers(store: FacultySpiderV3Store, limit: int = 50) -> LlmTriggerResult:
    rows = store.page_rows_for_llm_trigger(limit=limit)
    marked = 0
    issues = 0
    for row in rows:
        html = Path(row["raw_html_path"]).read_text(encoding="utf-8", errors="replace")
        profile = extract_person_profile(html, row["url"], school=row["school"])
        should_trigger, reason = should_trigger_llm(html, profile)
        if should_trigger:
            store.update_page_status(row["url"], llm_status="needs_llm")
            store.add_review_issue(
                issue_type="llm_used",
                severity="low",
                message=f"Page marked for future LLM extraction: {reason}",
                source_url=row["url"],
                related_table="pages",
                related_id=row["id"],
            )
            marked += 1
            issues += 1
        else:
            store.update_page_status(row["url"], llm_status="not_needed")
    return LlmTriggerResult(len(rows), marked, issues)
