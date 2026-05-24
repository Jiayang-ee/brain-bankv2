from __future__ import annotations

import re
from dataclasses import dataclass


COMMON_SURNAMES = {
    "wang",
    "li",
    "zhang",
    "liu",
    "chen",
    "yang",
    "huang",
    "zhao",
    "wu",
    "zhou",
    "xu",
    "sun",
    "ma",
    "zhu",
    "hu",
    "guo",
    "he",
    "gao",
    "lin",
    "luo",
    "zheng",
    "liang",
    "xie",
    "song",
    "tang",
    "deng",
    "han",
    "feng",
    "cao",
    "peng",
    "cai",
    "yuan",
    "pan",
    "du",
    "jiang",
    "xiao",
    "cheng",
    "shen",
    "yu",
    "lu",
    "wei",
    "ye",
    "fang",
    "ren",
    "qian",
}

COMPOUND_SURNAMES = {
    "ouyang",
    "sima",
    "zhuge",
    "shangguan",
    "situ",
    "huangfu",
}

NON_PERSON_TERMS = {
    "faculty",
    "people",
    "directory",
    "department",
    "school",
    "college",
    "center",
    "centre",
    "institute",
    "research",
}

CHINESE_CONTEXT_RE = re.compile(
    r"china|chinese|tsinghua|peking|fudan|zhejiang|shanghai jiao tong|nanjing|ustc|"
    r"中国|清华|北大|复旦|浙江大学|上海交通|南京大学|中国科学技术大学",
    re.I,
)


@dataclass(frozen=True)
class NameScore:
    name: str
    score: float
    is_likely_chinese_name: bool
    reason: str


def score_chinese_name(name: str, context: str = "", accept_threshold: float = 0.70) -> NameScore:
    cleaned = " ".join(name.strip().split())
    if not cleaned:
        return NameScore(name=name, score=0.0, is_likely_chinese_name=False, reason="empty_name")
    if _has_chinese_char(cleaned):
        return NameScore(name=cleaned, score=0.98, is_likely_chinese_name=True, reason="contains_chinese_character")

    tokens = _name_tokens(cleaned)
    if not tokens or any(token in NON_PERSON_TERMS for token in tokens):
        return NameScore(name=cleaned, score=0.05, is_likely_chinese_name=False, reason="non_person_or_empty_tokens")

    score = 0.0
    reasons: list[str] = []

    if _has_chinese_surname(tokens):
        score += 0.45
        reasons.append("chinese_surname")
    if _has_pinyin_given_name_shape(tokens):
        score += 0.2
        reasons.append("pinyin_given_name_shape")
    if _has_initial_plus_pinyin(tokens):
        score += 0.1
        reasons.append("initial_plus_pinyin")
    if CHINESE_CONTEXT_RE.search(context):
        score += 0.15
        reasons.append("chinese_context")
    if 2 <= len(tokens) <= 4:
        score += 0.05
        reasons.append("person_name_length")

    score = min(score, 0.95)
    reason = ",".join(reasons) if reasons else "weak_or_no_chinese_name_signal"
    return NameScore(name=cleaned, score=round(score, 2), is_likely_chinese_name=score >= accept_threshold, reason=reason)


def _has_chinese_char(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)


def _name_tokens(value: str) -> list[str]:
    normalized = re.sub(r"[^A-Za-z.\-\s]", " ", value)
    return [token.strip(".-").casefold() for token in normalized.split() if token.strip(".-")]


def _has_chinese_surname(tokens: list[str]) -> bool:
    if not tokens:
        return False
    first = tokens[0].replace("-", "")
    last = tokens[-1].replace("-", "")
    return first in COMMON_SURNAMES or last in COMMON_SURNAMES or first in COMPOUND_SURNAMES or last in COMPOUND_SURNAMES


def _has_pinyin_given_name_shape(tokens: list[str]) -> bool:
    if len(tokens) < 2:
        return False
    for token in tokens:
        compact = token.replace("-", "")
        if 2 <= len(compact) <= 12 and re.fullmatch(r"[a-z]+", compact) and _vowel_count(compact) >= 1:
            if compact not in COMMON_SURNAMES and compact not in COMPOUND_SURNAMES:
                return True
    return False


def _has_initial_plus_pinyin(tokens: list[str]) -> bool:
    return any(len(token) == 1 and token.isalpha() for token in tokens) and _has_chinese_surname(tokens)


def _vowel_count(value: str) -> int:
    return sum(1 for char in value if char in "aeiou")
