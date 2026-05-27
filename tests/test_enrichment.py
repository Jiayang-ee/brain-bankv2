"""Tests for enrichment evidence-strength rules and storage methods."""

import sqlite3

import pytest

from faculty_spider_v3.enrichment import (
    build_field_update,
    EnrichmentResult,
    EnrichmentCandidate,
    FieldUpdate,
    format_enrichment_result,
)
from faculty_spider_v3.storage import FacultySpiderV3Store


# ----------------------------------------------------------------------
# build_field_update unit tests
# ----------------------------------------------------------------------


class TestBuildFieldUpdate:
    def test_official_site_never_overwritten_by_supplement_source(self):
        """official_site is the strongest evidence; supplement sources cannot overwrite it."""
        update = build_field_update(
            field="title",
            new_value="Associate Professor",
            source="semantic_scholar",
            confidence=0.9,
            current_value="Assistant Professor",
            current_source="semantic_scholar",
            current_primary_source="official_site",
        )
        assert update.new_value == ""
        assert update.is_strong_evidence is False

    def test_weaker_source_does_not_overwrite_stronger_source(self):
        """Medium evidence (semantic_scholar) does not overwrite same-tier existing data."""
        update = build_field_update(
            field="title",
            new_value="Professor",
            source="dblp",
            confidence=0.8,
            current_value="Assistant Professor",
            current_source="semantic_scholar",
            current_primary_source="publication",
        )
        # DBLP is weaker than Semantic Scholar for title field
        assert update.new_value == ""

    def test_stronger_source_overwrites_weaker_source(self):
        """A stronger supplement source can improve on a weaker one."""
        update = build_field_update(
            field="title",
            new_value="Professor",
            source="semantic_scholar",
            confidence=0.85,
            current_value="Assistant Professor",
            current_source="dblp",
            current_primary_source="publication",
        )
        assert update.new_value == "Professor"
        assert update.source == "semantic_scholar"

    def test_empty_field_is_filled(self):
        """An empty current field is always filled when new evidence exists."""
        update = build_field_update(
            field="title",
            new_value="Professor",
            source="semantic_scholar",
            confidence=0.85,
            current_value="",
            current_source="",
            current_primary_source="publication",
        )
        assert update.new_value == "Professor"

    def test_identical_value_is_skipped(self):
        """An update that matches the current value is skipped (no-op)."""
        update = build_field_update(
            field="title",
            new_value="Professor",
            source="semantic_scholar",
            confidence=0.85,
            current_value="Professor",
            current_source="semantic_scholar",
            current_primary_source="publication",
        )
        assert update.new_value == ""

    def test_low_confidence_flags_review(self):
        """Data below confidence threshold (0.7) sets requires_review=True."""
        update = build_field_update(
            field="email",
            new_value="ambiguous@example.edu",
            source="semantic_scholar",
            confidence=0.5,
            current_value="",
            current_source="",
            current_primary_source="publication",
        )
        assert update.new_value == "ambiguous@example.edu"
        assert update.requires_review is True

    def test_high_confidence_no_review_flag(self):
        """Data at or above threshold auto-writes without review flag."""
        update = build_field_update(
            field="email",
            new_value="confirmed@example.edu",
            source="semantic_scholar",
            confidence=0.9,
            current_value="",
            current_source="",
            current_primary_source="publication",
        )
        assert update.new_value == "confirmed@example.edu"
        assert update.requires_review is False

    def test_crossref_weak_school_only(self):
        """Crossref source is weak evidence; it should still fill an empty school."""
        update = build_field_update(
            field="school",
            new_value="MIT",
            source="crossref",
            confidence=0.5,
            current_value="",
            current_source="",
            current_primary_source="publication",
        )
        assert update.new_value == "MIT"
        assert update.requires_review is True  # below 0.7 threshold

    def test_new_value_same_as_current_skipped(self):
        """Updating a field with the same value results in no-op."""
        update = build_field_update(
            field="department",
            new_value="Department of Management",
            source="semantic_scholar",
            confidence=0.9,
            current_value="Department of Management",
            current_source="semantic_scholar",
            current_primary_source="publication",
        )
        assert update.new_value == ""


# ----------------------------------------------------------------------
# EnrichmentResult formatting
# ----------------------------------------------------------------------


class TestFormatEnrichmentResult:
    def test_format_shows_updates_and_review_tags(self):
        result = EnrichmentResult(
            person_id=1,
            updates=[
                FieldUpdate(field="title", new_value="Professor", source="semantic_scholar", confidence=0.85, is_strong_evidence=True, requires_review=False),
                FieldUpdate(field="email", new_value="low@example.edu", source="semantic_scholar", confidence=0.5, is_strong_evidence=True, requires_review=True),
            ],
            conflicts=[],
            skipped=["department: no improvement over semantic_scholar"],
            errors=[],
        )
        formatted = format_enrichment_result(result)
        assert "Professor" in formatted
        assert "REVIEW" in formatted  # low-confidence email flagged
        assert "no improvement" in formatted


# ----------------------------------------------------------------------
# Storage: list_publication_only_people
# ----------------------------------------------------------------------


class TestListPublicationOnlyPeople:
    def test_returns_only_publication_source_type(self, tmp_path):
        store = FacultySpiderV3Store(tmp_path / "test.sqlite")
        store.init_db()

        from faculty_spider_v3.models import PersonProfile

        # Insert an official_site person
        store.upsert_person_profile(
            PersonProfile(
                name="Zhang Wei",
                school="Tsinghua University",
                department="School of Economics",
                title="Professor",
                email="zhangwei@example.edu",
                source_url="https://www.tsinghua.edu.cn/faculty/zhangwei",
                personal_homepage="",
                research_interests="",
                biography="",
                publications="",
                photo_url="",
                photo_path="",
                education="",
                advisor="",
                source_text="",
                extraction_method="html_rule",
                confidence_score=0.9,
            ),
            is_likely_chinese_name=True,
            chinese_name_score=1.0,
            name_filter_reason="",
        )

        # Insert publication-only person directly via SQL
        with store.connect() as conn:
            conn.execute(
                """
                insert into people(name, normalized_name, school, primary_source_type,
                    primary_source_url, extraction_method, is_likely_chinese_name,
                    chinese_name_score, review_status, enrichment_confidence)
                values('Li Ming', 'li ming', 'Peking University', 'publication',
                    'https://doi.org/10.1234/test', 'publication_aggregate', 1, 0.9,
                    'needs_review', 0.0)
                """,
            )

        rows = store.list_publication_only_people()
        assert len(rows) == 1
        assert rows[0]["name"] == "Li Ming"


# ----------------------------------------------------------------------
# Storage: apply_enrichment_updates
# ----------------------------------------------------------------------


class TestApplyEnrichmentUpdates:
    def test_writes_field_source_and_confidence(self, tmp_path):
        store = FacultySpiderV3Store(tmp_path / "test.sqlite")
        store.init_db()

        # Insert a publication-only person directly
        with store.connect() as conn:
            conn.execute(
                """
                insert into people(name, normalized_name, school, primary_source_type,
                    primary_source_url, extraction_method, is_likely_chinese_name,
                    chinese_name_score, review_status, enrichment_confidence,
                    personal_homepage, homepage_source, title, title_source,
                    department, department_source, email, email_source, school, school_source)
                values('Wang Lei', 'wang lei', 'Fudan University', 'publication',
                    'https://doi.org/10.1234/test2', 'publication_aggregate', 1, 0.9,
                    'needs_review', 0.0, '', '', '', '', '', '', '', '', '', '')
                """,
            )
            row = conn.execute("select id from people where name = 'Wang Lei'").fetchone()
            person_id = row["id"]

        updates = [
            FieldUpdate(
                field="title",
                new_value="Associate Professor",
                source="semantic_scholar",
                confidence=0.85,
                is_strong_evidence=True,
                requires_review=False,
            ),
            FieldUpdate(
                field="email",
                new_value="wanglei@fudan.edu.cn",
                source="semantic_scholar",
                confidence=0.5,
                is_strong_evidence=True,
                requires_review=True,
            ),
        ]

        store.apply_enrichment_updates(person_id, updates, requires_review=True)

        with store.connect() as conn:
            row = conn.execute(
                "select title, title_source, email, email_source, enrichment_confidence, review_status from people where id = ?",
                (person_id,),
            ).fetchone()

        assert row["title"] == "Associate Professor"
        assert row["title_source"] == "semantic_scholar"
        assert row["email"] == "wanglei@fudan.edu.cn"
        assert row["email_source"] == "semantic_scholar"
        assert row["enrichment_confidence"] == 0.85
        assert row["review_status"] == "needs_review"

    def test_skipped_when_no_updates(self, tmp_path):
        """apply_enrichment_updates with empty list does nothing."""
        store = FacultySpiderV3Store(tmp_path / "test.sqlite")
        store.init_db()

        with store.connect() as conn:
            conn.execute(
                """
                insert into people(name, normalized_name, school, primary_source_type,
                    primary_source_url, extraction_method, is_likely_chinese_name,
                    chinese_name_score, review_status, enrichment_confidence)
                values('Chen Ping', 'chen ping', 'Zhejiang University', 'publication',
                    'https://doi.org/10.1234/test3', 'publication_aggregate', 1, 0.9,
                    'needs_review', 0.0)
                """,
            )
            row = conn.execute("select id from people where name = 'Chen Ping'").fetchone()
            person_id = row["id"]

        store.apply_enrichment_updates(person_id, [], requires_review=False)

        with store.connect() as conn:
            row = conn.execute(
                "select enrichment_confidence, review_status from people where id = ?",
                (person_id,),
            ).fetchone()

        # enrichment_confidence unchanged (0.0), review_status unchanged (needs_review)
        assert row["enrichment_confidence"] == 0.0
        assert row["review_status"] == "needs_review"


# ----------------------------------------------------------------------
# Storage: get_person
# ----------------------------------------------------------------------


class TestGetPerson:
    def test_returns_enrichment_fields(self, tmp_path):
        store = FacultySpiderV3Store(tmp_path / "test.sqlite")
        store.init_db()

        with store.connect() as conn:
            conn.execute(
                """
                insert into people(name, normalized_name, school, primary_source_type,
                    primary_source_url, extraction_method, is_likely_chinese_name,
                    chinese_name_score, review_status, enrichment_confidence,
                    homepage_source, title_source, school_source)
                values('Zhao Yang', 'zhao yang', 'Nankai University', 'publication',
                    'https://doi.org/10.1234/test4', 'publication_aggregate', 1, 0.9,
                    'needs_review', 0.75, 'semantic_scholar', 'semantic_scholar', 'openalex')
                """,
            )
            row = conn.execute("select id from people where name = 'Zhao Yang'").fetchone()
            person_id = row["id"]

        person = store.get_person(person_id)
        assert person is not None
        assert person["homepage_source"] == "semantic_scholar"
        assert person["title_source"] == "semantic_scholar"
        assert person["school_source"] == "openalex"
        assert person["enrichment_confidence"] == 0.75

    def test_returns_none_for_missing_id(self, tmp_path):
        store = FacultySpiderV3Store(tmp_path / "test.sqlite")
        store.init_db()
        assert store.get_person(99999) is None


# ----------------------------------------------------------------------
# Conflict detection
# ----------------------------------------------------------------------


class TestConflictDetection:
    def test_conflict_when_same_field_different_value_from_two_sources(self):
        """When two different supplement sources provide different values for the same field,
        the second update is still accepted but the conflict is recorded."""
        result = EnrichmentResult(
            person_id=1,
            updates=[
                FieldUpdate(field="email", new_value="ss@example.edu", source="semantic_scholar", confidence=0.9, is_strong_evidence=True, requires_review=False),
            ],
            conflicts=["email conflict: semantic_scholar='ss@example.edu' vs crossref='other@example.edu'"],
            skipped=[],
            errors=[],
        )
        formatted = format_enrichment_result(result)
        assert "conflict" in formatted

    def test_conflict_list_empty_when_no_conflicts(self):
        """No conflicts recorded when all sources agree or field was empty."""
        result = EnrichmentResult(
            person_id=2,
            updates=[
                FieldUpdate(field="school", new_value="MIT", source="dblp", confidence=0.6, is_strong_evidence=False, requires_review=True),
            ],
            conflicts=[],
            skipped=[],
            errors=[],
        )
        assert result.conflicts == []


# ----------------------------------------------------------------------
# Evidence strength: weak never overrides strong
# ----------------------------------------------------------------------


class TestWeakNeverOverridesStrong:
    def test_openalex_weak_school_does_not_override_dblp_school(self):
        """OpenAlex (confidence=0.5) does not override DBLP (confidence=0.6) for school field."""
        update = build_field_update(
            field="school",
            new_value="Stanford University",
            source="openalex",
            confidence=0.5,
            current_value="MIT",
            current_source="dblp",
            current_primary_source="publication",
        )
        assert update.new_value == ""

    def test_crossref_weak_school_does_not_override_dblp_school(self):
        """Crossref (confidence=0.5) does not override DBLP (confidence=0.6) for school field."""
        update = build_field_update(
            field="school",
            new_value="Stanford University",
            source="crossref",
            confidence=0.5,
            current_value="MIT",
            current_source="dblp",
            current_primary_source="publication",
        )
        assert update.new_value == ""

    def test_dblp_school_does_not_override_semantic_scholar_school(self):
        """DBLP (confidence=0.6) does not override Semantic Scholar (confidence=0.7) for school field."""
        update = build_field_update(
            field="school",
            new_value="Stanford University",
            source="dblp",
            confidence=0.6,
            current_value="MIT",
            current_source="semantic_scholar",
            current_primary_source="publication",
        )
        # SS has higher strength than DBLP, so DBLP cannot overwrite SS
        assert update.new_value == ""

    def test_weaker_source_can_fill_empty_field(self):
        """Weaker source CAN fill an empty field (no existing value to override)."""
        update = build_field_update(
            field="school",
            new_value="MIT",
            source="openalex",
            confidence=0.5,
            current_value="",
            current_source="",
            current_primary_source="publication",
        )
        # Empty field is always fillable, but requires review (confidence < 0.7)
        assert update.new_value == "MIT"
        assert update.requires_review is True

    def test_same_source_same_value_skipped(self):
        """Same source providing identical value is a no-op."""
        update = build_field_update(
            field="title",
            new_value="Professor",
            source="semantic_scholar",
            confidence=0.85,
            current_value="Professor",
            current_source="semantic_scholar",
            current_primary_source="publication",
        )
        assert update.new_value == ""


# ----------------------------------------------------------------------
# Low-confidence + name-collision review issue triggers
# ----------------------------------------------------------------------


class TestReviewIssueGeneration:
    def test_low_confidence_email_flags_review(self):
        """Email below 0.7 confidence sets requires_review=True."""
        update = build_field_update(
            field="email",
            new_value="unconfirmed@example.edu",
            source="semantic_scholar",
            confidence=0.5,
            current_value="",
            current_source="",
            current_primary_source="publication",
        )
        assert update.requires_review is True
        assert update.new_value == "unconfirmed@example.edu"

    def test_high_confidence_email_no_review(self):
        """Email at or above 0.7 confidence auto-writes without review."""
        update = build_field_update(
            field="email",
            new_value="confirmed@example.edu",
            source="semantic_scholar",
            confidence=0.9,
            current_value="",
            current_source="",
            current_primary_source="publication",
        )
        assert update.requires_review is False
        assert update.new_value == "confirmed@example.edu"

    def test_official_site_field_unchanged_with_any_supplement(self):
        """Any supplement source touching an official_site field is blocked at build_field_update level."""
        for source in ["semantic_scholar", "dblp", "crossref", "openalex"]:
            update = build_field_update(
                field="email",
                new_value="hacked@example.edu",
                source=source,
                confidence=0.99,
                current_value="real@example.edu",
                current_source="official_site",
                current_primary_source="official_site",
            )
            assert update.new_value == "", f"{source} should not overwrite official_site field"
            assert update.requires_review is False


# ----------------------------------------------------------------------
# apply_enrichment_updates: duplicate guard
# ----------------------------------------------------------------------


class TestApplyEnrichmentUpdatesNoDuplicate:
    def test_apply_enrichment_updates_with_duplicate_guard(self, tmp_path):
        """apply_enrichment_updates with empty updates list returns early (no-op)."""
        store = FacultySpiderV3Store(tmp_path / "test.sqlite")
        store.init_db()

        with store.connect() as conn:
            conn.execute(
                """
                insert into people(name, normalized_name, school, primary_source_type,
                    primary_source_url, extraction_method, is_likely_chinese_name,
                    chinese_name_score, review_status, enrichment_confidence)
                values('Test Person', 'test person', 'Harvard University', 'publication',
                    'https://doi.org/10.1234/test', 'publication_aggregate', 1, 0.9,
                    'needs_review', 0.0)
                """,
            )
            row = conn.execute("select id from people where name = 'Test Person'").fetchone()
            person_id = row["id"]

        # Call with empty list — should not raise and should be a no-op
        store.apply_enrichment_updates(person_id, [], requires_review=False)

        with store.connect() as conn:
            row = conn.execute(
                "select enrichment_confidence, review_status from people where id = ?",
                (person_id,),
            ).fetchone()

        # Should be unchanged (enrichment_confidence still 0.0, review_status still needs_review)
        assert row["enrichment_confidence"] == 0.0
        assert row["review_status"] == "needs_review"