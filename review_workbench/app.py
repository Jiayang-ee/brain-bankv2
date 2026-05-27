"""Flask review workbench for Wave 1 faculty candidate review."""

from __future__ import annotations

import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.utils import secure_filename

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max upload

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
QUEUE_CSV = REPO_ROOT / "data" / "review" / "wave1_review_queue.csv"
QUALITY_CSV = REPO_ROOT / "data" / "review" / "wave1_quality_gap_report.csv"
ISSUES_CSV = REPO_ROOT / "data" / "review" / "issues.csv"
EXPORTS_PEOPLE_CSV = REPO_ROOT / "data" / "exports" / "people.csv"
RUN_RECORD_JSON = REPO_ROOT / "data" / "review" / "wave1_run_record.json"

# Review decision enumeration (backend contract: accepted, rejected, needs_review, or empty; approved is aliased to accepted by import_review_decisions)
VALID_DECISIONS = ["accepted", "rejected", "needs_review", ""]

# Fields we allow reviewers to edit
EDITABLE_FIELDS = ["review_decision", "review_decision_note", "resolved_issue_types"]

# All columns in the queue CSV (must match WAVE1_REVIEW_FIELDS in report.py)
QUEUE_FIELDS = [
    "priority_score", "priority_tier", "person_id", "name", "school",
    "department", "title", "email", "personal_homepage",
    "primary_source_type", "confidence_score", "review_status",
    "discipline_score", "discipline_is_relevant", "discipline_review_status",
    "pub_last_5_year_total", "pub_a_plus_total", "pub_a_total",
    "pub_a1_total", "pub_a2_total", "pub_top_total",
    "pub_first_author_total", "pub_corresponding_author_total",
    "pub_journals", "pub_years", "source_url", "paper_links",
    "open_issue_types", "open_issue_messages", "open_issue_source_urls",
    "gap_missing_school", "gap_missing_homepage", "gap_missing_email",
    "gap_low_confidence", "gap_name_conflict", "gap_discipline_uncertain",
    "gap_high_output_no_affiliation",
    "review_decision", "review_decision_note", "resolved_issue_types",
    "created_at", "updated_at",
]


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _load_queue() -> list[dict]:
    """Load review queue rows from CSV, sorted by priority_score desc."""
    if not QUEUE_CSV.exists():
        return []
    with QUEUE_CSV.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    # Sort by priority_score descending (handle empty strings)
    def score(row):
        try:
            return float(row.get("priority_score", 0) or 0)
        except (ValueError, TypeError):
            return 0
    rows.sort(key=score, reverse=True)
    return rows


def _load_quality_gaps() -> list[dict]:
    """Load quality gap report rows."""
    if not QUALITY_CSV.exists():
        return []
    with QUALITY_CSV.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _load_issues() -> list[dict]:
    """Load open issues."""
    if not ISSUES_CSV.exists():
        return []
    with ISSUES_CSV.open(encoding="utf-8-sig", newline="") as f:
        return [row for row in csv.DictReader(f) if row.get("status") == "open"]


def _save_queue(rows: list[dict]) -> None:
    """Write review queue back to CSV, preserving field order."""
    QUEUE_CSV.parent.mkdir(parents=True, exist_ok=True)
    with QUEUE_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=QUEUE_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _regenerate_quality_gap() -> list[dict]:
    """Re-run the quality gap report CLI and reload results."""
    try:
        result = subprocess.run(
            [
                "python3", "-m", "faculty_spider_v3.cli",
                "review", "wave1-report",
                "--run-id", f"workbench-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}",
            ],
            cwd=str(REPO_ROOT / "src"),
            capture_output=True,
            text=True,
            timeout=60,
            env={**__import__("os").environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"wave1-report failed (exit {result.returncode}): {result.stderr[:500]}"
            )
    except Exception:
        raise
    return _load_quality_gap_report_from_csv()


def _load_quality_gap_report_from_csv() -> list[dict]:
    """Parse quality gap CSV into summary dicts per category."""
    return _load_quality_gaps()


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------

def _compute_stats(rows: list[dict]) -> dict:
    """Compute dashboard statistics from queue rows."""
    total = len(rows)
    by_decision = {}
    by_gap = {
        "missing_school": 0,
        "missing_homepage_email": 0,
        "low_confidence": 0,
        "name_conflict": 0,
        "discipline_uncertain": 0,
        "source_errors": 0,
        "undecided": 0,
        "needs_review": 0,
    }

    for r in rows:
        d = (r.get("review_decision") or "").strip().lower()
        if d in ("accepted", "approved", "approved/accepted"):
            by_decision["accepted"] = by_decision.get("accepted", 0) + 1
        elif d == "rejected":
            by_decision["rejected"] = by_decision.get("rejected", 0) + 1
        elif d == "needs_review":
            by_decision["needs_review"] = by_decision.get("needs_review", 0) + 1
            by_gap["needs_review"] += 1
        else:
            by_decision["未决策"] = by_decision.get("未决策", 0) + 1
            by_gap["undecided"] += 1

        if r.get("gap_missing_school") == "1":
            by_gap["missing_school"] += 1
        if r.get("gap_missing_homepage") == "1" or r.get("gap_missing_email") == "1":
            by_gap["missing_homepage_email"] += 1
        if r.get("gap_low_confidence") == "1":
            by_gap["low_confidence"] += 1
        if r.get("gap_name_conflict") == "1":
            by_gap["name_conflict"] += 1
        if r.get("gap_discipline_uncertain") == "1":
            by_gap["discipline_uncertain"] += 1
        if r.get("gap_high_output_no_affiliation") == "1":
            by_gap["source_errors"] += 1

    return {
        "total": total,
        "by_decision": by_decision,
        "by_gap": by_gap,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Quality dashboard + review queue entry."""
    rows = _load_queue()
    quality_gaps = _load_quality_gaps()
    stats = _compute_stats(rows)
    issues = _load_issues()

    # Decision distribution for chart
    decisions = list(stats["by_decision"].items())

    return render_template(
        "index.html",
        stats=stats,
        decisions=decisions,
        quality_gaps=quality_gaps,
        issues=issues[:50],  # limit for display
    )


@app.route("/queue")
def list_queue():
    """Full review queue with filters and sort."""
    rows = _load_queue()

    # Apply filters
    filter_decision = request.args.get("decision", "")
    filter_gap = request.args.get("gap", "")
    filter_tier = request.args.get("tier", "")
    search = request.args.get("search", "").strip()
    sort_by = request.args.get("sort", "priority_score")
    sort_dir = request.args.get("dir", "desc")

    if filter_decision:
        if filter_decision == "undecided":
            rows = [r for r in rows if not (r.get("review_decision") or "").strip()]
        elif filter_decision == "needs_review":
            rows = [r for r in rows if (r.get("review_decision") or "").strip().lower() == "needs_review"]
        elif filter_decision == "accepted":
            rows = [r for r in rows if (r.get("review_decision") or "").strip().lower() in ("accepted", "approved", "approved/accepted")]
        elif filter_decision == "rejected":
            rows = [r for r in rows if (r.get("review_decision") or "").strip().lower() == "rejected"]

    if filter_gap:
        if filter_gap == "missing_homepage_email":
            rows = [r for r in rows if r.get("gap_missing_homepage") == "1" or r.get("gap_missing_email") == "1"]
        else:
            rows = [r for r in rows if r.get(f"gap_{filter_gap}") == "1"]

    if filter_tier:
        rows = [r for r in rows if (r.get("priority_tier") or "").lower() == filter_tier.lower()]

    if search:
        term = search.casefold()
        rows = [
            r for r in rows
            if term in (r.get("name") or "").casefold()
            or term in (r.get("school") or "").casefold()
            or term in (r.get("title") or "").casefold()
            or term in (r.get("email") or "").casefold()
        ]

    # Sort (numeric fields sorted as numbers)
    reverse = sort_dir == "desc"
    numeric_fields = {"priority_score", "confidence_score", "discipline_score",
                      "pub_last_5_year_total", "pub_a_plus_total", "pub_a_total",
                      "pub_a1_total", "pub_a2_total", "pub_top_total",
                      "pub_first_author_total", "pub_corresponding_author_total"}
    if sort_by in QUEUE_FIELDS:
        def sort_key(r):
            val = r.get(sort_by) or ""
            if sort_by in numeric_fields:
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return 0
            return val
        rows.sort(key=sort_key, reverse=reverse)

    total = len(_load_queue())
    filtered = len(rows)

    return render_template(
        "queue.html",
        rows=rows,
        total=total,
        filtered=filtered,
        filter_decision=filter_decision,
        filter_gap=filter_gap,
        filter_tier=filter_tier,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@app.route("/record/<int:person_id>")
def record_view(person_id: int):
    """View a single candidate record."""
    rows = _load_queue()
    record = next((r for r in rows if int(r.get("person_id", 0)) == person_id), None)
    if not record:
        abort(404)

    # Load open issues for this person
    issues = [r for r in _load_issues() if int(r.get("person_id") or 0) == person_id]

    # Load quality gaps
    quality_gaps = _load_quality_gaps()

    return render_template(
        "record.html",
        record=record,
        issues=issues,
        quality_gaps=quality_gaps,
    )


@app.route("/record/<int:person_id>/edit", methods=["GET", "POST"])
def record_edit(person_id: int):
    """Edit decision and notes for a single candidate."""
    rows = _load_queue()
    record = next((r for r in rows if int(r.get("person_id", 0)) == person_id), None)
    if not record:
        abort(404)

    if request.method == "POST":
        decision = (request.form.get("review_decision") or "").strip()
        note = (request.form.get("review_decision_note") or "").strip()
        resolved = (request.form.get("resolved_issue_types") or "").strip()

        # Validate decision enum (backend contract: accepted/rejected/needs_review/empty; approved aliased to accepted on import)
        if decision and decision not in ["accepted", "rejected", "needs_review"]:
            return jsonify({"error": f"非法决策值: {decision}"}), 400

        # Update the record in memory
        record["review_decision"] = decision
        record["review_decision_note"] = note
        record["resolved_issue_types"] = resolved

        # Save back to CSV
        # Find and replace the row in the full list
        full_rows = _load_queue()
        for i, r in enumerate(full_rows):
            if int(r.get("person_id", 0)) == person_id:
                for field in EDITABLE_FIELDS:
                    full_rows[i][field] = record.get(field, "")
                break

        _save_queue(full_rows)

        return redirect(url_for("record_view", person_id=person_id))

    issues = [r for r in _load_issues() if int(r.get("person_id") or 0) == person_id]
    return render_template(
        "edit.html",
        record=record,
        issues=issues,
    )


@app.route("/save", methods=["POST"])
def save_queue():
    """Save the full queue CSV (bulk operations come through here)."""
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file provided"}), 400

    try:
        # Parse uploaded CSV
        import io
        stream = file.stream.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(stream))
        rows = list(reader)

        # Validate required columns
        if "person_id" not in (reader.fieldnames or []) or "review_decision" not in (reader.fieldnames or []):
            return jsonify({"error": "CSV缺少必需列: person_id, review_decision"}), 400

        # Merge editable fields into existing queue rows
        existing = {int(r["person_id"]): r for r in _load_queue()}
        merged = []
        for row in rows:
            pid = int(row["person_id"])
            if pid in existing:
                for field in EDITABLE_FIELDS:
                    existing[pid][field] = row.get(field, "")
                merged.append(existing[pid])
            else:
                merged.append(row)

        _save_queue(merged)
        return jsonify({"success": True, "updated": len(rows)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/export")
def export_csv():
    """Export current queue as CSV for download."""
    rows = _load_queue()
    import io
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=QUEUE_FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue(), 200, {
        "Content-Type": "text/csv; charset=utf-8-sig",
        "Content-Disposition": f"attachment; filename=wave1_review_queue_{datetime.now(timezone.utc):%Y%m%d}.csv",
    }


@app.route("/refresh", methods=["POST"])
def refresh_stats():
    """Re-run quality gap generation and return updated stats."""
    try:
        quality_gaps = _regenerate_quality_gap()
        rows = _load_queue()
        stats = _compute_stats(rows)
        return jsonify({"success": True, "stats": stats, "quality_gaps": quality_gaps})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)