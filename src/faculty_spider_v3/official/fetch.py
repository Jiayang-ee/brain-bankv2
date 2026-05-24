from __future__ import annotations

import hashlib
import time
from pathlib import Path

import requests

from faculty_spider_v3.config import RAW_HTML_DIR, REQUEST_RETRIES, REQUEST_TIMEOUT_SECONDS, USER_AGENT
from faculty_spider_v3.models import PageFetch


class StaticFetcher:
    def __init__(self, timeout: int = REQUEST_TIMEOUT_SECONDS, retries: int = REQUEST_RETRIES):
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def fetch(self, url: str) -> PageFetch:
        last_error = ""
        for attempt in range(self.retries + 1):
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.encoding = response.encoding or response.apparent_encoding or "utf-8"
                return PageFetch(
                    url=url,
                    status_code=response.status_code,
                    html=response.text,
                    encoding=response.encoding,
                    error="" if response.ok else f"HTTP {response.status_code}",
                )
            except requests.RequestException as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < self.retries:
                    time.sleep(0.5 * (attempt + 1))
        return PageFetch(url=url, status_code=None, html="", encoding="", error=last_error)


def content_hash(html: str) -> str:
    return hashlib.sha1(html.encode("utf-8", errors="replace")).hexdigest()


def save_raw_html(fetch: PageFetch, raw_dir: str | Path = RAW_HTML_DIR) -> Path:
    Path(raw_dir).mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(fetch.url.encode("utf-8")).hexdigest()
    path = Path(raw_dir) / f"{digest}.html"
    path.write_text(fetch.html, encoding="utf-8", errors="replace")
    return path
