import sqlite3

from faculty_spider_v3.models import PageFetch, SchoolEntrypoint, SchoolSeed
from faculty_spider_v3.official.export import export_page_audit_csv, export_people_csv
from faculty_spider_v3.official.pipeline import (
    discover_from_school_entrypoints,
    discover_from_school_seeds,
    extract_html_profiles,
    fetch_candidate_links,
    mark_llm_triggers,
)
from faculty_spider_v3.storage import FacultySpiderV3Store


ROOT_HTML = """
<html><body>
  <a href="/people/yifan-chen">Yifan Chen Faculty Profile</a>
  <a href="/news/story">News</a>
</body></html>
"""

PROFILE_HTML = """
<html><body>
  <h1>Yifan Chen</h1>
  <p class="job-title">Assistant Professor</p>
  <p class="department">Department of Management Science</p>
  <a href="mailto:yifan.chen@example.edu">Email</a>
  <h2>Research Interests</h2><p>Decision analytics.</p>
  <h2>Education</h2><p>PhD, Tsinghua University. Advisor: Wei Zhang.</p>
</body></html>
"""


class FakeFetcher:
    def __init__(self, pages):
        self.pages = pages

    def fetch(self, url):
        html = self.pages.get(url, "")
        if html:
            return PageFetch(url=url, status_code=200, html=html, encoding="utf-8")
        return PageFetch(url=url, status_code=404, html="", encoding="", error="HTTP 404")


def test_official_pipeline_discovers_fetches_and_extracts(tmp_path):
    store = FacultySpiderV3Store(tmp_path / "test.sqlite")
    store.init_db()
    store.upsert_school_seeds([SchoolSeed(rank=1, school_name_en="Example University", homepage_url="https://example.edu")])
    fetcher = FakeFetcher({"https://example.edu": ROOT_HTML, "https://example.edu/people/yifan-chen": PROFILE_HTML})

    discover_result = discover_from_school_seeds(store, limit=1, links_per_school=5, fetcher=fetcher, raw_html_dir=tmp_path / "raw")
    assert discover_result.candidate_links_saved == 1
    assert store.count("candidate_links") == 1

    fetch_result = fetch_candidate_links(store, limit=5, fetcher=fetcher, raw_html_dir=tmp_path / "raw")
    assert fetch_result.pages_saved == 1

    extract_result = extract_html_profiles(store, limit=5)
    assert extract_result.people_saved == 1
    assert store.count("people") == 1

    conn = sqlite3.connect(tmp_path / "test.sqlite")
    row = conn.execute("select name, school, is_likely_chinese_name from people").fetchone()
    assert row == ("Yifan Chen", "Example University", 1)


def test_discover_marks_root_faculty_list_pending(tmp_path):
    store = FacultySpiderV3Store(tmp_path / "test.sqlite")
    store.init_db()
    store.upsert_school_seeds([SchoolSeed(rank=1, school_name_en="Example University", homepage_url="https://example.edu")])
    fetcher = FakeFetcher({"https://example.edu": ROOT_HTML})

    discover_from_school_seeds(store, limit=1, links_per_school=5, fetcher=fetcher, raw_html_dir=tmp_path / "raw")

    conn = sqlite3.connect(tmp_path / "test.sqlite")
    row = conn.execute("select page_type, parser_status from pages where url = 'https://example.edu/'").fetchone()
    assert row == ("faculty_list", "pending")


def test_discover_from_school_entrypoints_saves_list_page_and_candidates(tmp_path):
    store = FacultySpiderV3Store(tmp_path / "test.sqlite")
    store.init_db()
    store.upsert_school_entrypoints(
        [
            SchoolEntrypoint(
                school="Example University",
                unit="Business School",
                entry_url="https://example.edu/business/faculty",
                entry_type="html_directory",
                status="verified",
            )
        ]
    )
    fetcher = FakeFetcher({"https://example.edu/business/faculty": ROOT_HTML})

    result = discover_from_school_entrypoints(store, limit=5, links_per_entrypoint=5, fetcher=fetcher, raw_html_dir=tmp_path / "raw")

    assert result.schools_processed == 1
    assert result.candidate_links_saved == 1
    conn = sqlite3.connect(tmp_path / "test.sqlite")
    page_row = conn.execute("select school, department, page_type, parser_status from pages").fetchone()
    link_row = conn.execute("select school, department from candidate_links").fetchone()
    assert page_row == ("Example University", "Business School", "faculty_list", "pending")
    assert link_row == ("Example University", "Business School")


def test_mark_llm_triggers_marks_sparse_page(tmp_path):
    store = FacultySpiderV3Store(tmp_path / "test.sqlite")
    store.init_db()
    fetch = PageFetch(url="https://example.edu/people/yifan-chen", status_code=200, html="<h1>Yifan Chen</h1><p>Biography Research Education</p>", encoding="utf-8")
    raw_path = tmp_path / "raw.html"
    raw_path.write_text(fetch.html, encoding="utf-8")
    store.save_page(fetch, page_type="faculty_candidate", raw_html_path=str(raw_path), parser_status="pending")

    result = mark_llm_triggers(store, limit=5)

    assert result.pages_marked == 1
    assert store.count("review_issues") == 1


def test_official_exports_people_and_page_audit(tmp_path):
    store = FacultySpiderV3Store(tmp_path / "test.sqlite")
    store.init_db()
    store.upsert_school_seeds([SchoolSeed(rank=1, school_name_en="Example University", homepage_url="https://example.edu")])
    fetcher = FakeFetcher({"https://example.edu": ROOT_HTML, "https://example.edu/people/yifan-chen": PROFILE_HTML})
    discover_from_school_seeds(store, limit=1, links_per_school=5, fetcher=fetcher, raw_html_dir=tmp_path / "raw")
    fetch_candidate_links(store, limit=5, fetcher=fetcher, raw_html_dir=tmp_path / "raw")
    extract_html_profiles(store, limit=5)

    people_csv = tmp_path / "people.csv"
    audit_csv = tmp_path / "page_audit.csv"
    assert export_people_csv(store.people_rows(), people_csv) == 1
    assert export_page_audit_csv(store.page_audit_rows(), audit_csv) >= 2
    assert "Yifan Chen" in people_csv.read_text(encoding="utf-8-sig")
    assert "parser_status" in audit_csv.read_text(encoding="utf-8-sig").splitlines()[0]
