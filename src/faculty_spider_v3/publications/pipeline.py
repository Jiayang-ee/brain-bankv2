from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from html import unescape
import re

from faculty_spider_v3.discipline.filter import score_paper_discipline_relevance
from faculty_spider_v3.storage import FacultySpiderV3Store
from faculty_spider_v3.storage import normalize_text

from .crossref import CrossrefClient
from .openalex import OpenAlexClient, default_from_year


@dataclass(frozen=True)
class PublicationSearchResult:
    journals_processed: int
    papers_seen: int
    papers_saved: int
    errors: int
    last_error: str = ""


def search_publications(
    store: FacultySpiderV3Store,
    journals_limit: int = 5,
    works_per_journal: int = 20,
    from_year: int | None = None,
    sources: tuple[str, ...] = ("openalex", "crossref"),
    journal_names: list[str] | None = None,
) -> PublicationSearchResult:
    from_year = from_year or default_from_year(date.today())
    current_year = date.today().year
    journals = store.list_journals(limit=journals_limit, journal_names=journal_names)
    papers_seen = 0
    papers_saved = 0
    errors = 0
    openalex = OpenAlexClient() if "openalex" in sources else None
    crossref = CrossrefClient() if "crossref" in sources else None

    for journal in journals:
        result = search_publications_for_journal(
            store,
            journal,
            works_per_journal=works_per_journal,
            from_year=from_year,
            sources=sources,
            current_year=current_year,
            openalex=openalex,
            crossref=crossref,
        )
        papers_seen += result.papers_seen
        papers_saved += result.papers_saved
        errors += result.errors

    return PublicationSearchResult(
        journals_processed=len(journals),
        papers_seen=papers_seen,
        papers_saved=papers_saved,
        errors=errors,
    )


def search_publications_for_journal(
    store: FacultySpiderV3Store,
    journal,
    works_per_journal: int = 20,
    from_year: int | None = None,
    sources: tuple[str, ...] = ("openalex", "crossref"),
    current_year: int | None = None,
    openalex: OpenAlexClient | None = None,
    crossref: CrossrefClient | None = None,
    journal_group: str = "",
) -> PublicationSearchResult:
    from_year = from_year or default_from_year(date.today())
    current_year = current_year or date.today().year
    openalex = openalex if openalex is not None else OpenAlexClient() if "openalex" in sources else None
    crossref = crossref if crossref is not None else CrossrefClient() if "crossref" in sources else None

    all_papers = []
    errors = 0
    error_messages: list[str] = []
    for source_name, client in (("openalex", openalex), ("crossref", crossref)):
        if client is None:
            continue
        try:
            if source_name == "crossref":
                papers = client.search_works_by_journal(
                    journal["journal_name"],
                    from_year=from_year,
                    per_page=works_per_journal,
                    issn=journal["issn_cn"],
                )
            else:
                papers = client.search_works_by_journal(journal["journal_name"], from_year=from_year, per_page=works_per_journal)
        except Exception as exc:  # noqa: BLE001 - API failures should not stop the batch.
            message = f"{source_name} failed for {journal['journal_name']}: {type(exc).__name__}: {exc}"
            store.add_review_issue(
                issue_type="publication_source_error",
                severity="medium",
                message=message,
                source_url="",
                related_table="journals",
                related_id=journal["id"],
            )
            errors += 1
            error_messages.append(message)
            continue
        for paper in papers:
            if not paper.title or not _paper_matches_journal_window(paper, journal["journal_name"], from_year, current_year):
                continue
            # Apply discipline filtering for broad-impact journals
            if journal_group == "broad_high_impact":
                discipline_score = score_paper_discipline_relevance(
                    title=paper.title,
                    abstract=paper.abstract,
                    keywords="",
                )
                # Reject papers that don't meet minimum threshold
                if discipline_score.review_status == "rejected":
                    store.add_review_issue(
                        issue_type="broad_journal_discipline_filter",
                        severity="low",
                        message=f"Paper filtered by discipline relevance for broad journal {journal['journal_name']}: "
                        f"title='{paper.title[:80]}...' score={discipline_score.score} status={discipline_score.review_status} "
                        f"reason={discipline_score.reason}",
                        source_url=str(paper.paper_url or paper.url or ""),
                        related_table="papers",
                        related_id=None,
                    )
                    continue
            all_papers.append(replace(paper, journal=journal["journal_name"]))

    return PublicationSearchResult(
        journals_processed=1,
        papers_seen=len(all_papers),
        papers_saved=store.upsert_papers(all_papers),
        errors=errors,
        last_error=" | ".join(error_messages),
    )


def _paper_matches_journal_window(paper, journal_name: str, from_year: int, current_year: int) -> bool:
    if paper.year is None or paper.year < from_year or paper.year > current_year:
        return False
    return _journal_names_match(paper.journal, journal_name)


def _journal_names_match(actual: str, expected: str) -> bool:
    actual_normalized = _normalize_journal_name_for_match(actual)
    if not actual_normalized:
        return False
    return actual_normalized in _journal_name_variants(expected)


def _journal_name_variants(value: str) -> set[str]:
    variants = {_normalize_journal_name_for_match(value)}
    if "-" in value:
        prefix, suffix = value.split("-", 1)
        variants.add(_normalize_journal_name_for_match(prefix))
        variants.add(_normalize_journal_name_for_match(suffix))
    return {variant for variant in variants if len(variant) >= 5}


def _normalize_journal_name_for_match(value: str) -> str:
    text = unescape(value or "").casefold().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return normalize_text(text)
