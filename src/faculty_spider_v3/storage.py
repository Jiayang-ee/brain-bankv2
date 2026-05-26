from __future__ import annotations

import sqlite3
import json
from pathlib import Path
from typing import Iterable

from .models import Journal, LinkCandidate, PageFetch, PaperRecord, PersonProfile, SchoolEntrypoint, SchoolSeed
from .urls import canonicalize_url


class FacultySpiderV3Store:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.create_function("normalize_text_for_join", 1, normalize_text)
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                create table if not exists sources (
                    id integer primary key autoincrement,
                    source_type text not null,
                    name text not null,
                    base_url text default '',
                    config_json text default '{}',
                    enabled integer default 1,
                    created_at text default current_timestamp,
                    updated_at text default current_timestamp,
                    unique(source_type, name)
                );

                create table if not exists school_seeds (
                    id integer primary key autoincrement,
                    rank integer,
                    school_name_en text not null unique,
                    school_name_zh text default '',
                    homepage_url text default '',
                    difficulty_level integer,
                    crawl_status text default '',
                    notes text default '',
                    created_at text default current_timestamp,
                    updated_at text default current_timestamp
                );

                create table if not exists school_entrypoints (
                    id integer primary key autoincrement,
                    school text not null,
                    unit text default '',
                    entry_url text not null unique,
                    entry_type text default '',
                    url_pattern text default '',
                    pagination_pattern text default '',
                    person_link_selector text default '',
                    api_endpoint text default '',
                    roles_included text default '',
                    notes text default '',
                    status text default 'new',
                    created_at text default current_timestamp,
                    updated_at text default current_timestamp
                );

                create table if not exists journals (
                    id integer primary key autoincrement,
                    source_file text default '',
                    journal_system text default '',
                    discipline text default '',
                    journal_name text not null,
                    normalized_journal_name text not null,
                    issn_cn text default '',
                    achievement_level text default '',
                    talent_pool_use text default '',
                    notes text default '',
                    created_at text default current_timestamp,
                    updated_at text default current_timestamp,
                    unique(normalized_journal_name, issn_cn)
                );

                create table if not exists pages (
                    id integer primary key autoincrement,
                    source_id integer,
                    url text not null unique,
                    source_url text default '',
                    school text default '',
                    department text default '',
                    page_type text default '',
                    status_code integer,
                    content_hash text default '',
                    raw_html_path text default '',
                    fetched_at text,
                    fetch_error text default '',
                    parser_status text default '',
                    llm_status text default '',
                    created_at text default current_timestamp,
                    updated_at text default current_timestamp
                );

                create table if not exists papers (
                    id integer primary key autoincrement,
                    title text not null,
                    normalized_title text not null,
                    journal text default '',
                    year integer,
                    doi text default '',
                    url text default '',
                    abstract text default '',
                    authors_json text default '[]',
                    first_author_name text default '',
                    corresponding_author_names_json text default '[]',
                    affiliations_json text default '[]',
                    source text default '',
                    paper_url text default '',
                    source_api_url text default '',
                    created_at text default current_timestamp,
                    updated_at text default current_timestamp,
                    unique(normalized_title, year, journal)
                );

                create table if not exists people (
                    id integer primary key autoincrement,
                    name text not null,
                    normalized_name text not null,
                    email text default '',
                    school text default '',
                    department text default '',
                    field text default '',
                    research_direction text default '',
                    title text default '',
                    career_stage text default '',
                    age integer,
                    birth_year integer,
                    photo_url text default '',
                    photo_path text default '',
                    education text default '',
                    advisor text default '',
                    personal_homepage text default '',
                    research_interests text default '',
                    biography text default '',
                    publications_json text default '[]',
                    publication_stats_json text default '{}',
                    paper_links_json text default '[]',
                    primary_source_type text default '',
                    primary_source_url text default '',
                    extraction_method text default '',
                    is_likely_chinese_name integer default 0,
                    chinese_name_score real default 0,
                    name_filter_reason text default '',
                    discipline_score real default 0,
                    discipline_is_relevant integer default 0,
                    discipline_review_status text default '',
                    discipline_matched_disciplines_json text default '[]',
                    discipline_matched_keywords_json text default '[]',
                    discipline_negative_keywords_json text default '[]',
                    discipline_reason text default '',
                    confidence_score real default 0,
                    review_status text default 'new',
                    created_at text default current_timestamp,
                    updated_at text default current_timestamp
                );
                create unique index if not exists idx_people_identity
                    on people(normalized_name, school, primary_source_url);

                create table if not exists person_papers (
                    id integer primary key autoincrement,
                    person_id integer not null,
                    paper_id integer not null,
                    author_role text default '',
                    achievement_level text default '',
                    paper_url text default '',
                    doi text default '',
                    year integer,
                    journal text default '',
                    created_at text default current_timestamp,
                    unique(person_id, paper_id, author_role)
                );

                create table if not exists publication_stats (
                    person_id integer primary key,
                    last_5_year_total integer default 0,
                    first_author_total integer default 0,
                    corresponding_author_total integer default 0,
                    top_total integer default 0,
                    a_plus_total integer default 0,
                    a_total integer default 0,
                    a1_total integer default 0,
                    a2_total integer default 0,
                    level_counts_json text default '{}',
                    updated_at text default current_timestamp
                );

                create table if not exists candidate_links (
                    id integer primary key autoincrement,
                    source_id integer,
                    url text not null unique,
                    source_url text default '',
                    school text default '',
                    department text default '',
                    anchor_text text default '',
                    page_type text default '',
                    confidence_score real default 0,
                    status text default 'queued',
                    created_at text default current_timestamp,
                    updated_at text default current_timestamp
                );

                create table if not exists review_issues (
                    id integer primary key autoincrement,
                    person_id integer,
                    related_table text default '',
                    related_id integer,
                    issue_type text not null,
                    severity text default 'medium',
                    message text default '',
                    source_url text default '',
                    status text default 'open',
                    created_at text default current_timestamp,
                    resolved_at text
                );

                create table if not exists publication_runs (
                    id integer primary key autoincrement,
                    run_name text not null,
                    journal_group text not null,
                    from_year integer not null,
                    works_per_journal integer not null,
                    sources text not null,
                    status text default 'created',
                    started_at text,
                    finished_at text,
                    created_at text default current_timestamp,
                    updated_at text default current_timestamp
                );

                create table if not exists publication_run_items (
                    id integer primary key autoincrement,
                    run_id integer not null,
                    journal_id integer not null,
                    journal_name text not null,
                    status text default 'pending',
                    cursor text default '',
                    page integer default 0,
                    attempts integer default 0,
                    papers_seen integer default 0,
                    papers_saved integer default 0,
                    last_error text default '',
                    started_at text,
                    finished_at text,
                    created_at text default current_timestamp,
                    updated_at text default current_timestamp,
                    unique(run_id, journal_id)
                );
                """
            )
            self._add_column_if_missing(conn, "candidate_links", "school", "text default ''")
            self._add_column_if_missing(conn, "candidate_links", "department", "text default ''")
            self._add_column_if_missing(conn, "people", "discipline_score", "real default 0")
            self._add_column_if_missing(conn, "people", "discipline_is_relevant", "integer default 0")
            self._add_column_if_missing(conn, "people", "discipline_review_status", "text default ''")
            self._add_column_if_missing(conn, "people", "discipline_matched_disciplines_json", "text default '[]'")
            self._add_column_if_missing(conn, "people", "discipline_matched_keywords_json", "text default '[]'")
            self._add_column_if_missing(conn, "people", "discipline_negative_keywords_json", "text default '[]'")
            self._add_column_if_missing(conn, "people", "discipline_reason", "text default ''")
            # P5: enrichment source tracking fields
            self._add_column_if_missing(conn, "people", "homepage_source", "text default ''")
            self._add_column_if_missing(conn, "people", "title_source", "text default ''")
            self._add_column_if_missing(conn, "people", "department_source", "text default ''")
            self._add_column_if_missing(conn, "people", "email_source", "text default ''")
            self._add_column_if_missing(conn, "people", "school_source", "text default ''")
            self._add_column_if_missing(conn, "people", "enrichment_confidence", "real default 0.0")

    @staticmethod
    def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        existing = {row["name"] for row in conn.execute(f"pragma table_info({table})")}
        if column not in existing:
            conn.execute(f"alter table {table} add column {column} {definition}")

    def upsert_source(self, source_type: str, name: str, base_url: str = "", config_json: str = "{}") -> int:
        with self.connect() as conn:
            conn.execute(
                """
                insert into sources(source_type, name, base_url, config_json)
                values(?, ?, ?, ?)
                on conflict(source_type, name) do update set
                    base_url=excluded.base_url,
                    config_json=excluded.config_json,
                    updated_at=current_timestamp
                """,
                (source_type, name, base_url, config_json),
            )
            row = conn.execute("select id from sources where source_type = ? and name = ?", (source_type, name)).fetchone()
            return int(row["id"])

    def upsert_school_seeds(self, schools: Iterable[SchoolSeed]) -> int:
        rows = list(schools)
        with self.connect() as conn:
            conn.executemany(
                """
                insert into school_seeds(rank, school_name_en, school_name_zh, homepage_url, difficulty_level, crawl_status, notes)
                values(:rank, :school_name_en, :school_name_zh, :homepage_url, :difficulty_level, :crawl_status, :notes)
                on conflict(school_name_en) do update set
                    rank=excluded.rank,
                    school_name_zh=excluded.school_name_zh,
                    homepage_url=excluded.homepage_url,
                    difficulty_level=excluded.difficulty_level,
                    crawl_status=excluded.crawl_status,
                    notes=excluded.notes,
                    updated_at=current_timestamp
                """,
                [school.__dict__ for school in rows],
            )
        return len(rows)

    def upsert_school_entrypoints(self, entrypoints: Iterable[SchoolEntrypoint]) -> int:
        rows = list(entrypoints)
        with self.connect() as conn:
            conn.executemany(
                """
                insert into school_entrypoints(school, unit, entry_url, entry_type, url_pattern,
                    pagination_pattern, person_link_selector, api_endpoint, roles_included, notes, status)
                values(:school, :unit, :entry_url, :entry_type, :url_pattern,
                    :pagination_pattern, :person_link_selector, :api_endpoint, :roles_included, :notes, :status)
                on conflict(entry_url) do update set
                    school=excluded.school,
                    unit=excluded.unit,
                    entry_type=excluded.entry_type,
                    url_pattern=excluded.url_pattern,
                    pagination_pattern=excluded.pagination_pattern,
                    person_link_selector=excluded.person_link_selector,
                    api_endpoint=excluded.api_endpoint,
                    roles_included=excluded.roles_included,
                    notes=excluded.notes,
                    status=excluded.status,
                    updated_at=current_timestamp
                """,
                [entrypoint.__dict__ for entrypoint in rows],
            )
        return len(rows)

    def list_school_entrypoints(
        self,
        limit: int | None = None,
        school_names: list[str] | None = None,
        statuses: list[str] | None = None,
    ) -> list[sqlite3.Row]:
        query = "select * from school_entrypoints where entry_url != ''"
        params: list[object] = []
        if school_names:
            placeholders = ",".join("?" for _ in school_names)
            query += f" and school in ({placeholders})"
            params.extend(school_names)
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            query += f" and status in ({placeholders})"
            params.extend(statuses)
        query += " order by school, unit, id"
        if limit is not None:
            query += " limit ?"
            params.append(limit)
        with self.connect() as conn:
            return list(conn.execute(query, params))

    def upsert_journals(self, journals: Iterable[Journal]) -> int:
        rows = [dict(journal.__dict__, normalized_journal_name=normalize_text(journal.journal_name)) for journal in journals]
        with self.connect() as conn:
            conn.executemany(
                """
                insert into journals(source_file, journal_system, discipline, journal_name, normalized_journal_name,
                    issn_cn, achievement_level, talent_pool_use, notes)
                values(:source_file, :journal_system, :discipline, :journal_name, :normalized_journal_name,
                    :issn_cn, :achievement_level, :talent_pool_use, :notes)
                on conflict(normalized_journal_name, issn_cn) do update set
                    source_file=excluded.source_file,
                    journal_system=excluded.journal_system,
                    discipline=excluded.discipline,
                    journal_name=excluded.journal_name,
                    achievement_level=excluded.achievement_level,
                    talent_pool_use=excluded.talent_pool_use,
                    notes=excluded.notes,
                    updated_at=current_timestamp
                """,
                rows,
            )
        return len(rows)

    def list_journals(self, limit: int | None = None, journal_names: list[str] | None = None) -> list[sqlite3.Row]:
        query = "select * from journals"
        params: list[object] = []
        if journal_names:
            placeholders = ",".join("?" for _ in journal_names)
            query += f" where journal_name in ({placeholders})"
            params.extend(journal_names)
        query += " order by case when achievement_level like '%TOP%' then 0 when achievement_level like 'A+%' then 1 when achievement_level like 'A%' then 2 else 3 end, journal_name"
        if limit is not None:
            query += " limit ?"
            params.append(limit)
        with self.connect() as conn:
            return list(conn.execute(query, params))

    def get_journal(self, journal_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("select * from journals where id = ?", (journal_id,)).fetchone()

    def create_publication_run(
        self,
        run_name: str,
        journal_group: str,
        from_year: int,
        works_per_journal: int,
        sources: str,
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                insert into publication_runs(run_name, journal_group, from_year, works_per_journal, sources)
                values(?, ?, ?, ?, ?)
                """,
                (run_name, journal_group, from_year, works_per_journal, sources),
            )
            return int(cursor.lastrowid)

    def add_publication_run_items(self, run_id: int, journals: Iterable[sqlite3.Row]) -> int:
        rows = [(run_id, int(journal["id"]), str(journal["journal_name"])) for journal in journals]
        with self.connect() as conn:
            conn.executemany(
                """
                insert or ignore into publication_run_items(run_id, journal_id, journal_name)
                values(?, ?, ?)
                """,
                rows,
            )
            return int(conn.total_changes)

    def get_publication_run(self, run_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("select * from publication_runs where id = ?", (run_id,)).fetchone()

    def latest_resumable_publication_run(
        self,
        journal_group: str,
        from_year: int,
        works_per_journal: int,
        sources: str,
    ) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                """
                select * from publication_runs
                where journal_group = ?
                  and from_year = ?
                  and works_per_journal = ?
                  and sources = ?
                  and status in ('created', 'running', 'partial', 'failed')
                order by id desc
                limit 1
                """,
                (journal_group, from_year, works_per_journal, sources),
            ).fetchone()

    def update_publication_run_status(self, run_id: int, status: str, started: bool = False, finished: bool = False) -> None:
        assignments = ["status = ?", "updated_at = current_timestamp"]
        params: list[object] = [status]
        if started:
            assignments.append("started_at = coalesce(started_at, current_timestamp)")
        if finished:
            assignments.append("finished_at = current_timestamp")
        params.append(run_id)
        with self.connect() as conn:
            conn.execute(f"update publication_runs set {', '.join(assignments)} where id = ?", params)

    def publication_run_items(self, run_id: int, include_completed: bool = True) -> list[sqlite3.Row]:
        query = "select * from publication_run_items where run_id = ?"
        params: list[object] = [run_id]
        if not include_completed:
            query += " and status != 'completed'"
        query += " order by id"
        with self.connect() as conn:
            return list(conn.execute(query, params))

    def publication_run_item_counts(self, run_id: int) -> dict[str, int]:
        with self.connect() as conn:
            rows = conn.execute(
                "select status, count(*) as total from publication_run_items where run_id = ? group by status",
                (run_id,),
            ).fetchall()
        return {str(row["status"]): int(row["total"]) for row in rows}

    def start_publication_run_item(self, item_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                update publication_run_items
                set status = 'running',
                    attempts = attempts + 1,
                    started_at = coalesce(started_at, current_timestamp),
                    updated_at = current_timestamp
                where id = ?
                """,
                (item_id,),
            )

    def finish_publication_run_item(self, item_id: int, status: str, papers_seen: int, papers_saved: int, last_error: str = "") -> None:
        with self.connect() as conn:
            conn.execute(
                """
                update publication_run_items
                set status = ?,
                    papers_seen = papers_seen + ?,
                    papers_saved = papers_saved + ?,
                    last_error = ?,
                    finished_at = current_timestamp,
                    updated_at = current_timestamp
                where id = ?
                """,
                (status, papers_seen, papers_saved, last_error, item_id),
            )

    def upsert_papers(self, papers: Iterable[PaperRecord]) -> int:
        rows = []
        for paper in papers:
            rows.append(
                {
                    "title": paper.title,
                    "normalized_title": normalize_text(paper.title),
                    "journal": paper.journal,
                    "year": paper.year,
                    "doi": normalize_doi(paper.doi),
                    "url": canonicalize_url(paper.url),
                    "abstract": paper.abstract,
                    "authors_json": json.dumps(list(paper.authors), ensure_ascii=False),
                    "first_author_name": paper.first_author_name,
                    "corresponding_author_names_json": json.dumps(list(paper.corresponding_author_names), ensure_ascii=False),
                    "affiliations_json": json.dumps(list(paper.affiliations), ensure_ascii=False),
                    "source": paper.source,
                    "paper_url": canonicalize_url(paper.paper_url),
                    "source_api_url": canonicalize_url(paper.source_api_url),
                }
            )
        with self.connect() as conn:
            conn.executemany(
                """
                insert into papers(title, normalized_title, journal, year, doi, url, abstract, authors_json,
                    first_author_name, corresponding_author_names_json, affiliations_json, source, paper_url, source_api_url)
                values(:title, :normalized_title, :journal, :year, :doi, :url, :abstract, :authors_json,
                    :first_author_name, :corresponding_author_names_json, :affiliations_json, :source, :paper_url, :source_api_url)
                on conflict(normalized_title, year, journal) do update set
                    title=excluded.title,
                    doi=coalesce(nullif(excluded.doi, ''), papers.doi),
                    url=coalesce(nullif(excluded.url, ''), papers.url),
                    abstract=coalesce(nullif(excluded.abstract, ''), papers.abstract),
                    authors_json=case when excluded.authors_json != '[]' then excluded.authors_json else papers.authors_json end,
                    first_author_name=coalesce(nullif(excluded.first_author_name, ''), papers.first_author_name),
                    corresponding_author_names_json=case when excluded.corresponding_author_names_json != '[]' then excluded.corresponding_author_names_json else papers.corresponding_author_names_json end,
                    affiliations_json=case when excluded.affiliations_json != '[]' then excluded.affiliations_json else papers.affiliations_json end,
                    source=case when instr(papers.source, excluded.source) = 0 then trim(papers.source || ',' || excluded.source, ',') else papers.source end,
                    paper_url=coalesce(nullif(excluded.paper_url, ''), papers.paper_url),
                    source_api_url=coalesce(nullif(excluded.source_api_url, ''), papers.source_api_url),
                    updated_at=current_timestamp
                """,
                rows,
            )
        return len(rows)

    def paper_rows(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    """
                    select p.id, p.title, p.journal, p.year, p.doi, p.url, p.paper_url, p.source,
                        p.source_api_url, p.first_author_name, p.corresponding_author_names_json,
                        p.authors_json, p.affiliations_json, j.achievement_level, j.talent_pool_use,
                        p.created_at, p.updated_at
                    from papers p
                    left join journals j on normalize_text_for_join(p.journal) = j.normalized_journal_name
                    order by p.year desc, p.journal, p.title
                    """
                )
            )

    def papers_missing_affiliations(self, limit: int | None = None, journal_names: list[str] | None = None) -> list[sqlite3.Row]:
        query = """
            select id, title, journal, year, doi, url, paper_url, source, source_api_url,
                first_author_name, corresponding_author_names_json, authors_json, affiliations_json
            from papers
            where doi != ''
              and (affiliations_json = '' or affiliations_json = '[]')
        """
        params: list[object] = []
        if journal_names:
            placeholders = ",".join("?" for _ in journal_names)
            query += f" and journal in ({placeholders})"
            params.extend(journal_names)
        query += " order by journal, year desc, id"
        if limit is not None:
            query += " limit ?"
            params.append(limit)
        with self.connect() as conn:
            return list(conn.execute(query, params))

    def update_paper_authorship_metadata(
        self,
        paper_id: int,
        authors: Iterable[dict],
        affiliations: Iterable[str],
        first_author_name: str = "",
        corresponding_author_names: Iterable[str] = (),
        source_api_url: str = "",
    ) -> None:
        authors_json = json.dumps(list(authors), ensure_ascii=False)
        affiliations_json = json.dumps(list(dict.fromkeys(affiliations)), ensure_ascii=False)
        corresponding_json = json.dumps(list(corresponding_author_names), ensure_ascii=False)
        assignments = [
            "authors_json = ?",
            "affiliations_json = ?",
            "updated_at = current_timestamp",
        ]
        params: list[object] = [authors_json, affiliations_json]
        if first_author_name:
            assignments.append("first_author_name = ?")
            params.append(first_author_name)
        if corresponding_json != "[]":
            assignments.append("corresponding_author_names_json = ?")
            params.append(corresponding_json)
        if source_api_url:
            assignments.append("source_api_url = coalesce(nullif(source_api_url, ''), ?)")
            params.append(canonicalize_url(source_api_url))
        params.append(paper_id)
        with self.connect() as conn:
            conn.execute(f"update papers set {', '.join(assignments)} where id = ?", params)

    def paper_candidate_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        with self.connect() as conn:
            papers = conn.execute(
                """
                select p.id, p.title, p.journal, p.year, p.doi, p.paper_url, p.url, p.source,
                    p.first_author_name, p.corresponding_author_names_json, p.authors_json,
                    p.affiliations_json, j.achievement_level
                from papers p
                left join journals j on normalize_text_for_join(p.journal) = j.normalized_journal_name
                order by p.year desc, p.journal, p.title
                """
            ).fetchall()
        for paper in papers:
            corresponding = _json_list(paper["corresponding_author_names_json"])
            rows.append(_paper_candidate_row(paper, paper["first_author_name"], "first_author"))
            for name in corresponding:
                if name and name != paper["first_author_name"]:
                    rows.append(_paper_candidate_row(paper, name, "corresponding_author"))
        return [row for row in rows if row["name"]]

    def list_school_seeds(self, limit: int | None = None, school_names: list[str] | None = None) -> list[sqlite3.Row]:
        query = "select * from school_seeds where homepage_url != ''"
        params: list[object] = []
        if school_names:
            placeholders = ",".join("?" for _ in school_names)
            query += f" and school_name_en in ({placeholders})"
            params.extend(school_names)
        query += " order by rank is null, rank, school_name_en"
        if limit is not None:
            query += " limit ?"
            params.append(limit)
        with self.connect() as conn:
            return list(conn.execute(query, params))

    def upsert_candidate_links(self, source_id: int | None, candidates: Iterable[LinkCandidate], school: str = "", department: str = "") -> int:
        rows = [
            dict(
                candidate.__dict__,
                url=canonicalize_url(candidate.url),
                source_url=canonicalize_url(candidate.source_url),
                source_id=source_id,
                school=school,
                department=department,
            )
            for candidate in candidates
        ]
        with self.connect() as conn:
            conn.executemany(
                """
                insert into candidate_links(source_id, url, source_url, school, department, anchor_text, page_type, confidence_score)
                values(:source_id, :url, :source_url, :school, :department, :anchor_text, :page_type, :confidence_score)
                on conflict(url) do update set
                    source_id=coalesce(excluded.source_id, candidate_links.source_id),
                    source_url=excluded.source_url,
                    school=excluded.school,
                    department=excluded.department,
                    anchor_text=excluded.anchor_text,
                    page_type=excluded.page_type,
                    confidence_score=excluded.confidence_score,
                    updated_at=current_timestamp
                """,
                rows,
            )
        return len(rows)

    def candidate_link_rows(self, status: str = "queued", limit: int | None = None) -> list[sqlite3.Row]:
        query = "select * from candidate_links where status = ? order by confidence_score desc, id"
        params: list[object] = [status]
        if limit is not None:
            query += " limit ?"
            params.append(limit)
        with self.connect() as conn:
            return list(conn.execute(query, params))

    def mark_candidate_status(self, url: str, status: str) -> None:
        with self.connect() as conn:
            conn.execute("update candidate_links set status = ?, updated_at = current_timestamp where url = ?", (status, url))

    def save_page(
        self,
        fetch: PageFetch,
        source_id: int | None = None,
        source_url: str = "",
        school: str = "",
        department: str = "",
        page_type: str = "",
        content_hash: str = "",
        raw_html_path: str = "",
        parser_status: str = "",
        llm_status: str = "",
    ) -> int:
        canonical_fetch = PageFetch(
            url=canonicalize_url(fetch.url),
            status_code=fetch.status_code,
            html=fetch.html,
            encoding=fetch.encoding,
            error=fetch.error,
        )
        source_url = canonicalize_url(source_url)
        with self.connect() as conn:
            conn.execute(
                """
                insert into pages(source_id, url, source_url, school, department, page_type, status_code,
                    content_hash, raw_html_path, fetched_at, fetch_error, parser_status, llm_status)
                values(?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp, ?, ?, ?)
                on conflict(url) do update set
                    source_id=coalesce(excluded.source_id, pages.source_id),
                    source_url=excluded.source_url,
                    school=excluded.school,
                    department=excluded.department,
                    page_type=excluded.page_type,
                    status_code=excluded.status_code,
                    content_hash=excluded.content_hash,
                    raw_html_path=excluded.raw_html_path,
                    fetched_at=current_timestamp,
                    fetch_error=excluded.fetch_error,
                    parser_status=excluded.parser_status,
                    llm_status=excluded.llm_status,
                    updated_at=current_timestamp
                """,
                (
                    source_id,
                    canonical_fetch.url,
                    source_url,
                    school,
                    department,
                    page_type,
                    canonical_fetch.status_code,
                    content_hash,
                    raw_html_path,
                    canonical_fetch.error,
                    parser_status,
                    llm_status,
                ),
            )
            row = conn.execute("select id from pages where url = ?", (canonical_fetch.url,)).fetchone()
            return int(row["id"])

    def page_rows_for_extraction(self, limit: int | None = None) -> list[sqlite3.Row]:
        query = """
            select * from pages
            where raw_html_path != ''
              and (parser_status = '' or parser_status = 'pending' or parser_status = 'skipped')
              and page_type in ('faculty_candidate', 'faculty_profile', 'profile', 'faculty_list')
            order by id
        """
        params: list[object] = []
        if limit is not None:
            query += " limit ?"
            params.append(limit)
        with self.connect() as conn:
            return list(conn.execute(query, params))

    def page_rows_for_llm_trigger(self, limit: int | None = None) -> list[sqlite3.Row]:
        query = """
            select * from pages
            where raw_html_path != ''
              and (llm_status = '' or llm_status = 'pending')
            order by id
        """
        params: list[object] = []
        if limit is not None:
            query += " limit ?"
            params.append(limit)
        with self.connect() as conn:
            return list(conn.execute(query, params))

    def update_page_status(self, url: str, parser_status: str | None = None, llm_status: str | None = None, page_type: str | None = None) -> None:
        assignments = []
        params: list[object] = []
        if parser_status is not None:
            assignments.append("parser_status = ?")
            params.append(parser_status)
        if llm_status is not None:
            assignments.append("llm_status = ?")
            params.append(llm_status)
        if page_type is not None:
            assignments.append("page_type = ?")
            params.append(page_type)
        if not assignments:
            return
        assignments.append("updated_at = current_timestamp")
        params.append(url)
        with self.connect() as conn:
            conn.execute(f"update pages set {', '.join(assignments)} where url = ?", params)

    def upsert_person_profile(
        self,
        profile: PersonProfile,
        is_likely_chinese_name: bool,
        chinese_name_score: float,
        name_filter_reason: str,
        review_status: str = "new",
        discipline_score=None,
    ) -> int:
        normalized_name = normalize_text(profile.name)
        source_url = canonicalize_url(profile.source_url)
        personal_homepage = canonicalize_url(profile.personal_homepage)
        photo_url = canonicalize_url(profile.photo_url)
        with self.connect() as conn:
            conn.execute(
                """
                insert into people(name, normalized_name, email, school, department, title, photo_url, photo_path,
                    education, advisor, personal_homepage, research_interests, biography, publications_json,
                    primary_source_type, primary_source_url, extraction_method, is_likely_chinese_name,
                    chinese_name_score, name_filter_reason, discipline_score, discipline_is_relevant,
                    discipline_review_status, discipline_matched_disciplines_json, discipline_matched_keywords_json,
                    discipline_negative_keywords_json, discipline_reason, confidence_score, review_status)
                values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'official_site', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(normalized_name, school, primary_source_url) do update set
                    name=excluded.name,
                    email=excluded.email,
                    department=excluded.department,
                    title=excluded.title,
                    photo_url=excluded.photo_url,
                    photo_path=excluded.photo_path,
                    education=excluded.education,
                    advisor=excluded.advisor,
                    personal_homepage=excluded.personal_homepage,
                    research_interests=excluded.research_interests,
                    biography=excluded.biography,
                    publications_json=excluded.publications_json,
                    extraction_method=excluded.extraction_method,
                    is_likely_chinese_name=excluded.is_likely_chinese_name,
                    chinese_name_score=excluded.chinese_name_score,
                    name_filter_reason=excluded.name_filter_reason,
                    discipline_score=excluded.discipline_score,
                    discipline_is_relevant=excluded.discipline_is_relevant,
                    discipline_review_status=excluded.discipline_review_status,
                    discipline_matched_disciplines_json=excluded.discipline_matched_disciplines_json,
                    discipline_matched_keywords_json=excluded.discipline_matched_keywords_json,
                    discipline_negative_keywords_json=excluded.discipline_negative_keywords_json,
                    discipline_reason=excluded.discipline_reason,
                    confidence_score=excluded.confidence_score,
                    review_status=excluded.review_status,
                    updated_at=current_timestamp
                """,
                (
                    profile.name,
                    normalized_name,
                    profile.email,
                    profile.school,
                    profile.department,
                    profile.title,
                    photo_url,
                    profile.photo_path,
                    profile.education,
                    profile.advisor,
                    personal_homepage,
                    profile.research_interests,
                    profile.biography,
                    profile.publications,
                    source_url,
                    profile.extraction_method,
                    1 if is_likely_chinese_name else 0,
                    chinese_name_score,
                    name_filter_reason,
                    float(discipline_score.score) if discipline_score else 0,
                    1 if discipline_score and discipline_score.is_relevant else 0,
                    discipline_score.review_status if discipline_score else "",
                    json.dumps(discipline_score.matched_disciplines, ensure_ascii=False) if discipline_score else "[]",
                    json.dumps(discipline_score.matched_keywords, ensure_ascii=False) if discipline_score else "[]",
                    json.dumps(discipline_score.negative_keywords, ensure_ascii=False) if discipline_score else "[]",
                    discipline_score.reason if discipline_score else "",
                    profile.confidence_score,
                    review_status,
                ),
            )
            row = conn.execute(
                "select id from people where normalized_name = ? and school = ? and primary_source_url = ?",
                (normalized_name, profile.school, source_url),
            ).fetchone()
            return int(row["id"])

    def upsert_publication_people_candidates(self, candidates: Iterable[dict[str, object]]) -> dict[str, int]:
        inserted = 0
        updated = 0
        with self.connect() as conn:
            for candidate in candidates:
                normalized_name = normalize_text(str(candidate["name"]))
                existing = conn.execute(
                    """
                    select * from people
                    where normalized_name = ?
                    order by
                        case when primary_source_type = 'official_site' then 0 else 1 end,
                        id
                    limit 1
                    """,
                    (normalized_name,),
                ).fetchone()
                publication_stats = _publication_stats_from_candidate(candidate)
                paper_links = _split_pipe(str(candidate.get("paper_links", "")))
                publications = _split_pipe(str(candidate.get("paper_titles", "")))
                candidate_review_status = str(candidate.get("review_status", "needs_review"))
                # All publication-only candidates require human review regardless of their
                # stratification tier. Stratification (strong_candidate/needs_review/rejected)
                # is a human-review priority hint, not an auto-approval signal.
                initial_review_status = "needs_review"
                if existing:
                    conn.execute(
                        """
                        update people set
                            publication_stats_json = ?,
                            paper_links_json = ?,
                            publications_json = ?,
                            chinese_name_score = max(chinese_name_score, ?),
                            name_filter_reason = case
                                when name_filter_reason = '' then ?
                                else name_filter_reason
                            end,
                            is_likely_chinese_name = max(is_likely_chinese_name, ?),
                            review_status = case
                                when review_status = 'new' then ?
                                else review_status
                            end,
                            updated_at = current_timestamp
                        where id = ?
                        """,
                        (
                            json.dumps(publication_stats, ensure_ascii=False, sort_keys=True),
                            json.dumps(paper_links, ensure_ascii=False),
                            json.dumps(publications, ensure_ascii=False),
                            float(candidate["chinese_name_score"]),
                            str(candidate["name_filter_reason"]),
                            int(candidate["is_likely_chinese_name"]),
                            initial_review_status,
                            existing["id"],
                        ),
                    )
                    updated += 1
                else:
                    conn.execute(
                        """
                        insert into people(name, normalized_name, school, department, publications_json,
                            publication_stats_json, paper_links_json, primary_source_type, primary_source_url,
                            extraction_method, is_likely_chinese_name, chinese_name_score, name_filter_reason,
                            discipline_score, discipline_is_relevant, discipline_review_status, discipline_reason,
                            confidence_score, review_status)
                        values(?, ?, ?, '', ?, ?, ?, 'publication', ?, 'publication_aggregate', ?, ?, ?,
                            0, 0, 'needs_review', 'publication_only_candidate_pending_enrichment', ?, ?)
                        """,
                        (
                            str(candidate["name"]),
                            normalized_name,
                            str(candidate.get("affiliations", "")),
                            json.dumps(publications, ensure_ascii=False),
                            json.dumps(publication_stats, ensure_ascii=False, sort_keys=True),
                            json.dumps(paper_links, ensure_ascii=False),
                            canonicalize_url(paper_links[0]) if paper_links else "",
                            int(candidate["is_likely_chinese_name"]),
                            float(candidate["chinese_name_score"]),
                            str(candidate["name_filter_reason"]),
                            _publication_candidate_confidence(candidate),
                            initial_review_status,
                        ),
                    )
                    inserted += 1
                _add_publication_candidate_review_issues(conn, candidate, existing["id"] if existing else conn.execute("select last_insert_rowid()").fetchone()[0], paper_links)
            return {"inserted": inserted, "updated": updated}

    def people_rows(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    """
                    select id, name, age, career_stage, email, school, department, field, research_direction, title,
                        primary_source_url as source_url, primary_source_type, personal_homepage, research_interests,
                        biography, publications_json, publication_stats_json, paper_links_json, photo_url, photo_path,
                        education, advisor, confidence_score, review_status, is_likely_chinese_name,
                        chinese_name_score, name_filter_reason, discipline_score, discipline_is_relevant,
                        discipline_review_status, discipline_matched_disciplines_json, discipline_matched_keywords_json,
                        discipline_negative_keywords_json, discipline_reason, created_at, updated_at
                    from people
                    order by school, name, id
                    """
                )
            )

    def deduplicate_people_by_canonical_url(self) -> dict[str, int]:
        with self.connect() as conn:
            rows = list(conn.execute("select * from people order by id"))
            groups: dict[tuple[str, str, str], list[sqlite3.Row]] = {}
            for row in rows:
                key = (row["normalized_name"], row["school"], canonicalize_url(row["primary_source_url"]))
                groups.setdefault(key, []).append(row)

            merged_groups = 0
            deleted_rows = 0
            for (normalized_name, school, canonical_source_url), duplicates in groups.items():
                if len(duplicates) <= 1:
                    row = duplicates[0]
                    if row["primary_source_url"] != canonical_source_url:
                        conn.execute(
                            "update people set primary_source_url = ?, updated_at = current_timestamp where id = ?",
                            (canonical_source_url, row["id"]),
                        )
                    continue

                keeper = max(duplicates, key=_people_row_quality)
                merged = _merged_people_values(keeper, duplicates)
                loser_ids = [row["id"] for row in duplicates if row["id"] != keeper["id"]]
                conn.executemany("delete from people where id = ?", [(row_id,) for row_id in loser_ids])
                conn.execute(
                    """
                    update people set
                        email = ?,
                        department = ?,
                        field = ?,
                        research_direction = ?,
                        title = ?,
                        career_stage = ?,
                        age = ?,
                        birth_year = ?,
                        photo_url = ?,
                        photo_path = ?,
                        education = ?,
                        advisor = ?,
                        personal_homepage = ?,
                        research_interests = ?,
                        biography = ?,
                        publications_json = ?,
                        publication_stats_json = ?,
                        paper_links_json = ?,
                        primary_source_url = ?,
                        extraction_method = ?,
                        is_likely_chinese_name = ?,
                        chinese_name_score = ?,
                        name_filter_reason = ?,
                        discipline_score = ?,
                        discipline_is_relevant = ?,
                        discipline_review_status = ?,
                        discipline_matched_disciplines_json = ?,
                        discipline_matched_keywords_json = ?,
                        discipline_negative_keywords_json = ?,
                        discipline_reason = ?,
                        confidence_score = ?,
                        review_status = ?,
                        updated_at = current_timestamp
                    where id = ?
                    """,
                    (
                        merged["email"],
                        merged["department"],
                        merged["field"],
                        merged["research_direction"],
                        merged["title"],
                        merged["career_stage"],
                        merged["age"],
                        merged["birth_year"],
                        merged["photo_url"],
                        merged["photo_path"],
                        merged["education"],
                        merged["advisor"],
                        merged["personal_homepage"],
                        merged["research_interests"],
                        merged["biography"],
                        merged["publications_json"],
                        merged["publication_stats_json"],
                        merged["paper_links_json"],
                        canonical_source_url,
                        merged["extraction_method"],
                        merged["is_likely_chinese_name"],
                        merged["chinese_name_score"],
                        merged["name_filter_reason"],
                        merged["discipline_score"],
                        merged["discipline_is_relevant"],
                        merged["discipline_review_status"],
                        merged["discipline_matched_disciplines_json"],
                        merged["discipline_matched_keywords_json"],
                        merged["discipline_negative_keywords_json"],
                        merged["discipline_reason"],
                        merged["confidence_score"],
                        merged["review_status"],
                        keeper["id"],
                    ),
                )
                merged_groups += 1
                deleted_rows += len(loser_ids)

            return {"merged_groups": merged_groups, "deleted_rows": deleted_rows}

    def update_person_discipline_score(self, person_id: int, discipline_score) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                update people set
                    discipline_score = ?,
                    discipline_is_relevant = ?,
                    discipline_review_status = ?,
                    discipline_matched_disciplines_json = ?,
                    discipline_matched_keywords_json = ?,
                    discipline_negative_keywords_json = ?,
                    discipline_reason = ?,
                    updated_at = current_timestamp
                where id = ?
                """,
                (
                    float(discipline_score.score),
                    1 if discipline_score.is_relevant else 0,
                    discipline_score.review_status,
                    json.dumps(discipline_score.matched_disciplines, ensure_ascii=False),
                    json.dumps(discipline_score.matched_keywords, ensure_ascii=False),
                    json.dumps(discipline_score.negative_keywords, ensure_ascii=False),
                    discipline_score.reason,
                    person_id,
                ),
            )

    def update_person_review_status(self, person_id: int, review_status: str, resolved_issue_types: list[str] | None = None) -> None:
        """Update a person's review_status and optionally resolve matching open review issues."""
        with self.connect() as conn:
            conn.execute(
                "update people set review_status = ?, updated_at = current_timestamp where id = ?",
                (review_status, person_id),
            )
            if resolved_issue_types:
                placeholders = ",".join("?" * len(resolved_issue_types))
                conn.execute(
                    f"update review_issues set status = 'resolved', resolved_at = current_timestamp "
                    f"where person_id = ? and status = 'open' and issue_type in ({placeholders})",
                    [person_id] + resolved_issue_types,
                )

    def import_review_decisions(self, csv_path: str | Path) -> int:
        """
        Apply review decisions written back from people_review.csv.

        Expected columns: person_id, review_status, resolved_issue_types (pipe-separated).

        Returns the number of decisions applied.
        """
        import csv as _csv

        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV not found: {csv_path}")

        applied = 0
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = _csv.DictReader(handle)
            for row in reader:
                pid = int(row["person_id"])
                new_status = row.get("review_status", "").strip()
                resolved_raw = row.get("resolved_issue_types", "").strip()
                resolved_types = resolved_raw.split(" | ") if resolved_raw else []

                if new_status:
                    self.update_person_review_status(pid, new_status, resolved_types or None)
                    applied += 1

        return applied

    def page_audit_rows(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    """
                    select id, school, department, page_type, status_code, fetch_error, parser_status, llm_status,
                        raw_html_path, url, source_url, fetched_at, updated_at
                    from pages
                    order by school, id
                    """
                )
            )

    def count(self, table: str) -> int:
        allowed = {
            "sources",
            "school_seeds",
            "school_entrypoints",
            "journals",
            "pages",
            "papers",
            "people",
            "person_papers",
            "publication_stats",
            "publication_runs",
            "publication_run_items",
            "candidate_links",
            "review_issues",
        }
        if table not in allowed:
            raise ValueError(f"Unsupported table: {table}")
        with self.connect() as conn:
            row = conn.execute(f"select count(*) as total from {table}").fetchone()
            return int(row["total"])

    def add_review_issue(
        self,
        issue_type: str,
        severity: str = "medium",
        message: str = "",
        person_id: int | None = None,
        related_table: str = "",
        related_id: int | None = None,
        source_url: str = "",
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                insert into review_issues(person_id, related_table, related_id, issue_type, severity, message, source_url)
                values(?, ?, ?, ?, ?, ?, ?)
                """,
                (person_id, related_table, related_id, issue_type, severity, message, source_url),
            )
            return int(cursor.lastrowid)

    def review_issue_rows(self, status: str | None = None) -> list[sqlite3.Row]:
        query = """
            select id, person_id, related_table, related_id, issue_type, severity, message,
                source_url, status, created_at, resolved_at
            from review_issues
        """
        params: tuple[object, ...] = ()
        if status:
            query += " where status = ?"
            params = (status,)
        query += " order by created_at, id"
        with self.connect() as conn:
            return list(conn.execute(query, params))


def normalize_text(value: str) -> str:
    return " ".join(value.casefold().strip().split())


def normalize_doi(value: str) -> str:
    doi = (value or "").strip()
    doi = doi.removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    return doi.lower()


def _json_list(value: str) -> list:
    try:
        loaded = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return loaded if isinstance(loaded, list) else []


def _paper_candidate_row(paper: sqlite3.Row, name: str, author_role: str) -> dict[str, object]:
    authors = _json_list(paper["authors_json"])
    affiliations = _json_list(paper["affiliations_json"])
    author_affiliations = []
    for author in authors:
        if author.get("name") == name:
            author_affiliations = author.get("affiliations") or []
            break
    return {
        "name": name,
        "author_role": author_role,
        "paper_id": paper["id"],
        "title": paper["title"],
        "journal": paper["journal"],
        "achievement_level": paper["achievement_level"] or "",
        "year": paper["year"],
        "doi": paper["doi"],
        "paper_url": paper["paper_url"] or paper["url"],
        "source": paper["source"],
        "affiliations": "; ".join(author_affiliations or affiliations),
    }


def _publication_stats_from_candidate(candidate: dict[str, object]) -> dict[str, object]:
    return {
        "last_5_year_total": int(candidate.get("last_5_year_total") or 0),
        "first_author_total": int(candidate.get("first_author_total") or 0),
        "corresponding_author_total": int(candidate.get("corresponding_author_total") or 0),
        "top_total": int(candidate.get("top_total") or 0),
        "a_plus_total": int(candidate.get("a_plus_total") or 0),
        "a_total": int(candidate.get("a_total") or 0),
        "a1_total": int(candidate.get("a1_total") or 0),
        "a2_total": int(candidate.get("a2_total") or 0),
        "level_counts": _json_object(str(candidate.get("level_counts_json") or "{}")),
        "journals": _split_pipe(str(candidate.get("journals", ""))),
        "years": _split_pipe(str(candidate.get("years", ""))),
        "author_roles": _split_pipe(str(candidate.get("author_roles", ""))),
    }


def _publication_candidate_confidence(candidate: dict[str, object]) -> float:
    score = 0.45
    if int(candidate.get("a_plus_total") or 0) or int(candidate.get("top_total") or 0):
        score += 0.25
    if int(candidate.get("last_5_year_total") or 0) >= 2:
        score += 0.1
    if float(candidate.get("chinese_name_score") or 0) >= 0.7:
        score += 0.1
    return round(min(score, 0.9), 2)


def _add_publication_candidate_review_issues(conn: sqlite3.Connection, candidate: dict[str, object], person_id: int, paper_links: list[str]) -> None:
    """Add review issues for publication-only candidates based on risk signals."""
    name = str(candidate.get("name", "")).strip()
    affiliations = str(candidate.get("affiliations", "")).strip()
    chinese_name_score = float(candidate.get("chinese_name_score") or 0)
    is_likely_chinese = int(candidate.get("is_likely_chinese_name") or 0)
    review_status = str(candidate.get("review_status", "needs_review"))

    source_url = paper_links[0] if paper_links else ""

    if not affiliations:
        conn.execute(
            """
            insert into review_issues(person_id, related_table, related_id, issue_type, severity, message, source_url)
            values(?, 'people', ?, 'missing_affiliation', 'medium',
                'Publication-only candidate has no institution affiliation', ?)
            """,
            (person_id, person_id, source_url),
        )

    if is_likely_chinese and chinese_name_score < 0.7:
        conn.execute(
            """
            insert into review_issues(person_id, related_table, related_id, issue_type, severity, message, source_url)
            values(?, 'people', ?, 'weak_chinese_name_score', 'low',
                'Chinese-name score in review band; candidate may not be Chinese', ?)
            """,
            (person_id, person_id, source_url),
        )

    if review_status == "needs_review":
        conn.execute(
            """
            insert into review_issues(person_id, related_table, related_id, issue_type, severity, message, source_url)
            values(?, 'people', ?, 'publication_only_needs_review', 'medium',
                'Publication-only candidate requires manual review before talent pool use', ?)
            """,
            (person_id, person_id, source_url),
        )

    paper_count = int(candidate.get("last_5_year_total") or 0)
    if is_likely_chinese and paper_count >= 5 and not affiliations:
        conn.execute(
            """
            insert into review_issues(person_id, related_table, related_id, issue_type, severity, message, source_url)
            values(?, 'people', ?, 'high_output_no_affiliation', 'high',
                'High-output author (5+ papers) with no institution affiliation; verify identity', ?)
            """,
            (person_id, person_id, source_url),
        )


def _split_pipe(value: str) -> list[str]:
    return [item.strip() for item in value.split("|") if item.strip()]


def _json_object(value: str) -> dict:
    try:
        loaded = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _people_row_quality(row: sqlite3.Row) -> tuple[int, float, int, int]:
    fields = (
        "email",
        "department",
        "field",
        "research_direction",
        "title",
        "career_stage",
        "photo_url",
        "photo_path",
        "education",
        "advisor",
        "personal_homepage",
        "research_interests",
        "biography",
        "publications_json",
        "publication_stats_json",
        "paper_links_json",
    )
    nonempty = sum(1 for field in fields if row[field])
    https = 1 if str(row["primary_source_url"]).startswith("https://") else 0
    return nonempty, float(row["confidence_score"] or 0), https, int(row["id"])


def _merged_people_values(keeper: sqlite3.Row, rows: list[sqlite3.Row]) -> dict[str, object]:
    merged = dict(keeper)
    merge_fields = (
        "email",
        "department",
        "field",
        "research_direction",
        "title",
        "career_stage",
        "photo_url",
        "photo_path",
        "education",
        "advisor",
        "personal_homepage",
        "research_interests",
        "biography",
        "publications_json",
        "publication_stats_json",
        "paper_links_json",
        "extraction_method",
        "name_filter_reason",
        "discipline_review_status",
        "discipline_matched_disciplines_json",
        "discipline_matched_keywords_json",
        "discipline_negative_keywords_json",
        "discipline_reason",
    )
    for field in merge_fields:
        if merged.get(field):
            continue
        for row in sorted(rows, key=_people_row_quality, reverse=True):
            if row[field]:
                merged[field] = row[field]
                break
    merged["age"] = merged.get("age") or _first_nonempty(rows, "age")
    merged["birth_year"] = merged.get("birth_year") or _first_nonempty(rows, "birth_year")
    merged["is_likely_chinese_name"] = max(int(row["is_likely_chinese_name"] or 0) for row in rows)
    merged["chinese_name_score"] = max(float(row["chinese_name_score"] or 0) for row in rows)
    merged["discipline_score"] = max(float(row["discipline_score"] or 0) for row in rows)
    merged["discipline_is_relevant"] = max(int(row["discipline_is_relevant"] or 0) for row in rows)
    merged["confidence_score"] = max(float(row["confidence_score"] or 0) for row in rows)
    if any(row["review_status"] == "needs_review" for row in rows):
        merged["review_status"] = "needs_review"
    return merged


def _first_nonempty(rows: list[sqlite3.Row], field: str) -> object:
    for row in sorted(rows, key=_people_row_quality, reverse=True):
        if row[field] is not None and row[field] != "":
            return row[field]
    return None
