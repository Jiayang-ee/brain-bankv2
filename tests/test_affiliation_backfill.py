from faculty_spider_v3.models import PaperRecord
from faculty_spider_v3.publications import affiliation_backfill
from faculty_spider_v3.publications.affiliation_backfill import _affiliations_from_citation_meta
from faculty_spider_v3.storage import FacultySpiderV3Store


class FakeOpenAlexClient:
    def work_by_doi(self, doi, fallback_journal=""):
        if doi == "10.1/with-aff":
            return PaperRecord(
                title="Paper",
                journal=fallback_journal,
                year=2026,
                doi=doi,
                authors=(
                    {"name": "Yifan Chen", "position": "first", "affiliations": ["Example University"]},
                    {"name": "Wei Zhang", "position": "middle", "affiliations": ["Example University"]},
                ),
                first_author_name="Yifan Chen",
                affiliations=("Example University",),
                source_api_url="https://openalex.org/W1",
            )
        return PaperRecord(title="Paper", journal=fallback_journal, year=2026, doi=doi)


def test_backfill_missing_affiliations_from_openalex(tmp_path, monkeypatch):
    store = FacultySpiderV3Store(tmp_path / "test.sqlite")
    store.init_db()
    store.upsert_papers(
        [
            PaperRecord(
                title="Paper",
                journal="Management Science",
                year=2026,
                doi="10.1/with-aff",
                authors=({"name": "Yifan Chen", "position": "first", "affiliations": []},),
                first_author_name="Yifan Chen",
                source="crossref",
            )
        ]
    )
    monkeypatch.setattr(affiliation_backfill, "OpenAlexClient", FakeOpenAlexClient)

    result = affiliation_backfill.backfill_missing_affiliations(store, refresh_exports=False)

    assert result.openalex_updated == 1
    assert result.still_missing == 0
    row = store.paper_rows()[0]
    assert "Example University" in row["affiliations_json"]
    assert "Example University" in row["authors_json"]


def test_citation_meta_affiliations_parser():
    html = """
    <html><head>
      <meta name="citation_author" content="Yifan Chen">
      <meta name="citation_author_institution" content="Example University">
      <meta name="citation_author" content="Wei Zhang">
      <meta name="citation_author_institution" content="Another University">
    </head></html>
    """

    authors, affiliations = _affiliations_from_citation_meta(html)

    assert authors == ["Yifan Chen", "Wei Zhang"]
    assert affiliations == ["Example University", "Another University"]
