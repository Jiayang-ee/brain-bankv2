"""Publication-only person field enrichment.

Evidence hierarchy (strongest to weakest):
    1. official_site  – highest priority, never overridden by supplement sources
    2. semantic_scholar – medium priority: homepage, title, department, email
    3. dblp            – medium priority: affiliation (computer science)
    4. crossref        – weak evidence: school only
    5. openalex       – weak evidence: school only

Rules
----
- Strong evidence NEVER overwrites existing strong evidence.
- Medium evidence overwrites only if:
    (a) the target field is currently empty, OR
    (b) the existing value came from a strictly weaker source
- Low-confidence data (< 0.7) is flagged for review instead of auto-written.
- All writes record the source and confidence for traceability.
- Publication-only candidates are always flagged needs_review after enrichment.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class EvidenceStrength(IntEnum):
    """Ordered from weakest (0) to strongest (4)."""

    WEAK = 0
    CROSSREF = 1
    OPENALEX = 1
    DBLP = 2
    SEMANTIC_SCHOLAR = 3
    OFFICIAL_SITE = 4


SUPPLEMENT_SOURCE_FIELD_MAP = {
    "semantic_scholar": {
        "homepage": "homepage_source",
        "title": "title_source",
        "department": "department_source",
        "email": "email_source",
    },
    "dblp": {
        "school": "school_source",
    },
    "crossref": {
        "school": "school_source",
    },
    "openalex": {
        "school": "school_source",
    },
}

# Minimum confidence to auto-write; below this → needs_review
CONFIDENCE_THRESHOLD = 0.7


@dataclass(frozen=True)
class EnrichmentCandidate:
    person_id: int
    name: str
    school: str
    personal_homepage: str
    title: str
    department: str
    email: str
    homepage_source: str
    title_source: str
    department_source: str
    email_source: str
    school_source: str
    enrichment_confidence: float
    primary_source_type: str


@dataclass(frozen=True)
class FieldUpdate:
    field: str
    new_value: str
    source: str
    confidence: float
    is_strong_evidence: bool
    requires_review: bool


@dataclass(frozen=True)
class EnrichmentResult:
    person_id: int
    updates: list[FieldUpdate]
    conflicts: list[str]
    skipped: list[str]
    errors: list[str]


def build_field_update(
    field: str,
    new_value: str,
    source: str,
    confidence: float,
    current_value: str,
    current_source: str,
    current_primary_source: str,
) -> FieldUpdate:
    """Decide whether a proposed field update should proceed or be flagged for review.

    Strong-override guard: official_site fields are never overwritten by any
    supplement source, regardless of confidence.
    """
    if not new_value or new_value == current_value:
        return FieldUpdate(field=field, new_value="", source="", confidence=0.0, is_strong_evidence=False, requires_review=False)

    source_strength = _source_strength(source)
    current_strength = _source_strength(current_source)
    current_primary_strength = _source_strength(current_primary_source) if current_primary_source else -1

    # Rule 1: official_site never overwrites official_site
    if current_primary_source == "official_site":
        return FieldUpdate(
            field=field,
            new_value="",
            source="",
            confidence=0.0,
            is_strong_evidence=False,
            requires_review=False,
        )

    # Rule 2: Weaker evidence never overwrites stronger evidence at the same tier
    # (but equal-or-better strength can improve / fill empty fields)
    if source_strength < current_strength and current_value:
        return FieldUpdate(
            field=field,
            new_value="",
            source="",
            confidence=0.0,
            is_strong_evidence=False,
            requires_review=False,
        )

    requires_review = confidence < CONFIDENCE_THRESHOLD
    return FieldUpdate(
        field=field,
        new_value=new_value,
        source=source,
        confidence=confidence,
        is_strong_evidence=(source_strength >= EvidenceStrength.SEMANTIC_SCHOLAR),
        requires_review=requires_review,
    )


def _source_strength(source: str) -> int:
    """Return EvidenceStrength value for a source string, or WEAK if unknown."""
    mapping = {
        "official_site": EvidenceStrength.OFFICIAL_SITE,
        "semantic_scholar": EvidenceStrength.SEMANTIC_SCHOLAR,
        "dblp": EvidenceStrength.DBLP,
        "crossref": EvidenceStrength.CROSSREF,
        "openalex": EvidenceStrength.OPENALEX,
    }
    return mapping.get(source, EvidenceStrength.WEAK)


def format_enrichment_result(result: EnrichmentResult) -> str:
    """Human-readable summary of an enrichment result."""
    lines = [f"Person ID: {result.person_id}"]
    if result.updates:
        lines.append("  Updates:")
        for u in result.updates:
            review_tag = " [REVIEW]" if u.requires_review else ""
            lines.append(f"    {u.field}: {u.new_value!r} (source={u.source}, conf={u.confidence:.2f}){review_tag}")
    if result.conflicts:
        lines.append(f"  Conflicts: {result.conflicts}")
    if result.skipped:
        lines.append(f"  Skipped (no improvement): {result.skipped}")
    if result.errors:
        lines.append(f"  Errors: {result.errors}")
    return "\n".join(lines)