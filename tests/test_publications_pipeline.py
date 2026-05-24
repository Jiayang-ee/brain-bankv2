from faculty_spider_v3.models import Journal, PaperRecord
from faculty_spider_v3.publications.export import export_publication_candidates_csv, export_publication_people_candidates_csv, export_publication_quality_report_csv
from faculty_spider_v3.publications.openalex import default_from_year
from faculty_spider_v3.publications.pipeline import _journal_names_match
from faculty_spider_v3.storage import FacultySpiderV3Store


def test_upsert_papers_merges_openalex_and_crossref(tmp_path):
    store = FacultySpiderV3Store(tmp_path / "test.sqlite")
    store.init_db()
    store.upsert_journals(
        [
            Journal(
                source_file="test",
                journal_system="UTD",
                discipline="Management",
                journal_name="Management Science",
                issn_cn="",
                achievement_level="A+",
                talent_pool_use="强入库论文锚点",
            )
        ]
    )
    paper = PaperRecord(
        title="Platform Operations with AI",
        journal="Management Science",
        year=2025,
        doi="10.1287/test.2025.1",
        authors=({"name": "Yifan Chen", "position": "first", "affiliations": ["Example University"]},),
        first_author_name="Yifan Chen",
        source="openalex",
        paper_url="https://doi.org/10.1287/test.2025.1",
    )
    duplicate = PaperRecord(
        title="Platform Operations with AI",
        journal="Management Science",
        year=2025,
        doi="https://doi.org/10.1287/test.2025.1",
        authors=({"name": "Yifan Chen", "position": "first", "affiliations": ["Example University"]},),
        first_author_name="Yifan Chen",
        source="crossref",
    )

    assert store.upsert_papers([paper]) == 1
    assert store.upsert_papers([duplicate]) == 1
    assert store.count("papers") == 1
    row = store.paper_rows()[0]
    assert row["achievement_level"] == "A+"
    assert "openalex" in row["source"]
    assert "crossref" in row["source"]


def test_paper_candidate_rows_exports_first_and_corresponding_authors(tmp_path):
    store = FacultySpiderV3Store(tmp_path / "test.sqlite")
    store.init_db()
    store.upsert_papers(
        [
            PaperRecord(
                title="Optimization Paper",
                journal="Operations Research",
                year=2024,
                authors=(
                    {"name": "Yifan Chen", "position": "first", "affiliations": ["A"]},
                    {"name": "Wei Zhang", "is_corresponding": True, "affiliations": ["B"]},
                ),
                first_author_name="Yifan Chen",
                corresponding_author_names=("Wei Zhang",),
                source="openalex",
            )
        ]
    )

    rows = store.paper_candidate_rows()

    assert [row["author_role"] for row in rows] == ["first_author", "corresponding_author"]
    assert rows[0]["name"] == "Yifan Chen"
    assert rows[1]["name"] == "Wei Zhang"


def test_default_from_year_is_last_five_year_window():
    import datetime as dt

    assert default_from_year(dt.date(2026, 5, 21)) == 2022


def test_journal_name_matching_accepts_seed_aliases():
    assert _journal_names_match(
        "Transportation Research Part A: Policy and Practice",
        "TRANSPORTATION RESEARCH PART A-POLICY AND PRACTICE",
    )
    assert _journal_names_match(
        "Manufacturing &amp; Service Operations Management",
        "M&SOM-MANUFACTURING & SERVICE OPERATIONS MANAGEMENT",
    )
    assert _journal_names_match(
        "Omega",
        "OMEGA-INTERNATIONAL JOURNAL OF MANAGEMENT SCIENCE",
    )
    assert not _journal_names_match("Science", "MANAGEMENT SCIENCE")


def test_export_publication_candidates_filters_chinese_names(tmp_path):
    rows = [
        {
            "name": "Yifan Chen",
            "author_role": "first_author",
            "paper_id": 1,
            "title": "Paper",
            "journal": "Management Science",
            "achievement_level": "A+",
            "year": 2026,
            "doi": "",
            "paper_url": "",
            "source": "openalex",
            "affiliations": "",
        },
        {
            "name": "John Smith",
            "author_role": "first_author",
            "paper_id": 2,
            "title": "Paper",
            "journal": "Management Science",
            "achievement_level": "A+",
            "year": 2026,
            "doi": "",
            "paper_url": "",
            "source": "openalex",
            "affiliations": "",
        },
    ]
    output = tmp_path / "candidates.csv"

    assert export_publication_candidates_csv(rows, output, chinese_only=True) == 1
    text = output.read_text(encoding="utf-8-sig")
    assert "Yifan Chen" in text
    assert "John Smith" not in text
    assert "chinese_name_score" in text.splitlines()[0]


def test_export_publication_people_candidates_aggregates_by_author(tmp_path):
    rows = [
        {
            "name": "Yifan Chen",
            "author_role": "first_author",
            "paper_id": 1,
            "title": "Optimization Paper",
            "journal": "Management Science",
            "achievement_level": "A+",
            "year": 2026,
            "doi": "10.1/a",
            "paper_url": "https://doi.org/10.1/a",
            "source": "openalex",
            "affiliations": "Example University",
        },
        {
            "name": "Yifan Chen",
            "author_role": "corresponding_author",
            "paper_id": 2,
            "title": "Analytics Paper",
            "journal": "Information Systems Research",
            "achievement_level": "A1",
            "year": 2025,
            "doi": "10.1/b",
            "paper_url": "https://doi.org/10.1/b",
            "source": "crossref",
            "affiliations": "Example University",
        },
        {
            "name": "John Smith",
            "author_role": "first_author",
            "paper_id": 3,
            "title": "Other Paper",
            "journal": "Management Science",
            "achievement_level": "A+",
            "year": 2026,
            "doi": "",
            "paper_url": "",
            "source": "openalex",
            "affiliations": "",
        },
    ]
    output = tmp_path / "people_candidates.csv"

    assert export_publication_people_candidates_csv(rows, output) == 1
    text = output.read_text(encoding="utf-8-sig")
    assert "Yifan Chen" in text
    assert "John Smith" not in text
    assert "first_author_total" in text.splitlines()[0]
    assert "https://doi.org/10.1/a | https://doi.org/10.1/b" in text


def test_upsert_publication_people_candidates_creates_publication_only_person(tmp_path):
    store = FacultySpiderV3Store(tmp_path / "test.sqlite")
    store.init_db()
    candidates = [
        {
            "name": "Yifan Chen",
            "affiliations": "Example University",
            "last_5_year_total": 1,
            "first_author_total": 1,
            "corresponding_author_total": 0,
            "top_total": 0,
            "a_plus_total": 1,
            "a_total": 0,
            "a1_total": 0,
            "a2_total": 0,
            "level_counts_json": '{"A+": 1}',
            "paper_links": "https://doi.org/10.1/a",
            "paper_titles": "Optimization Paper",
            "journals": "Management Science",
            "years": "2026",
            "author_roles": "first_author",
            "is_likely_chinese_name": 1,
            "chinese_name_score": 0.7,
            "name_filter_reason": "chinese_surname",
            "review_status": "strong_candidate",
        }
    ]

    result = store.upsert_publication_people_candidates(candidates)

    assert result == {"inserted": 1, "updated": 0}
    row = store.people_rows()[0]
    assert row["name"] == "Yifan Chen"
    assert row["school"] == "Example University"
    assert row["primary_source_type"] == "publication"
    assert "Optimization Paper" in row["publications_json"]
    assert "last_5_year_total" in row["publication_stats_json"]
    assert row["review_status"] == "needs_review"


def test_export_publication_quality_report(tmp_path):
    store = FacultySpiderV3Store(tmp_path / "test.sqlite")
    store.init_db()
    store.upsert_journals(
        [
            Journal(
                source_file="test",
                journal_system="UTD",
                discipline="Management",
                journal_name="Management Science",
                issn_cn="",
                achievement_level="A+",
                talent_pool_use="强入库论文锚点",
            )
        ]
    )
    store.upsert_papers(
        [
            PaperRecord(
                title="Platform Operations with AI",
                journal="Management Science",
                year=2026,
                authors=({"name": "Yifan Chen", "position": "first", "affiliations": ["Example University"]},),
                first_author_name="Yifan Chen",
                source="openalex,crossref",
            )
        ]
    )
    output = tmp_path / "quality.csv"

    assert export_publication_quality_report_csv(store.list_journals(), store.paper_rows(), store.paper_candidate_rows(), store.review_issue_rows(), output) == 1
    text = output.read_text(encoding="utf-8-sig")
    assert "merged_count" in text.splitlines()[0]
    assert "Management Science" in text
