from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse

import requests

from faculty_spider_v3.config import FACULTY_PHOTO_DIR, REQUEST_TIMEOUT_SECONDS, USER_AGENT


def save_photo(url: str, photo_dir: str | Path = FACULTY_PHOTO_DIR) -> str:
    if not url:
        return ""
    Path(photo_dir).mkdir(parents=True, exist_ok=True)
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT})
        if not response.ok or not response.content:
            return ""
    except requests.RequestException:
        return ""
    suffix = _suffix_from_url(url) or _suffix_from_content_type(response.headers.get("content-type", ""))
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    path = Path(photo_dir) / f"{digest}{suffix or '.jpg'}"
    path.write_bytes(response.content)
    return str(path)


def _suffix_from_url(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp"} else ""


def _suffix_from_content_type(content_type: str) -> str:
    if "png" in content_type:
        return ".png"
    if "gif" in content_type:
        return ".gif"
    if "webp" in content_type:
        return ".webp"
    if "jpeg" in content_type or "jpg" in content_type:
        return ".jpg"
    return ""
