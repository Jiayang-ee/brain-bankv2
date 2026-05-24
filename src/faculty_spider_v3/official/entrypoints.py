from __future__ import annotations

import csv
from pathlib import Path

from faculty_spider_v3.models import SchoolEntrypoint

ENTRYPOINT_FIELDNAMES = [
    "school",
    "unit",
    "entry_url",
    "entry_type",
    "url_pattern",
    "pagination_pattern",
    "person_link_selector",
    "api_endpoint",
    "roles_included",
    "notes",
    "status",
]


def read_school_entrypoints(path: str | Path) -> list[SchoolEntrypoint]:
    entrypoints: list[SchoolEntrypoint] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            entry_url = (row.get("entry_url") or "").strip()
            school = (row.get("school") or "").strip()
            if not school or not entry_url:
                continue
            entrypoints.append(
                SchoolEntrypoint(
                    school=school,
                    unit=(row.get("unit") or "").strip(),
                    entry_url=entry_url,
                    entry_type=(row.get("entry_type") or "").strip(),
                    url_pattern=(row.get("url_pattern") or "").strip(),
                    pagination_pattern=(row.get("pagination_pattern") or "").strip(),
                    person_link_selector=(row.get("person_link_selector") or "").strip(),
                    api_endpoint=(row.get("api_endpoint") or "").strip(),
                    roles_included=(row.get("roles_included") or "").strip(),
                    notes=(row.get("notes") or "").strip(),
                    status=(row.get("status") or "").strip() or "new",
                )
            )
    return entrypoints


def write_school_entrypoints_csv(entrypoints: list[SchoolEntrypoint], path: str | Path) -> int:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=ENTRYPOINT_FIELDNAMES)
        writer.writeheader()
        for entrypoint in entrypoints:
            writer.writerow({field: getattr(entrypoint, field) for field in ENTRYPOINT_FIELDNAMES})
    return len(entrypoints)
