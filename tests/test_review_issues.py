import csv

from faculty_spider_v3.review.issues import export_review_issues_csv
from faculty_spider_v3.storage import FacultySpiderV3Store


def test_export_review_issues_csv(tmp_path):
    store = FacultySpiderV3Store(tmp_path / "test.sqlite")
    store.init_db()
    issue_id = store.add_review_issue(
        issue_type="name_filter_uncertain",
        severity="medium",
        message="Chinese-name score is in review band.",
        related_table="people",
        related_id=12,
        source_url="https://example.edu/profile",
    )

    rows = store.review_issue_rows()
    assert rows[0]["id"] == issue_id

    csv_path = tmp_path / "issues.csv"
    assert export_review_issues_csv(rows, csv_path) == 1

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        exported = list(csv.DictReader(handle))
    assert exported[0]["issue_type"] == "name_filter_uncertain"
    assert exported[0]["source_url"] == "https://example.edu/profile"
