from faculty_spider_v3.models import SchoolEntrypoint
from faculty_spider_v3.official.entrypoints import read_school_entrypoints, write_school_entrypoints_csv
from faculty_spider_v3.storage import FacultySpiderV3Store


def test_read_and_write_school_entrypoints(tmp_path):
    csv_path = tmp_path / "entrypoints.csv"
    entrypoints = [
        SchoolEntrypoint(
            school="Example University",
            unit="Business School",
            entry_url="https://example.edu/faculty",
            entry_type="html_directory",
            status="verified",
        )
    ]

    assert write_school_entrypoints_csv(entrypoints, csv_path) == 1
    loaded = read_school_entrypoints(csv_path)

    assert loaded == entrypoints


def test_store_school_entrypoints_filters_status_and_school(tmp_path):
    store = FacultySpiderV3Store(tmp_path / "test.sqlite")
    store.init_db()
    store.upsert_school_entrypoints(
        [
            SchoolEntrypoint("Example University", "Business School", "https://example.edu/faculty", status="verified"),
            SchoolEntrypoint("Other University", "Engineering", "https://other.edu/people", status="new"),
        ]
    )

    rows = store.list_school_entrypoints(school_names=["Example University"], statuses=["verified"])

    assert len(rows) == 1
    assert rows[0]["unit"] == "Business School"
    assert store.count("school_entrypoints") == 2
