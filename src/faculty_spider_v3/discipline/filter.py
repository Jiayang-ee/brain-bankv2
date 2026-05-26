from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class DisciplineScore:
    score: float
    is_relevant: bool
    review_status: str
    matched_disciplines: list[str]
    matched_keywords: list[str]
    negative_keywords: list[str]
    reason: str


DISCIPLINE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "management_science": (
        "management science",
        "operations research",
        "operations management",
        "decision science",
        "decision analytics",
        "optimization",
        "stochastic",
        "queueing",
        "supply chain",
        "logistics",
        "运筹",
        "管理科学",
        "决策",
        "优化",
        "供应链",
    ),
    "information_systems": (
        "information systems",
        "information system",
        "digital platform",
        "platform economy",
        "e-commerce",
        "business analytics",
        "data analytics",
        "analytics",
        "machine learning",
        "artificial intelligence",
        "信息系统",
        "平台",
        "商务分析",
        "数据分析",
        "人工智能",
    ),
    "business_management": (
        "business school",
        "school of business",
        "management",
        "strategy",
        "marketing",
        "organization",
        "organizational behavior",
        "innovation",
        "entrepreneurship",
        "管理",
        "商学院",
        "战略",
        "营销",
        "创新",
        "创业",
    ),
    "quantitative_finance_economics": (
        "finance",
        "financial economics",
        "fintech",
        "risk management",
        "economics",
        "econometrics",
        "market design",
        "金融",
        "金融科技",
        "风险管理",
        "经济学",
        "计量经济",
    ),
    "industrial_systems_engineering": (
        "industrial engineering",
        "systems engineering",
        "engineering management",
        "data science",
        "statistics",
        "statistical learning",
        "computational social science",
        "工业工程",
        "系统工程",
        "工程管理",
        "数据科学",
        "统计",
    ),
}

STRONG_UNIT_KEYWORDS = (
    "business school",
    "school of business",
    "management science",
    "operations research",
    "operations management",
    "information systems",
    "industrial engineering",
    "systems engineering",
    "engineering management",
    "商学院",
    "管理科学",
    "运筹",
    "信息系统",
    "工业工程",
    "系统工程",
)

NEGATIVE_KEYWORDS = (
    "medicine",
    "medical school",
    "biology",
    "chemistry",
    "physics",
    "literature",
    "history",
    "music",
    "law school",
    "clinical psychology",
    "tesol",
    "linguistics",
    "医学",
    "生物",
    "化学",
    "物理",
    "文学",
    "历史",
    "音乐",
    "法学院",
    "临床心理",
    "语言学",
)


def score_discipline_relevance(
    *,
    department: str = "",
    title: str = "",
    field: str = "",
    research_direction: str = "",
    research_interests: str = "",
    biography: str = "",
    publications: str = "",
    source_url: str = "",
    journal_names: list[str] | None = None,
    accept_threshold: float = 0.75,
    review_threshold: float = 0.45,
) -> DisciplineScore:
    weighted_texts = [
        (department, 0.35),
        (field, 0.3),
        (research_direction, 0.3),
        (research_interests, 0.3),
        (publications, 0.25),
        (" ".join(journal_names or []), 0.25),
        (biography, 0.15),
        (title, 0.08),
        (source_url, 0.08),
    ]
    matched_disciplines: set[str] = set()
    matched_keywords: set[str] = set()
    score = 0.0

    for text, weight in weighted_texts:
        normalized = _normalize(text)
        if not normalized:
            continue
        for discipline, keywords in DISCIPLINE_KEYWORDS.items():
            hits = _matched_keywords(normalized, keywords)
            if hits:
                matched_disciplines.add(discipline)
                matched_keywords.update(hits)
                score += weight * min(1.0, 0.55 + 0.15 * len(hits))
        strong_hits = _matched_keywords(normalized, STRONG_UNIT_KEYWORDS)
        if strong_hits:
            matched_keywords.update(strong_hits)
            score += min(0.2, 0.08 * len(strong_hits))

    negative_hits = sorted(_matched_keywords(_normalize(" ".join(text for text, _ in weighted_texts)), NEGATIVE_KEYWORDS))
    if len(matched_disciplines) >= 2:
        score += 0.1
    if matched_keywords and score < review_threshold:
        score = review_threshold
    if negative_hits and not matched_disciplines:
        score -= 0.25
    elif negative_hits:
        score -= 0.08

    score = round(max(0.0, min(1.0, score)), 2)
    if score >= accept_threshold:
        review_status = "accepted"
    elif score >= review_threshold:
        review_status = "needs_review"
    else:
        review_status = "rejected"

    reason_parts = []
    if matched_disciplines:
        reason_parts.append("matched_disciplines=" + ",".join(sorted(matched_disciplines)))
    if matched_keywords:
        reason_parts.append("matched_keywords=" + ",".join(sorted(matched_keywords)[:12]))
    if negative_hits:
        reason_parts.append("negative_keywords=" + ",".join(negative_hits))
    if not reason_parts:
        reason_parts.append("no_management_science_signal")

    return DisciplineScore(
        score=score,
        is_relevant=score >= accept_threshold,
        review_status=review_status,
        matched_disciplines=sorted(matched_disciplines),
        matched_keywords=sorted(matched_keywords),
        negative_keywords=negative_hits,
        reason="; ".join(reason_parts),
    )


def score_paper_discipline_relevance(
    *,
    title: str = "",
    abstract: str = "",
    keywords: str = "",
    accept_threshold: float = 0.6,
    review_threshold: float = 0.35,
) -> DisciplineScore:
    """
    Score a paper for discipline relevance based on its title, abstract, and keywords.
    Used for filtering papers from broad-impact journals (Nature, Science, PNAS, PAMI, JMLR, etc.)
    where the journal itself is not a reliable indicator of relevance.

    Args:
        title: Paper title
        abstract: Paper abstract
        keywords: Paper keywords (may be comma-separated or space-separated)
        accept_threshold: Score above this threshold is accepted without review
        review_threshold: Score above this threshold needs human review

    Returns:
        DisciplineScore with score, matched disciplines/keywords, and reason
    """
    # Build a combined text for keyword matching
    combined_text = " ".join(filter(None, [title, abstract, keywords]))
    if not combined_text:
        return DisciplineScore(
            score=0.0,
            is_relevant=False,
            review_status="rejected",
            matched_disciplines=[],
            matched_keywords=[],
            negative_keywords=[],
            reason="no_management_science_signal",
        )

    # Check for negative keywords first (strong rejection signals)
    normalized_combined = _normalize(combined_text)
    negative_hits = sorted(_matched_keywords(normalized_combined, NEGATIVE_KEYWORDS))

    matched_disciplines: set[str] = set()
    matched_keywords: set[str] = set()
    score = 0.0

    for discipline, discipline_keywords in DISCIPLINE_KEYWORDS.items():
        hits = _matched_keywords(normalized_combined, discipline_keywords)
        if hits:
            matched_disciplines.add(discipline)
            matched_keywords.update(hits)
            # Paper scoring uses slightly different weights - title/abstract matter more
            if discipline_keywords == DISCIPLINE_KEYWORDS["management_science"]:
                score += 0.40 * min(1.0, 0.55 + 0.15 * len(hits))
            elif discipline_keywords == DISCIPLINE_KEYWORDS["information_systems"]:
                score += 0.35 * min(1.0, 0.55 + 0.15 * len(hits))
            elif discipline_keywords == DISCIPLINE_KEYWORDS["business_management"]:
                score += 0.30 * min(1.0, 0.55 + 0.15 * len(hits))
            elif discipline_keywords == DISCIPLINE_KEYWORDS["quantitative_finance_economics"]:
                score += 0.30 * min(1.0, 0.55 + 0.15 * len(hits))
            elif discipline_keywords == DISCIPLINE_KEYWORDS["industrial_systems_engineering"]:
                score += 0.35 * min(1.0, 0.55 + 0.15 * len(hits))

    # Apply negative keyword penalty
    if negative_hits and not matched_disciplines:
        score -= 0.35
    elif negative_hits:
        score -= 0.15

    # Require at least one positive keyword match for non-zero score
    if not matched_keywords and score > 0:
        score = 0.0

    score = round(max(0.0, min(1.0, score)), 2)

    if score >= accept_threshold:
        review_status = "accepted"
    elif score >= review_threshold:
        review_status = "needs_review"
    else:
        review_status = "rejected"

    reason_parts = []
    if matched_disciplines:
        reason_parts.append("matched_disciplines=" + ",".join(sorted(matched_disciplines)))
    if matched_keywords:
        reason_parts.append("matched_keywords=" + ",".join(sorted(matched_keywords)[:12]))
    if negative_hits:
        reason_parts.append("negative_keywords=" + ",".join(negative_hits))
    if not reason_parts:
        reason_parts.append("no_management_science_signal")

    return DisciplineScore(
        score=score,
        is_relevant=score >= accept_threshold,
        review_status=review_status,
        matched_disciplines=sorted(matched_disciplines),
        matched_keywords=sorted(matched_keywords),
        negative_keywords=negative_hits,
        reason="; ".join(reason_parts),
    )


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def _matched_keywords(text: str, keywords: tuple[str, ...]) -> set[str]:
    hits: set[str] = set()
    for keyword in keywords:
        normalized_keyword = keyword.casefold()
        if _contains_keyword(text, normalized_keyword):
            hits.add(keyword)
    return hits


def _contains_keyword(text: str, keyword: str) -> bool:
    if re.search(r"[\u4e00-\u9fff]", keyword):
        return keyword in text
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])", text))
