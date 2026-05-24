from pathlib import Path

from faculty_spider_v3.official.seeds import read_school_seeds, write_school_seeds_csv
from faculty_spider_v3.storage import FacultySpiderV3Store


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
V1_TOP200 = WORKSPACE_ROOT / "faculty spiderv1" / "美国前200高校排名.xlsx"


def test_read_top50_school_seeds_from_v1_excel():
    seeds = read_school_seeds(V1_TOP200, limit=50)

    assert len(seeds) == 50
    assert seeds[0].rank == 1
    assert seeds[0].school_name_en == "Princeton University"
    assert seeds[0].school_name_zh == "普林斯顿大学"
    assert seeds[0].homepage_url


def test_write_and_import_top50_school_seed_csv(tmp_path):
    seeds = read_school_seeds(V1_TOP200, limit=50)
    csv_path = tmp_path / "us_top50_schools.csv"

    assert write_school_seeds_csv(seeds, csv_path) == 50
    reread = read_school_seeds(csv_path)
    assert len(reread) == 50

    store = FacultySpiderV3Store(tmp_path / "test.sqlite")
    store.init_db()
    assert store.upsert_school_seeds(reread) == 50
    assert store.count("school_seeds") == 50
