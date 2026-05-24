from __future__ import annotations

import json
import re
from html import unescape
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from faculty_spider_v3.models import PersonProfile
from faculty_spider_v3.urls import canonicalize_url

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
TITLE_RE = re.compile(
    r"\b(Assistant Professor|Associate Professor|Professor|Postdoctoral Fellow|Postdoctoral Researcher|"
    r"PhD Student|Doctoral Student|Research Scientist|Lecturer|Instructor|Professor of Practice|Dean|Chair)\b",
    re.I,
)
GENERIC_NAME_RE = re.compile(
    r"^(faculty|people|profiles?|directory|staff|students?|research|department|school|college)$|"
    r"faculty profiles?|faculty directory|research centers?|open positions?",
    re.I,
)
STOP_SECTION_RE = re.compile(
    r"^(Education|Teaching|Publications?|Selected Publications?|Biography|Bio|About|Contact|Email|Courses?|Awards?|"
    r"Affiliation|Affiliations?|TC Affiliations|Faculty Expertise|Office Hours?|Research|Research Interests?|"
    r"Scholarly Interests|Advisor|Advisors?|Active Professional Organizations?|Current Projects?|Grants?)$",
    re.I,
)
LLM_LABEL_RE = re.compile(r"Biography|Research|Education|Advisor|PhD|Postdoctoral|Publications", re.I)


def clean_text(text: str) -> str:
    return " ".join(text.split())


def extract_person_profile(html: str, profile_url: str, school: str = "") -> PersonProfile:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    source_text = clean_text(soup.get_text(" ", strip=True))

    name = _best_name(soup)
    email = _email_from_soup(soup, source_text)
    title = _title_near_name(soup, name, source_text)
    department = _department_from_soup(soup, source_text)
    research = (
        _section_from_dom(soup, ("Scholarly Interests", "Research Interests?", "Research Areas?", "Areas of Expertise", "Faculty Expertise", "Research Summary"))
        or _label_value_from_dom(soup, ("Faculty Expertise",))
        or _section_after_label(source_text, r"Scholarly Interests|Research Interests?|Research Areas?|Areas of Expertise|Faculty Expertise")
        or _research_sentence_from_text(source_text)
    )
    biography = _section_from_dom(soup, ("Biographical Information", "Biography", "Bio", "About", "Profile")) or _section_after_label(
        source_text, r"Biographical Information|Biography|Bio"
    )
    publications = _section_from_dom(soup, ("Publications?", "Selected Publications")) or _section_after_label(
        source_text, r"Publications?|Selected Publications"
    )
    education = _section_from_dom(soup, ("Educational Background", "Education", "Degrees?")) or _section_after_label(
        source_text, r"Educational Background|Education\s*:|Degrees?\s*:"
    )
    advisor = _section_after_label(
        source_text,
        r"\b(?:Advisor|Advisors?|Supervisor|Supervisors?)\b\s*:",
        stop_pattern=r"(Education|Research|Publications|Biography|Contact|Email)",
    )
    photo_url = _photo_url_from_soup(soup, profile_url, name)
    personal_homepage = _personal_homepage_from_soup(soup, profile_url)

    useful_fields = [name, title, email, school, department, research, biography, education, advisor, photo_url]
    confidence = round(sum(1 for value in useful_fields if value) / len(useful_fields), 2)

    return PersonProfile(
        name=name,
        school=school,
        department=department,
        title=title,
        email=email,
        source_url=profile_url,
        personal_homepage=personal_homepage,
        research_interests=research,
        biography=biography,
        publications=publications,
        photo_url=photo_url,
        photo_path="",
        education=education,
        advisor=advisor,
        source_text=source_text[:10000],
        extraction_method="html_rule",
        confidence_score=confidence,
    )


def extract_people_from_list_page(html: str, page_url: str, school: str = "") -> list[PersonProfile]:
    soup = BeautifulSoup(html, "html.parser")
    profiles: list[PersonProfile] = _profiles_from_fd_content_json(soup, page_url, school)
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    seen: set[tuple[str, str]] = {(profile.name.casefold(), profile.source_url) for profile in profiles}
    selectors = (
        "article",
        "li",
        "div[class*=person]",
        "div[class*=people]",
        "div[class*=profile]",
        "div[class*=faculty]",
        "div[class*=card]",
    )
    for node in soup.select(",".join(selectors)):
        profile = _profile_from_card(node, page_url, school)
        if not profile or not profile.name:
            continue
        key = (profile.name.casefold(), profile.source_url)
        if key in seen:
            continue
        seen.add(key)
        profiles.append(profile)
    return profiles


def _profiles_from_fd_content_json(soup: BeautifulSoup, page_url: str, school: str) -> list[PersonProfile]:
    profiles: list[PersonProfile] = []
    for script in soup.select("script.fd-content-json"):
        try:
            items = json.loads(script.get_text())
        except json.JSONDecodeError:
            continue
        for item in items:
            template = unescape(str(item.get("template", "")))
            card = BeautifulSoup(template, "html.parser")
            profile = _profile_from_card(card, page_url, school)
            if not profile and item.get("name"):
                profile = _profile_from_fd_item(item, page_url, school)
            if profile:
                profiles.append(profile)
    return profiles


def _profile_from_fd_item(item: dict, page_url: str, school: str) -> PersonProfile | None:
    name = clean_text(str(item.get("name", "")))
    if not name or GENERIC_NAME_RE.search(name):
        return None
    template = unescape(str(item.get("template", "")))
    card = BeautifulSoup(template, "html.parser")
    anchor = card.find("a", href=True)
    source_url = canonicalize_url(urljoin(page_url, anchor["href"]) if anchor else page_url)
    title = ""
    search = clean_text(str(item.get("search", "")))
    title_match = TITLE_RE.search(search)
    if title_match:
        title = clean_text(title_match.group(0))
    return PersonProfile(
        name=name,
        school=school,
        department=clean_text(str(item.get("departmentCode", ""))),
        title=title,
        email="",
        source_url=source_url,
        personal_homepage="",
        research_interests="",
        biography="",
        publications="",
        photo_url="",
        photo_path="",
        education="",
        advisor="",
        source_text=search[:10000],
        extraction_method="html_rule",
        confidence_score=0.33 if title else 0.22,
    )


def is_probable_person_profile(profile: PersonProfile) -> bool:
    if not profile.name or GENERIC_NAME_RE.search(profile.name):
        return False
    if profile.confidence_score >= 0.45 and (profile.title or profile.email or profile.research_interests or profile.biography):
        return True
    path = urlparse(profile.source_url).path
    return bool(re.search(r"/(people|faculty|profile|profiles)/[^/]+/?$", path, re.I) and profile.confidence_score >= 0.35)


def should_trigger_llm(html: str, profile: PersonProfile, parser_confidence_threshold: float = 0.65) -> tuple[bool, str]:
    useful = [
        profile.name,
        profile.title,
        profile.email,
        profile.school,
        profile.department,
        profile.research_interests,
        profile.biography,
        profile.education,
        profile.advisor,
        profile.photo_url,
    ]
    useful_count = sum(1 for value in useful if value)
    text = profile.source_text
    if useful_count < 3 and (profile.name or TITLE_RE.search(text) or EMAIL_RE.search(text)):
        return True, "likely_profile_with_fewer_than_3_useful_fields"
    if LLM_LABEL_RE.search(text) and not (profile.research_interests or profile.biography or profile.education or profile.publications):
        return True, "target_labels_present_but_sections_not_isolated"
    if _script_heavy(html):
        return True, "script_or_json_heavy_page"
    if profile.confidence_score < parser_confidence_threshold and (profile.name or profile.email or profile.title):
        return True, "low_html_parser_confidence"
    return False, "html_parser_sufficient_or_not_profile_like"


def _best_name(soup: BeautifulSoup) -> str:
    for selector in (".profile-name", ".fic-name", ".name", "[class*=name]", "main h1", "article h1", "h1", "h2"):
        found = soup.select_one(selector)
        if not found:
            continue
        if "sr-only" in found.get("class", []):
            continue
        text = clean_text(found.get_text(" ", strip=True))
        if 2 <= len(text) <= 80 and not GENERIC_NAME_RE.search(text):
            return text.title() if text.islower() or text.isupper() else text
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    title = re.split(r"[\-|–|—|,|/]", title)[0].strip()
    return title if 2 <= len(title) <= 80 and not GENERIC_NAME_RE.search(title) else ""


def _profile_from_card(node, page_url: str, school: str) -> PersonProfile | None:
    text = clean_text(node.get_text(" ", strip=True))
    if len(text) < 8 or len(text) > 2500:
        return None
    email = _email_from_card(node, text)
    title_match = TITLE_RE.search(text)
    anchor = _best_profile_anchor(node)
    name = _name_from_card(node, anchor, text)
    if not name or GENERIC_NAME_RE.search(name):
        return None
    if not (title_match or email or anchor):
        return None
    source_url = canonicalize_url(urljoin(page_url, anchor["href"]) if anchor and anchor.get("href") else page_url)
    photo_url = _photo_url_from_soup(BeautifulSoup(str(node), "html.parser"), page_url, name)
    profile = PersonProfile(
        name=name,
        school=school,
        department=_card_department(text),
        title=clean_text(title_match.group(0)) if title_match else "",
        email=email,
        source_url=source_url,
        personal_homepage="",
        research_interests=_section_after_label(text, r"Research Interests?|Research Areas?|Areas of Expertise"),
        biography="",
        publications="",
        photo_url=photo_url,
        photo_path="",
        education=_section_after_label(text, r"Education|Educational Background|Degrees?"),
        advisor=_section_after_label(text, r"Advisor|Advisors?|Supervisor|Supervisors?"),
        source_text=text[:10000],
        extraction_method="html_rule",
        confidence_score=0.0,
    )
    useful = [profile.name, profile.title, profile.email, profile.school, profile.department, profile.research_interests, profile.education, profile.advisor, profile.photo_url]
    return PersonProfile(**dict(profile.__dict__, confidence_score=round(sum(1 for value in useful if value) / len(useful), 2)))


def _best_profile_anchor(node):
    anchors = []
    for anchor in node.find_all("a", href=True):
        text = clean_text(anchor.get_text(" ", strip=True))
        href = anchor.get("href", "")
        if text and 2 <= len(text) <= 80 and not GENERIC_NAME_RE.search(text):
            score = 1
            if re.search(r"profile|people|faculty|person|bio", href, re.I):
                score += 2
            anchors.append((score, anchor))
    if not anchors:
        return None
    anchors.sort(key=lambda item: item[0], reverse=True)
    return anchors[0][1]


def _email_from_card(node, text: str) -> str:
    for anchor in node.select("[data-user][data-domain]"):
        user = clean_text(anchor.get("data-user", ""))
        domain = clean_text(anchor.get("data-domain", ""))
        if user and domain:
            candidate = f"{user}@{domain}"
            if EMAIL_RE.fullmatch(candidate):
                return candidate
    for anchor in node.find_all("a", href=True):
        href = anchor.get("href", "")
        if href.lower().startswith("mailto:"):
            match = EMAIL_RE.search(href)
            if match:
                return match.group(0)
    match = EMAIL_RE.search(text)
    return match.group(0) if match else ""


def _name_from_card(node, anchor, text: str) -> str:
    if anchor:
        anchor_text = clean_text(anchor.get_text(" ", strip=True))
        if 2 <= len(anchor_text) <= 80 and not GENERIC_NAME_RE.search(anchor_text):
            return anchor_text.title() if anchor_text.islower() or anchor_text.isupper() else anchor_text
    for selector in ("h2", "h3", "h4", ".name", "[class*=name]"):
        found = node.select_one(selector)
        if found:
            candidate = clean_text(found.get_text(" ", strip=True))
            if 2 <= len(candidate) <= 80 and not GENERIC_NAME_RE.search(candidate):
                return candidate.title() if candidate.islower() or candidate.isupper() else candidate
    first = re.split(r"\s{2,}|\||,", text, maxsplit=1)[0].strip()
    return first if 2 <= len(first) <= 80 and not GENERIC_NAME_RE.search(first) else ""


def _card_department(text: str) -> str:
    match = re.search(r"(Department of [A-Z][A-Za-z &,-]+|School of [A-Z][A-Za-z &,-]+|College of [A-Z][A-Za-z &,-]+)", text)
    return clean_text(match.group(1))[:250] if match else ""


def _email_from_soup(soup: BeautifulSoup, source_text: str) -> str:
    for anchor in soup.select("[data-user][data-domain]"):
        user = clean_text(anchor.get("data-user", ""))
        domain = clean_text(anchor.get("data-domain", ""))
        if user and domain:
            candidate = f"{user}@{domain}"
            if EMAIL_RE.fullmatch(candidate):
                return candidate
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if href.lower().startswith("mailto:"):
            match = EMAIL_RE.search(href)
            if match:
                return match.group(0)
    match = EMAIL_RE.search(source_text)
    return match.group(0) if match else ""


def _title_near_name(soup: BeautifulSoup, name: str, source_text: str) -> str:
    for selector in (".job-title", "[class*=job-title]", "[class*=position]", "[class*=title]"):
        found = soup.select_one(selector)
        if found:
            text = clean_text(found.get_text(" ", strip=True))
            if TITLE_RE.search(text):
                return text[:200]
    match = TITLE_RE.search(source_text)
    return clean_text(match.group(0)) if match else ""


def _department_from_soup(soup: BeautifulSoup, source_text: str) -> str:
    affiliation = _label_value_from_dom(soup, ("TC Affiliations", "Affiliations?", "Affiliation"))
    if affiliation:
        return affiliation[:250]
    for selector in ("[class*=department]", "[class*=division]", "[class*=program]", "[class*=school]", "[class*=college]", ".affiliation"):
        found = soup.select_one(selector)
        if found:
            text = clean_text(found.get_text(" ", strip=True))
            if text and len(text) <= 250:
                return re.sub(r"^Affiliation\s+", "", text, flags=re.I)
    return _section_after_label(source_text, r"Affiliation|Department", stop_pattern=r"(Education|Research|Publications|Biography|Contact|Email)")[:250]


def _label_value_from_dom(soup: BeautifulSoup, labels: tuple[str, ...]) -> str:
    label_re = re.compile(r"^(?:" + "|".join(labels) + r")\s*:?\s*", re.I)
    for node in soup.find_all(["h2", "h3", "h4", "strong", "b", "dt"]):
        label = clean_text(node.get_text(" ", strip=True))
        if not re.fullmatch(r"(?:" + "|".join(labels) + r")\s*:?", label, re.I):
            continue
        parent = node.parent
        if not parent:
            continue
        parent_text = clean_text(parent.get_text(" ", strip=True))
        value = label_re.sub("", parent_text).strip(" :")
        if value and value != label:
            return clean_text(value[:1200])
    return ""


def _section_from_dom(soup: BeautifulSoup, labels: tuple[str, ...]) -> str:
    for label_pattern in labels:
        section = _section_from_dom_label(soup, label_pattern)
        if section:
            return section
    return ""


def _section_from_dom_label(soup: BeautifulSoup, label_pattern: str) -> str:
    label_re = re.compile(label_pattern, re.I)
    for node in soup.find_all(["h2", "h3", "h4", "strong", "b", "dt"]):
        label = clean_text(node.get_text(" ", strip=True))
        if not label_re.search(label):
            continue
        parts = _section_parts_from_siblings(node)
        if not parts and node.parent and node.parent.name == "a":
            parts = _section_parts_from_siblings(node.parent)
        if parts:
            return clean_text(" ".join(parts)[:1200])
    return ""


def _section_parts_from_siblings(node) -> list[str]:
    parts = []
    for sibling in node.find_next_siblings():
        sibling_label = clean_text(sibling.get_text(" ", strip=True))
        if sibling.name in {"h2", "h3", "h4", "dt"} and STOP_SECTION_RE.search(sibling_label):
            break
        if sibling_label:
            parts.append(sibling_label)
        if len(" ".join(parts)) >= 1200:
            break
    return parts


def _section_after_label(
    text: str,
    label_pattern: str,
    stop_pattern: str = r"(Education|Teaching|Publications|Selected Publications|Biography|Biographical Information|"
    r"Research|Research Interests|Scholarly Interests|Faculty Expertise|Contact|Email)",
) -> str:
    match = re.search(r"(?:" + label_pattern + r")\s*:?\s*(.+)", text, flags=re.I)
    if not match:
        return ""
    value = match.group(1)
    stop = re.search(stop_pattern, value, flags=re.I)
    if stop:
        value = value[: stop.start()]
    return clean_text(value[:1200])


def _research_sentence_from_text(source_text: str) -> str:
    match = re.search(
        r"((?:His|Her|Their|[A-Z][A-Za-z.-]+(?:\s+[A-Z][A-Za-z.-]+){0,3})\s+research\s+"
        r"(?:examines|focuses on|centers on|explores|addresses)\s+.+?)(?:\.\s|$)",
        source_text,
        flags=re.I,
    )
    return clean_text(match.group(1))[:1200] if match else ""


def _image_src(node) -> str:
    for attr in ("src", "data-src", "data-original", "data-lazy-src"):
        value = node.get(attr)
        if value:
            return value.strip()
    srcset = node.get("srcset") or node.get("data-srcset")
    if srcset:
        return srcset.split(",", 1)[0].strip().split(" ", 1)[0].strip()
    return ""


def _photo_url_from_soup(soup: BeautifulSoup, profile_url: str, name: str) -> str:
    candidates = []
    for selector in ("img[class*=profile]", "img[class*=portrait]", "img[class*=headshot]", "img[class*=person]", "main img", "article img"):
        for image in soup.select(selector):
            src = _image_src(image)
            if not src:
                continue
            alt = clean_text(image.get("alt", ""))
            combined = f"{src} {alt} {' '.join(image.get('class', []))}"
            if re.search(r"(logo|icon|sprite|seal|shield|wordmark|placeholder|banner)", combined, re.I):
                continue
            score = 1
            if name and name.split()[0].lower() in alt.lower():
                score += 2
            if re.search(r"(profile|portrait|headshot|person|faculty)", combined, re.I):
                score += 2
            candidates.append((score, canonicalize_url(urljoin(profile_url, src))))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _personal_homepage_from_soup(soup: BeautifulSoup, profile_url: str) -> str:
    for anchor in soup.find_all("a", href=True):
        text = anchor.get_text(" ", strip=True).lower()
        if "website" in text or "homepage" in text or "personal" in text:
            return canonicalize_url(urljoin(profile_url, anchor["href"]))
    return ""


def _script_heavy(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    visible_text = clean_text(soup.get_text(" ", strip=True))
    script_text = " ".join(script.get_text(" ", strip=True) for script in soup.find_all("script"))
    return len(script_text) > 5000 and len(visible_text) < 1000
