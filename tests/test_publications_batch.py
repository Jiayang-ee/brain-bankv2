from faculty_spider_v3.models import Journal, PaperRecord
from faculty_spider_v3.publications import batch
from faculty_spider_v3.storage import FacultySpiderV3Store


class FakeOpenAlexClient:
    def search_works_by_journal(self, journal_name, from_year, per_page=25):
        return [
            PaperRecord(
                title=f"{journal_name} OpenAlex Paper",
                journal=journal_name,
                year=2026,
                authors=({"name": "Yifan Chen", "position": "first", "affiliations": ["Example University"]},),
                first_author_name="Yifan Chen",
                source="openalex",
            )
        ]


class FailingCrossrefClient:
    def search_works_by_journal(self, journal_name, from_year, per_page=25, issn=""):
        raise RuntimeError("crossref down")


def test_batch_run_creates_run_items_and_skips_completed_on_resume(tmp_path, monkeypatch):
    store = _store_with_journals(tmp_path)
    groups_csv = _groups_csv(tmp_path)
    monkeypatch.setattr(batch, "OpenAlexClient", FakeOpenAlexClient)
    monkeypatch.setattr(batch, "CrossrefClient", FailingCrossrefClient)

    result = batch.run_publication_batch(
        store,
        journal_group="default_batch",
        from_year=2022,
        works_per_journal=5,
        groups_csv=groups_csv,
        resume=True,
        refresh_exports=False,
    )

    assert result.status == "completed"
    assert result.items_processed == 2
    assert result.papers_seen == 2
    assert result.errors == 2
    assert store.count("publication_runs") == 1
    assert store.count("publication_run_items") == 2
    assert store.count("papers") == 2
    status = batch.publication_batch_status(store, result.run_id)
    assert status["items"] == {"completed": 2}

    resumed = batch.run_publication_batch(
        store,
        journal_group="default_batch",
        from_year=2022,
        works_per_journal=5,
        groups_csv=groups_csv,
        run_id=result.run_id,
        resume=True,
        refresh_exports=False,
    )

    assert resumed.run_id == result.run_id
    assert resumed.items_processed == 0
    assert store.count("papers") == 2


def test_batch_run_marks_item_failed_when_all_sources_fail(tmp_path, monkeypatch):
    store = _store_with_journals(tmp_path)
    groups_csv = _groups_csv(tmp_path)
    monkeypatch.setattr(batch, "OpenAlexClient", FailingOpenAlexClient)
    monkeypatch.setattr(batch, "CrossrefClient", FailingCrossrefClient)

    result = batch.run_publication_batch(
        store,
        journal_group="default_batch",
        from_year=2022,
        works_per_journal=5,
        sources=("openalex", "crossref"),
        groups_csv=groups_csv,
        max_journals=1,
        refresh_exports=False,
    )

    assert result.status == "partial"
    items = store.publication_run_items(result.run_id)
    assert items[0]["status"] == "failed"
    assert "openalex failed" in items[0]["last_error"]
    assert "crossref failed" in items[0]["last_error"]


class FailingOpenAlexClient:
    def search_works_by_journal(self, journal_name, from_year, per_page=25):
        raise RuntimeError("openalex down")


def _store_with_journals(tmp_path):
    store = FacultySpiderV3Store(tmp_path / "test.sqlite")
    store.init_db()
    store.upsert_journals(
        [
            Journal(
                source_file="test",
                journal_system="UTD",
                discipline="Management",
                journal_name="Management Science",
                issn_cn="0025-1909",
                achievement_level="A+",
                talent_pool_use="强入库论文锚点",
            ),
            Journal(
                source_file="test",
                journal_system="UTD",
                discipline="Management",
                journal_name="Operations Research",
                issn_cn="0030-364X",
                achievement_level="A+",
                talent_pool_use="强入库论文锚点",
            ),
        ]
    )
    return store


def _groups_csv(tmp_path):
    path = tmp_path / "publication_journal_groups.csv"
    path.write_text(
        "journal_name,achievement_level,issn,collection_group,default_for_m6,reason,notes\n"
        "MANAGEMENT SCIENCE,A+,0025-1909,default_batch,yes,,\n"
        "OPERATIONS RESEARCH,A+,0030-364X,default_batch,yes,,\n",
        encoding="utf-8",
    )
    return path
