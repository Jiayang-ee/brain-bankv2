from __future__ import annotations

import requests
import re

from faculty_spider_v3.config import REQUEST_TIMEOUT_SECONDS, USER_AGENT
from faculty_spider_v3.models import PaperRecord

CROSSREF_WORKS_URL = "https://api.crossref.org/works"


class CrossrefClient:
    def __init__(self, timeout: int = REQUEST_TIMEOUT_SECONDS):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.timeout = timeout

    def search_works_by_journal(self, journal_name: str, from_year: int, per_page: int = 25, issn: str = "") -> list[PaperRecord]:
        filters = [f"from-pub-date:{from_year}-01-01", "type:journal-article"]
        normalized_issn = _first_issn(issn)
        if normalized_issn:
            filters.append(f"issn:{normalized_issn}")
        response = self.session.get(
            CROSSREF_WORKS_URL,
            params={
                "query.container-title": journal_name,
                "filter": ",".join(filters),
                "rows": per_page,
                "sort": "published",
                "order": "desc",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return [_paper_from_item(item, journal_name) for item in response.json().get("message", {}).get("items", [])]


def _paper_from_item(item: dict, fallback_journal: str) -> PaperRecord:
    authors = []
    affiliations: list[str] = []
    for idx, author in enumerate(item.get("author") or []):
        name = _author_name(author)
        author_affiliations = [aff.get("name", "") for aff in author.get("affiliation") or [] if aff.get("name")]
        affiliations.extend(author_affiliations)
        authors.append(
            {
                "name": name,
                "orcid": author.get("ORCID", ""),
                "position": "first" if idx == 0 else "",
                "is_corresponding": author.get("sequence") == "first" and bool(author.get("authenticated-orcid")),
                "affiliations": author_affiliations,
            }
        )
    title = " ".join(item.get("title") or [])
    journal = " ".join(item.get("container-title") or []) or fallback_journal
    year = _published_year(item)
    doi = item.get("DOI", "")
    return PaperRecord(
        title=title,
        journal=journal,
        year=year,
        doi=doi,
        url=item.get("URL", ""),
        abstract=item.get("abstract", ""),
        authors=tuple(authors),
        first_author_name=authors[0]["name"] if authors else "",
        corresponding_author_names=(),
        affiliations=tuple(dict.fromkeys(affiliations)),
        source="crossref",
        paper_url=item.get("URL", "") or (f"https://doi.org/{doi}" if doi else ""),
        source_api_url=item.get("URL", ""),
    )


def _author_name(author: dict) -> str:
    given = author.get("given", "")
    family = author.get("family", "")
    literal = author.get("name", "")
    return " ".join(part for part in (given, family) if part).strip() or literal


def _published_year(item: dict) -> int | None:
    for key in ("published-print", "published-online", "published", "issued"):
        parts = item.get(key, {}).get("date-parts") or []
        if parts and parts[0]:
            return int(parts[0][0])
    return None


def _first_issn(value: str) -> str:
    match = re.search(r"\b\d{4}-[\dXx]{4}\b", value or "")
    return match.group(0) if match else ""
