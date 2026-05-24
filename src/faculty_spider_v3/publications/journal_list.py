from __future__ import annotations

import csv
from pathlib import Path

from faculty_spider_v3.models import Journal


JOURNAL_FIELD_MAP = {
    "来源文件": "source_file",
    "期刊体系": "journal_system",
    "学科/方向": "discipline",
    "期刊名称": "journal_name",
    "ISSN/CN": "issn_cn",
    "学校级别": "achievement_level",
    "人才库用途": "talent_pool_use",
    "备注": "notes",
}


def read_journals_csv(path: str | Path) -> list[Journal]:
    journals: list[Journal] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            values = {target: _clean(row.get(source, "")) for source, target in JOURNAL_FIELD_MAP.items()}
            if not values["journal_name"]:
                continue
            journals.append(Journal(**values))
    return journals


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()
