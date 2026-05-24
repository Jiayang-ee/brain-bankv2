from pathlib import Path

from faculty_spider_v3.publications.journal_list import read_journals_csv
from faculty_spider_v3.storage import FacultySpiderV3Store


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_read_journals_csv_from_v3_list():
    journals = read_journals_csv(PROJECT_ROOT / "管理科学与工程相关期刊筛选清单.csv")

    assert len(journals) == 51
    assert journals[0].journal_name == "管理世界"
    assert journals[0].achievement_level == "A+(TOP)"


def test_upsert_journals(tmp_path):
    store = FacultySpiderV3Store(tmp_path / "test.sqlite")
    store.init_db()
    journals = read_journals_csv(PROJECT_ROOT / "管理科学与工程相关期刊筛选清单.csv")

    assert store.upsert_journals(journals) == 51
    assert store.count("journals") == 51
    assert store.upsert_journals(journals) == 51
    assert store.count("journals") == 51
