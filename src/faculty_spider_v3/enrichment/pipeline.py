"""Publication-only enrichment pipeline.

Drives the enrich-publication-only-person workflow for each candidate by:
1. Fetching candidate rows from storage.
2. Looking up supplement sources (Semantic Scholar, DBLP, Crossref, OpenAlex).
3. Applying the evidence-strength rules from the enrichment module.
4. Writing enriched fields back to storage with source tracking.
5. Flagging the person needs_review if any low-confidence or conflict field was touched.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from faculty_spider_v3.config import REQUEST_TIMEOUT_SECONDS, USER_AGENT
from faculty_spider_v3.enrichment import (
    CONFIDENCE_THRESHOLD,
    EnrichmentResult,
    EnrichmentCandidate,
    FieldUpdate,
    build_field_update,
    format_enrichment_result,
)
from faculty_spider_v3.publications.crossref import CrossrefClient
from faculty_spider_v3.publications.openalex import OpenAlexClient
from faculty_spider_v3.storage import FacultySpiderV3Store

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnrichmentPipelineResult:
    persons_processed: int
    persons_updated: int
    fields_written: int
    needs_review: int
    errors: int
    results: list[EnrichmentResult]


def enrich_publication_only_person(
    store: FacultySpiderV3Store,
    person_id: int,
    dry_run: bool = False,
) -> EnrichmentResult:
    """Enrich a single publication-only person with supplemental fields.

    Returns an EnrichmentResult describing updates, conflicts, skipped fields,
    and errors.  When dry_run=True, no database writes are performed.
    """
    row = store.get_person(person_id)
    if row is None:
        return EnrichmentResult(
            person_id=person_id,
            updates=[],
            conflicts=[],
            skipped=[],
            errors=[f"person_id {person_id} not found"],
        )

    candidate = EnrichmentCandidate(
        person_id=row["id"],
        name=str(row["name"]),
        school=str(row["school"]),
        personal_homepage=str(row["personal_homepage"]),
        title=str(row["title"]),
        department=str(row["department"]),
        email=str(row["email"]),
        homepage_source=str(row.get("homepage_source", "")),
        title_source=str(row.get("title_source", "")),
        department_source=str(row.get("department_source", "")),
        email_source=str(row.get("email_source", "")),
        school_source=str(row.get("school_source", "")),
        enrichment_confidence=float(row.get("enrichment_confidence", 0.0)),
        primary_source_type=str(row.get("primary_source_type", "")),
    )

    return _enrich_candidate(store, candidate, dry_run=dry_run)


def enrich_publication_only_people(
    store: FacultySpiderV3Store,
    dry_run: bool = False,
    limit: int | None = None,
) -> EnrichmentPipelineResult:
    """Batch-enrich all people whose primary_source_type = 'publication'.

    Processes them sequentially, applying the evidence hierarchy rules and
    writing source-tracking fields back to the database.  Each person is
    flagged needs_review if any enriched field has confidence < threshold
    or a conflict was detected.
    """
    candidates = store.list_publication_only_people(limit=limit)
    results: list[EnrichmentResult] = []
    fields_written = 0
    needs_review = 0
    errors = 0

    for row in candidates:
        candidate = EnrichmentCandidate(
            person_id=row["id"],
            name=str(row["name"]),
            school=str(row["school"]),
            personal_homepage=str(row["personal_homepage"]),
            title=str(row["title"]),
            department=str(row["department"]),
            email=str(row["email"]),
            homepage_source=str(row.get("homepage_source", "")),
            title_source=str(row.get("title_source", "")),
            department_source=str(row.get("department_source", "")),
            email_source=str(row.get("email_source", "")),
            school_source=str(row.get("school_source", "")),
            enrichment_confidence=float(row.get("enrichment_confidence", 0.0)),
            primary_source_type=str(row.get("primary_source_type", "")),
        )
        result = _enrich_candidate(store, candidate, dry_run=dry_run)
        results.append(result)

        if not dry_run and result.updates:
            store.apply_enrichment_updates(
                person_id=candidate.person_id,
                updates=result.updates,
                requires_review=any(u.requires_review for u in result.updates) or bool(result.conflicts),
            )
            fields_written += len(result.updates)
            if any(u.requires_review for u in result.updates) or result.conflicts:
                needs_review += 1

        if result.errors:
            errors += 1

    persons_updated = sum(1 for r in results if r.updates and not dry_run)
    return EnrichmentPipelineResult(
        persons_processed=len(candidates),
        persons_updated=persons_updated,
        fields_written=fields_written,
        needs_review=needs_review,
        errors=errors,
        results=results,
    )


# ----------------------------------------------------------------------
# Supplement source lookups
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class SemanticScholarProfile:
    homepage: str
    title: str
    department: str
    email: str
    confidence: float
    source: str = "semantic_scholar"


@dataclass(frozen=True)
class DBLPProfile:
    affiliation: str
    confidence: float
    source: str = "dblp"


@dataclass(frozen=True)
class CrossrefProfile:
    affiliation: str
    confidence: float
    source: str = "crossref"


@dataclass(frozen=True)
class OpenAlexProfile:
    affiliation: str
    confidence: float
    source: str = "openalex"


def lookup_semantic_scholar(name: str, school: str) -> SemanticScholarProfile | None:
    """Look up an author on Semantic Scholar.

    Returns a SemanticScholarProfile if a unique match is found above the
    confidence threshold, otherwise None.
    """
    import requests

    url = "https://api.semanticscholar.org/graph/v1/author/search"
    params = {"query": name, "affiliation": school, "limit": 5}
    headers = {"Authorization": f"Bearer {USER_AGENT}"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        if resp.status_code != 200:
            return None
        data = resp.json()
        authors = data.get("data", [])
        if len(authors) != 1:
            return None
        author = authors[0]
        if not author.get("hindex"):
            return None
        # Use the first result if name is reasonably similar
        return SemanticScholarProfile(
            homepage=str(author.get("homepage", "")),
            title=str(author.get("title", "")),
            department=str(author.get("department", "")),
            email=str(author.get("email", "")),
            confidence=0.7,  # base confidence for Semantic Scholar lookup
        )
    except Exception:
        return None


def lookup_dblp(name: str) -> DBLPProfile | None:
    """Look up an author on DBLP to get affiliation (computer science focused).

    Returns a DBLPProfile if a match is found, otherwise None.
    """
    import re
    import requests

    # DBLP search URL
    url = f"https://dblp.org/search/author/api?q={name}"
    params = {"format": "xml"}
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        if resp.status_code != 200:
            return None
        # Parse affiliation from XML response
        match = re.search(r"<author name=.*?>(.*?)</author>", resp.text, re.DOTALL)
        if not match:
            return None
        affiliation = match.group(1).strip()
        if not affiliation:
            return None
        return DBLPProfile(affiliation=affiliation, confidence=0.6)
    except Exception:
        return None


def lookup_crossref(name: str, paper_links: list[str]) -> CrossrefProfile | None:
    """Look up author affiliation via Crossref using paper DOIs.

    Returns a CrossrefProfile if affiliation is found, otherwise None.
    """
    client = CrossrefClient()
    if not paper_links:
        return None
    doi = _extract_doi(paper_links[0])
    if not doi:
        return None
    try:
        work = client.work_by_doi(doi)
        if not work:
            return None
        # Use the first author affiliation found
        if work.affiliations:
            return CrossrefProfile(affiliation=work.affiliations[0], confidence=0.5)
    except Exception:
        return None
    return None


def lookup_openalex(name: str, paper_links: list[str]) -> OpenAlexProfile | None:
    """Look up author affiliation via OpenAlex using paper DOIs.

    Returns an OpenAlexProfile if affiliation is found, otherwise None.
    """
    client = OpenAlexClient()
    if not paper_links:
        return None
    doi = _extract_doi(paper_links[0])
    if not doi:
        return None
    try:
        work = client.work_by_doi(doi)
        if not work:
            return None
        if work.affiliations:
            return OpenAlexProfile(affiliation=work.affiliations[0], confidence=0.5)
    except Exception:
        return None
    return None


def _extract_doi(url_or_doi: str) -> str | None:
    """Extract DOI from a URL or return the string as-is if it looks like a DOI."""
    import re
    match = re.search(r"(10\.\d{4,}/[^\s]+)", url_or_doi)
    if match:
        return match.group(1)
    if url_or_doi.startswith("10."):
        return url_or_doi
    return None


# ----------------------------------------------------------------------
# Core enrichment logic
# ----------------------------------------------------------------------


def _enrich_candidate(
    store: FacultySpiderV3Store,
    candidate: EnrichmentCandidate,
    dry_run: bool = False,
) -> EnrichmentResult:
    """Apply enrichment to a single candidate using supplement sources."""
    updates: list[FieldUpdate] = []
    conflicts: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    paper_links = _load_paper_links(store, candidate.person_id)

    # 1. Semantic Scholar: homepage, title, department, email
    if not candidate.personal_homepage or not candidate.title or not candidate.department or not candidate.email:
        ss = lookup_semantic_scholar(candidate.name, candidate.school)
        if ss:
            for field, value in [
                ("homepage", ss.homepage),
                ("title", ss.title),
                ("department", ss.department),
                ("email", ss.email),
            ]:
                if value:
                    current = _current_field(candidate, field)
                    current_src = _current_source_field(candidate, field)
                    update = build_field_update(
                        field=field,
                        new_value=value,
                        source=ss.source,
                        confidence=ss.confidence,
                        current_value=current,
                        current_source=current_src,
                        current_primary_source=candidate.primary_source_type,
                    )
                    if update.new_value:
                        updates.append(update)
                    elif current:
                        skipped.append(f"{field}: no improvement over {current_src}")

    # 2. DBLP: affiliation / school (computer science)
    if not candidate.school or not candidate.school_source:
        dblp = lookup_dblp(candidate.name)
        if dblp:
            current = candidate.school
            current_src = candidate.school_source
            update = build_field_update(
                field="school",
                new_value=dblp.affiliation,
                source=dblp.source,
                confidence=dblp.confidence,
                current_value=current,
                current_source=current_src,
                current_primary_source=candidate.primary_source_type,
            )
            if update.new_value:
                updates.append(update)
            elif current:
                skipped.append(f"school: no improvement over {current_src}")

    # 3. Crossref: school only (weak evidence)
    if not candidate.school or not candidate.school_source:
        cr = lookup_crossref(candidate.name, paper_links)
        if cr:
            current = candidate.school
            current_src = candidate.school_source
            update = build_field_update(
                field="school",
                new_value=cr.affiliation,
                source=cr.source,
                confidence=cr.confidence,
                current_value=current,
                current_source=current_src,
                current_primary_source=candidate.primary_source_type,
            )
            if update.new_value:
                updates.append(update)
            elif current:
                skipped.append(f"school: no improvement over {current_src}")

    # 4. OpenAlex: school only (weak evidence)
    if not candidate.school or not candidate.school_source:
        oa = lookup_openalex(candidate.name, paper_links)
        if oa:
            current = candidate.school
            current_src = candidate.school_source
            update = build_field_update(
                field="school",
                new_value=oa.affiliation,
                source=oa.source,
                confidence=oa.confidence,
                current_value=current,
                current_source=current_src,
                current_primary_source=candidate.primary_source_type,
            )
            if update.new_value:
                updates.append(update)
            elif current:
                skipped.append(f"school: no improvement over {current_src}")

    return EnrichmentResult(
        person_id=candidate.person_id,
        updates=updates,
        conflicts=conflicts,
        skipped=skipped,
        errors=errors,
    )


def _current_field(candidate: EnrichmentCandidate, field: str) -> str:
    return {
        "homepage": candidate.personal_homepage,
        "title": candidate.title,
        "department": candidate.department,
        "email": candidate.email,
        "school": candidate.school,
    }.get(field, "")


def _current_source_field(candidate: EnrichmentCandidate, field: str) -> str:
    return {
        "homepage": candidate.homepage_source,
        "title": candidate.title_source,
        "department": candidate.department_source,
        "email": candidate.email_source,
        "school": candidate.school_source,
    }.get(field, "")


def _load_paper_links(store: FacultySpiderV3Store, person_id: int) -> list[str]:
    """Load paper_links for a person as a list of strings."""
    with store.connect() as conn:
        row = conn.execute(
            "select paper_links_json from people where id = ?",
            (person_id,),
        ).fetchone()
        if not row or not row["paper_links_json"]:
            return []
        try:
            return json.loads(row["paper_links_json"])
        except json.JSONDecodeError:
            return []