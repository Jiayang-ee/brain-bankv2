import sqlite3

from faculty_spider_v3.models import PersonProfile
from faculty_spider_v3.storage import FacultySpiderV3Store
from faculty_spider_v3.urls import canonicalize_url


def test_init_db_creates_core_tables(tmp_path):
    store = FacultySpiderV3Store(tmp_path / "test.sqlite")
    store.init_db()

    assert store.count("sources") == 0
    assert store.count("school_seeds") == 0
    assert store.count("journals") == 0
    assert store.count("people") == 0
    assert store.count("review_issues") == 0


def test_canonicalize_url_normalizes_http_https_and_query_order():
    assert canonicalize_url("http://WWW.TC.COLUMBIA.EDU/faculty/al3288/?b=2&a=1#bio") == "https://www.tc.columbia.edu/faculty/al3288/?a=1&b=2"


def test_people_upsert_uses_canonical_source_url(tmp_path):
    store = FacultySpiderV3Store(tmp_path / "test.sqlite")
    store.init_db()
    base = dict(
        name="Aitong Li",
        school="Columbia University",
        department="",
        title="Assistant Professor",
        email="",
        personal_homepage="",
        research_interests="",
        biography="",
        publications="",
        photo_url="",
        photo_path="",
        education="",
        advisor="",
        source_text="",
        extraction_method="html_rule",
        confidence_score=0.6,
    )

    store.upsert_person_profile(PersonProfile(**dict(base, source_url="http://www.tc.columbia.edu/faculty/al3288/")), True, 0.7, "")
    store.upsert_person_profile(PersonProfile(**dict(base, source_url="https://www.tc.columbia.edu/faculty/al3288/", email="aitong@example.edu")), True, 0.8, "")

    assert store.count("people") == 1
    conn = sqlite3.connect(tmp_path / "test.sqlite")
    row = conn.execute("select email, primary_source_url from people").fetchone()
    assert row == ("aitong@example.edu", "https://www.tc.columbia.edu/faculty/al3288/")


def test_people_upsert_stores_discipline_score(tmp_path):
    store = FacultySpiderV3Store(tmp_path / "test.sqlite")
    store.init_db()
    profile = PersonProfile(
        name="Yifan Chen",
        school="Example University",
        department="Department of Management Science",
        title="Assistant Professor",
        email="",
        source_url="https://example.edu/faculty/yifan-chen",
        personal_homepage="",
        research_interests="Operations research and supply chain analytics.",
        biography="",
        publications="",
        photo_url="",
        photo_path="",
        education="",
        advisor="",
        source_text="",
        extraction_method="html_rule",
        confidence_score=0.8,
    )
    from faculty_spider_v3.discipline.filter import score_discipline_relevance

    discipline_score = score_discipline_relevance(
        department=profile.department,
        research_interests=profile.research_interests,
    )
    store.upsert_person_profile(profile, True, 0.8, "", discipline_score=discipline_score)

    row = store.people_rows()[0]
    assert row["discipline_is_relevant"] == 1
    assert row["discipline_review_status"] == "accepted"
    assert "management_science" in row["discipline_matched_disciplines_json"]
