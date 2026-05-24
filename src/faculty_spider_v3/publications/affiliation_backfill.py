from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import unescape

import requests

from faculty_spider_v3.config import REQUEST_TIMEOUT_SECONDS, USER_AGENT
from faculty_spider_v3.publications.batch import export_publication_batch_outputs
from faculty_spider_v3.publications.openalex import OpenAlexClient
from faculty_spider_v3.storage import FacultySpiderV3Store


@dataclass(frozen=True)
class AffiliationBackfillResult:
    papers_checked: int
    openalex_updated: int
    landing_page_updated: int
    still_missing: int
    errors: int


def backfill_missing_affiliations(
    store: FacultySpiderV3Store,
    limit: int | None = None,
    journal_names: list[str] | None = None,
    use_landing_pages: bool = False,
    refresh_exports: bool = True,
    export_run_id: int | None = None,
) -> AffiliationBackfillResult:
    rows = store.papers_missing_affiliations(limit=limit, journal_names=journal_names)
    openalex = OpenAlexClient()
    landing_session = requests.Session()
    landing_session.headers.update({"User-Agent": USER_AGENT})
    openalex_updated = 0
    landing_page_updated = 0
    errors = 0

    for row in rows:
        try:
            paper = openalex.work_by_doi(str(row["doi"]), fallback_journal=str(row["journal"]))
        except Exception as exc:  # noqa: BLE001 - keep the backfill resumable.
            errors += 1
            store.add_review_issue(
                issue_type="affiliation_backfill_error",
                severity="low",
                message=f"OpenAlex DOI backfill failed for {row['doi']}: {type(exc).__name__}: {exc}",
                related_table="papers",
                related_id=row["id"],
                source_url=str(row["paper_url"] or row["url"] or ""),
            )
            paper = None
        if paper and paper.affiliations:
            store.update_paper_authorship_metadata(
                row["id"],
                paper.authors,
                paper.affiliations,
                first_author_name=paper.first_author_name,
                corresponding_author_names=paper.corresponding_author_names,
                source_api_url=paper.source_api_url,
            )
            openalex_updated += 1
            continue

        if not use_landing_pages:
            continue
        try:
            landing_authors, landing_affiliations = affiliations_from_landing_page(
                str(row["paper_url"] or row["url"] or f"https://doi.org/{row['doi']}"),
                landing_session,
            )
        except Exception as exc:  # noqa: BLE001 - publisher pages are best-effort only.
            errors += 1
            store.add_review_issue(
                issue_type="affiliation_backfill_error",
                severity="low",
                message=f"Landing page affiliation backfill failed for {row['doi']}: {type(exc).__name__}: {exc}",
                related_table="papers",
                related_id=row["id"],
                source_url=str(row["paper_url"] or row["url"] or ""),
            )
            continue
        if landing_affiliations:
            authors = _merge_landing_affiliations(row["authors_json"], landing_authors, landing_affiliations)
            store.update_paper_authorship_metadata(row["id"], authors, landing_affiliations, first_author_name=str(row["first_author_name"] or ""))
            landing_page_updated += 1

    still_missing = len(store.papers_missing_affiliations(journal_names=journal_names))
    if refresh_exports:
        export_publication_batch_outputs(store, export_run_id or _latest_publication_run_id(store) or 0)
    return AffiliationBackfillResult(len(rows), openalex_updated, landing_page_updated, still_missing, errors)


def affiliations_from_landing_page(url: str, session: requests.Session | None = None) -> tuple[list[str], list[str]]:
    session = session or requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS, allow_redirects=True)
    response.raise_for_status()
    html = response.text
    authors, affiliations = _affiliations_from_citation_meta(html)
    if affiliations:
        return authors, affiliations
    return _affiliations_from_json_ld(html)


def _affiliations_from_citation_meta(html: str) -> tuple[list[str], list[str]]:
    authors = _meta_values(html, "citation_author")
    affiliations = _meta_values(html, "citation_author_institution")
    return authors, affiliations


def _affiliations_from_json_ld(html: str) -> tuple[list[str], list[str]]:
    authors: list[str] = []
    affiliations: list[str] = []
    for match in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.I | re.S):
        text = unescape(match.group(1)).strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        for item in _jsonld_items(payload):
            author_items = item.get("author") or item.get("creator") or []
            if isinstance(author_items, dict):
                author_items = [author_items]
            if not isinstance(author_items, list):
                continue
            for author in author_items:
                if not isinstance(author, dict):
                    continue
                name = str(author.get("name") or "").strip()
                if name:
                    authors.append(name)
                affiliation = author.get("affiliation")
                affiliations.extend(_affiliation_names(affiliation))
    return _unique(authors), _unique(affiliations)


def _jsonld_items(payload) -> list[dict]:
    if isinstance(payload, dict):
        graph = payload.get("@graph")
        if isinstance(graph, list):
            return [item for item in graph if isinstance(item, dict)] + [payload]
        return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _affiliation_names(value) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, dict):
        name = str(value.get("name") or "").strip()
        return [name] if name else []
    if isinstance(value, list):
        names: list[str] = []
        for item in value:
            names.extend(_affiliation_names(item))
        return names
    return []


def _meta_values(html: str, name: str) -> list[str]:
    values = []
    pattern = re.compile(
        rf'<meta[^>]+(?:name|property)=["\']{re.escape(name)}["\'][^>]+content=["\'](.*?)["\'][^>]*>',
        re.I | re.S,
    )
    for match in pattern.finditer(html):
        value = unescape(match.group(1)).strip()
        if value:
            values.append(value)
    return _unique(values)


def _merge_landing_affiliations(authors_json: str, landing_authors: list[str], affiliations: list[str]) -> list[dict]:
    try:
        authors = json.loads(authors_json or "[]")
    except json.JSONDecodeError:
        authors = []
    if not isinstance(authors, list):
        authors = []
    if not authors:
        return [{"name": name, "affiliations": affiliations} for name in landing_authors]
    if len(affiliations) == len(authors):
        for author, affiliation in zip(authors, affiliations):
            if isinstance(author, dict) and not author.get("affiliations"):
                author["affiliations"] = [affiliation]
        return authors
    for author in authors:
        if isinstance(author, dict) and not author.get("affiliations"):
            author["affiliations"] = affiliations
    return authors


def _latest_publication_run_id(store: FacultySpiderV3Store) -> int | None:
    with store.connect() as conn:
        row = conn.execute("select id from publication_runs order by id desc limit 1").fetchone()
        return int(row["id"]) if row else None


def _unique(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        normalized = " ".join(value.split())
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result
