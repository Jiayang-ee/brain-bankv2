from __future__ import annotations

from datetime import date

import requests

from faculty_spider_v3.config import REQUEST_TIMEOUT_SECONDS, USER_AGENT
from faculty_spider_v3.models import PaperRecord

OPENALEX_BASE = "https://api.openalex.org"


class OpenAlexClient:
    def __init__(self, timeout: int = REQUEST_TIMEOUT_SECONDS):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.timeout = timeout

    def search_works_by_journal(self, journal_name: str, from_year: int, per_page: int = 25) -> list[PaperRecord]:
        source_id = self._source_id_for_journal(journal_name)
        params = {
            "per-page": per_page,
            "sort": "publication_date:desc",
            "filter": f"from_publication_date:{from_year}-01-01",
        }
        if source_id:
            params["filter"] += f",primary_location.source.id:{source_id}"
        else:
            params["search"] = journal_name
        response = self.session.get(f"{OPENALEX_BASE}/works", params=params, timeout=self.timeout)
        response.raise_for_status()
        return [_paper_from_work(item, journal_name) for item in response.json().get("results", [])]

    def work_by_doi(self, doi: str, fallback_journal: str = "") -> PaperRecord | None:
        normalized_doi = doi.removeprefix("https://doi.org/").removeprefix("http://doi.org/").strip().lower()
        if not normalized_doi:
            return None
        response = self.session.get(
            f"{OPENALEX_BASE}/works",
            params={"filter": f"doi:{normalized_doi}", "per-page": 1},
            timeout=self.timeout,
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        if not results:
            return None
        return _paper_from_work(results[0], fallback_journal)

    def _source_id_for_journal(self, journal_name: str) -> str:
        response = self.session.get(
            f"{OPENALEX_BASE}/sources",
            params={"search": journal_name, "per-page": 5},
            timeout=self.timeout,
        )
        response.raise_for_status()
        normalized = journal_name.casefold().strip()
        for item in response.json().get("results", []):
            display_name = str(item.get("display_name") or "").casefold().strip()
            if display_name == normalized:
                return str(item.get("id", "")).rsplit("/", 1)[-1]
        results = response.json().get("results", [])
        return str(results[0].get("id", "")).rsplit("/", 1)[-1] if results else ""


def _paper_from_work(item: dict, fallback_journal: str) -> PaperRecord:
    authors = []
    affiliations: list[str] = []
    for authorship in item.get("authorships") or []:
        author = authorship.get("author") or {}
        institutions = [inst.get("display_name", "") for inst in authorship.get("institutions") or [] if inst.get("display_name")]
        affiliations.extend(institutions)
        authors.append(
            {
                "name": author.get("display_name", ""),
                "author_id": author.get("id", ""),
                "position": authorship.get("author_position", ""),
                "is_corresponding": bool(authorship.get("is_corresponding")),
                "affiliations": institutions,
            }
        )
    first_author = next((author["name"] for author in authors if author.get("position") == "first"), "")
    if not first_author and authors:
        first_author = authors[0]["name"]
    corresponding = tuple(author["name"] for author in authors if author.get("is_corresponding") and author.get("name"))
    source = ((item.get("primary_location") or {}).get("source") or {}).get("display_name") or fallback_journal
    year = item.get("publication_year")
    return PaperRecord(
        title=item.get("title") or "",
        journal=source,
        year=int(year) if year else None,
        doi=item.get("doi") or "",
        url=item.get("id") or "",
        abstract="",
        authors=tuple(authors),
        first_author_name=first_author,
        corresponding_author_names=corresponding,
        affiliations=tuple(dict.fromkeys(affiliations)),
        source="openalex",
        paper_url=((item.get("primary_location") or {}).get("landing_page_url") or item.get("doi") or item.get("id") or ""),
        source_api_url=item.get("id") or "",
    )


def default_from_year(today: date | None = None) -> int:
    today = today or date.today()
    return today.year - 4
