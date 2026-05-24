from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Iterable


ISSUE_FIELDS = [
    "id",
    "person_id",
    "related_table",
    "related_id",
    "issue_type",
    "severity",
    "message",
    "source_url",
    "status",
    "created_at",
    "resolved_at",
]


def export_review_issues_csv(rows: Iterable[sqlite3.Row], path: str | Path) -> int:
    materialized = list(rows)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ISSUE_FIELDS)
        writer.writeheader()
        for row in materialized:
            writer.writerow({field: row[field] for field in ISSUE_FIELDS})
    return len(materialized)
