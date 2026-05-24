from __future__ import annotations

import json
import re
from html import unescape
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from faculty_spider_v3.models import LinkCandidate
from faculty_spider_v3.urls import canonicalize_url

NOISE_RE = re.compile(
    r"news|events?|alumni|admissions?|library|athletics|giving|facebook|twitter|instagram|linkedin|"
    r"youtube|calendar|maps?|contact|privacy|accessibility|copyright|apply|tuition|donate|socialmedia|"
    r"student|undergraduate|graduate|catalog|login|gdpr|human-resources|careers?|jobs?|registrar|"
    r"titleix|publicsafety|website-feedback|visit|tours?|history|awards?|commencement",
    re.I,
)
STATIC_FILE_RE = re.compile(r"\.(?:pdf|docx?|xlsx?|pptx?|zip|jpg|jpeg|png|gif|svg)(?:$|\?)", re.I)
FACULTY_RE = re.compile(r"faculty|people|profile|profiles|directory|staff|professor|lecturer|instructor|postdoc|phd|doctoral|fellows?", re.I)
ORG_RE = re.compile(r"department|school|college|center|centre|institute|program|research|lab|academics?", re.I)
TARGET_FIELD_RE = re.compile(
    r"management|business|operations?|information systems?|analytics|decision|industrial engineering|"
    r"systems engineering|data science|statistics|economics|finance|marketing|accounting|mse|orfe|"
    r"管理|运筹|决策|信息系统|数据|统计|金融|市场",
    re.I,
)
PROFILE_HINT_RE = re.compile(r"professor|associate professor|assistant professor|lecturer|postdoctoral|phd|faculty profile|email", re.I)


def classify_link(url: str, anchor_text: str) -> tuple[str, float]:
    haystack = f"{url} {anchor_text}".lower()
    path = urlparse(url).path
    if STATIC_FILE_RE.search(path) or NOISE_RE.search(haystack):
        return "noise", 0.1
    if FACULTY_RE.search(haystack):
        boost = 0.08 if TARGET_FIELD_RE.search(haystack) else 0.0
        if re.search(r"profile|profiles/[^/]+|/people/[^/]+|/faculty/[^/]+|person|bio", haystack):
            return "faculty_candidate", min(0.9, 0.78 + boost)
        return "faculty_list", min(0.84, 0.68 + boost)
    if ORG_RE.search(haystack):
        boost = 0.12 if TARGET_FIELD_RE.search(haystack) else 0.0
        return "organization", min(0.72, 0.55 + boost)
    return "unknown", 0.25


def discover_links(html: str, base_url: str, same_domain: bool = True) -> list[LinkCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    base_netloc = urlparse(base_url).netloc.lower()
    candidates: list[LinkCandidate] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        anchor_text = " ".join(anchor.get_text(" ", strip=True).split())
        _append_candidate(candidates, seen, base_url, base_netloc, anchor["href"], anchor_text, same_domain)

    for script in soup.select("script.fd-content-json"):
        try:
            items = json.loads(script.get_text())
        except json.JSONDecodeError:
            continue
        for item in items:
            template = unescape(str(item.get("template", "")))
            item_soup = BeautifulSoup(template, "html.parser")
            for anchor in item_soup.find_all("a", href=True):
                anchor_text = " ".join(anchor.get_text(" ", strip=True).split()) or str(item.get("name", "")).strip()
                _append_candidate(candidates, seen, base_url, base_netloc, anchor["href"], anchor_text, same_domain)
    return candidates


def classify_page(html: str, url: str) -> tuple[str, float]:
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one("script.fd-content-json"):
        return "faculty_list", 0.86
    profile_link_count = sum(1 for anchor in soup.find_all("a", href=True) if re.search(r"/faculty/[^/]+|/people/[^/]+|/profiles/[^/]+", anchor["href"], re.I))
    if profile_link_count >= 8:
        return "faculty_list", 0.82
    text = soup.get_text(" ", strip=True)
    haystack = f"{url} {text[:5000]}"
    if PROFILE_HINT_RE.search(haystack) and (re.search(r"@", haystack) or re.search(r"biography|research|education", haystack, re.I)):
        return "faculty_profile", 0.82
    if FACULTY_RE.search(haystack):
        return "faculty_list", 0.65
    if ORG_RE.search(haystack):
        return "organization", 0.55
    return "unknown", 0.25


def useful_candidates(candidates: list[LinkCandidate], limit: int) -> list[LinkCandidate]:
    useful = [candidate for candidate in candidates if candidate.page_type != "noise"]
    useful.sort(key=lambda item: item.confidence_score, reverse=True)
    return useful[:limit]


def _append_candidate(candidates: list[LinkCandidate], seen: set[str], base_url: str, base_netloc: str, href: str, anchor_text: str, same_domain: bool) -> None:
    absolute_url = canonicalize_url(urljoin(base_url, href).split("#", 1)[0])
    canonical_base_url = canonicalize_url(base_url)
    parsed = urlparse(absolute_url)
    if parsed.scheme not in {"http", "https"} or STATIC_FILE_RE.search(parsed.path):
        return
    if absolute_url.rstrip("/") == canonical_base_url.rstrip("/"):
        return
    if same_domain and parsed.netloc.lower() and not _same_site(base_netloc, parsed.netloc.lower()):
        return
    if absolute_url in seen:
        return
    seen.add(absolute_url)
    page_type, confidence = classify_link(absolute_url, anchor_text)
    candidates.append(LinkCandidate(absolute_url, canonical_base_url, anchor_text, page_type, confidence))


def _same_site(base_netloc: str, candidate_netloc: str) -> bool:
    if candidate_netloc == base_netloc or candidate_netloc.endswith("." + base_netloc):
        return True
    base_parts = base_netloc.split(".")
    if len(base_parts) >= 2:
        base_root = ".".join(base_parts[-2:])
        return candidate_netloc == base_root or candidate_netloc.endswith("." + base_root)
    return False
