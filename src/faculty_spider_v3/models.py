from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SchoolSeed:
    rank: Optional[int]
    school_name_en: str
    school_name_zh: str = ""
    homepage_url: str = ""
    difficulty_level: Optional[int] = None
    crawl_status: str = ""
    notes: str = ""


@dataclass(frozen=True)
class SchoolEntrypoint:
    school: str
    unit: str
    entry_url: str
    entry_type: str = ""
    url_pattern: str = ""
    pagination_pattern: str = ""
    person_link_selector: str = ""
    api_endpoint: str = ""
    roles_included: str = ""
    notes: str = ""
    status: str = "new"


@dataclass(frozen=True)
class Journal:
    source_file: str
    journal_system: str
    discipline: str
    journal_name: str
    issn_cn: str
    achievement_level: str
    talent_pool_use: str
    notes: str = ""


@dataclass(frozen=True)
class PaperRecord:
    title: str
    journal: str
    year: Optional[int]
    doi: str = ""
    url: str = ""
    abstract: str = ""
    authors: tuple[dict, ...] = ()
    first_author_name: str = ""
    corresponding_author_names: tuple[str, ...] = ()
    affiliations: tuple[str, ...] = ()
    source: str = ""
    paper_url: str = ""
    source_api_url: str = ""
    achievement_level: str = ""


@dataclass(frozen=True)
class PageFetch:
    url: str
    status_code: Optional[int]
    html: str
    encoding: str
    error: str = ""


@dataclass(frozen=True)
class LinkCandidate:
    url: str
    source_url: str
    anchor_text: str
    page_type: str
    confidence_score: float


@dataclass(frozen=True)
class PersonProfile:
    name: str
    school: str
    department: str
    title: str
    email: str
    source_url: str
    personal_homepage: str
    research_interests: str
    biography: str
    publications: str
    photo_url: str
    photo_path: str
    education: str
    advisor: str
    source_text: str
    extraction_method: str
    confidence_score: float
