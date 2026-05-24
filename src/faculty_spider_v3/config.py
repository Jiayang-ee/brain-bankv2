from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
SEED_DIR = DATA_DIR / "seeds"
RAW_HTML_DIR = DATA_DIR / "raw_html"
FACULTY_PHOTO_DIR = DATA_DIR / "faculty_photos"
EXPORT_DIR = DATA_DIR / "exports"
REVIEW_DIR = DATA_DIR / "review"
LOG_DIR = PROJECT_ROOT / "logs"
DEFAULT_DB = DATA_DIR / "faculty_spider_v3.sqlite"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 "
    "FacultySpiderV3/0.1"
)
REQUEST_TIMEOUT_SECONDS = 20
REQUEST_RETRIES = 2


def ensure_runtime_dirs() -> None:
    for path in (DATA_DIR, SEED_DIR, RAW_HTML_DIR, FACULTY_PHOTO_DIR, EXPORT_DIR, REVIEW_DIR, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)
