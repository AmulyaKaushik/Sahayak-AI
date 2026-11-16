"""Folder sync: scheme from the sub-folder, skips, de-duplication, retry."""

from rag import folder_sync
from rag.ingestion import IngestResult

PDF = b"%PDF-1.4 fake"


def _make(root, relative, data=PDF):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _patch(monkeypatch, existing=None):
    calls = {"ingest": [], "approve": []}

    def fake_ingest(filename, data, scheme_id=None):
        calls["ingest"].append((filename, scheme_id))
        return IngestResult(doc_id="new-doc", doc_type="loan", status="active")

    def fake_approve(doc_id, doc_type, scheme_id=None):
        calls["approve"].append((doc_id, doc_type, scheme_id))
        return IngestResult(doc_id=doc_id, doc_type=doc_type, status="active")

    monkeypatch.setattr(folder_sync, "ingest_pdf", fake_ingest)
    monkeypatch.setattr(folder_sync, "approve_document", fake_approve)
    monkeypatch.setattr(folder_sync.repository, "find_by_hash", lambda h: existing)
    return calls


def test_scheme_comes_from_the_subfolder(tmp_path, monkeypatch):
    calls = _patch(monkeypatch)
    _make(tmp_path, "home_loan/policy.pdf")
    _make(tmp_path, "faq.PDF")
    results = {r.file: r for r in folder_sync.sync_folder(tmp_path)}

    assert results["home_loan/policy.pdf"].scheme_id == "home_loan"
    assert results["faq.PDF"].scheme_id is None
    assert folder_sync._scheme_for(__import__("pathlib").Path("home_loan.pdf")) == ("home_loan", None)
    assert sorted(calls["ingest"], key=str) == [("faq.PDF", None), ("policy.pdf", "home_loan")]
    assert all(r.result == "ingested" for r in results.values())


def test_unknown_folder_and_bad_files_are_reported_not_ingested(tmp_path, monkeypatch):
    calls = _patch(monkeypatch)
    _make(tmp_path, "not_a_scheme/x.pdf")
    _make(tmp_path, "home_loan/notes.pdf", b"just text")
    _make(tmp_path, "home_loan/readme.txt", b"ignored")
    results = {r.file: r for r in folder_sync.sync_folder(tmp_path)}

    assert results["not_a_scheme/x.pdf"].result == "skipped"
    assert "not a known scheme" in results["not_a_scheme/x.pdf"].note
    assert results["home_loan/notes.pdf"].result == "error"
    assert "home_loan/readme.txt" not in results
    assert calls["ingest"] == []


def test_already_ingested_file_is_unchanged(tmp_path, monkeypatch):
    existing = {"doc_id": "d1", "status": "active", "doc_type": "loan", "scheme_id": "home_loan"}
    calls = _patch(monkeypatch, existing=existing)
    _make(tmp_path, "home_loan/policy.pdf")
    [item] = folder_sync.sync_folder(tmp_path)
    assert item.result == "unchanged" and item.doc_id == "d1"
    assert calls["ingest"] == [] and calls["approve"] == []


def test_moving_an_ingested_file_into_a_scheme_folder_retags_it(tmp_path, monkeypatch):
    existing = {"doc_id": "d4", "status": "active", "doc_type": "scheme", "scheme_id": None}
    calls = _patch(monkeypatch, existing=existing)
    tagged = []
    monkeypatch.setattr(folder_sync.repository, "set_scheme", lambda d, s: tagged.append((d, s)))
    _make(tmp_path, "sukanya_samriddhi/guide.pdf")
    _make(tmp_path, "top_level.pdf")
    results = {r.file: r for r in folder_sync.sync_folder(tmp_path)}
    assert results["sukanya_samriddhi/guide.pdf"].result == "retagged"
    assert results["top_level.pdf"].result == "unchanged"  # top level never strips a scheme
    assert tagged == [("d4", "sukanya_samriddhi")]
    assert calls["ingest"] == [] and calls["approve"] == []


def test_failed_embedding_is_retried_and_review_waits(tmp_path, monkeypatch):
    failed = {"doc_id": "d2", "status": "embedding_failed", "doc_type": "loan", "scheme_id": None}
    calls = _patch(monkeypatch, existing=failed)
    _make(tmp_path, "home_loan/policy.pdf")
    [item] = folder_sync.sync_folder(tmp_path)
    assert item.result == "retried" and item.status == "active"
    assert calls["approve"] == [("d2", "loan", "home_loan")]

    waiting = {"doc_id": "d3", "status": "needs_review", "doc_type": None, "scheme_id": None}
    _patch(monkeypatch, existing=waiting)
    [item] = folder_sync.sync_folder(tmp_path)
    assert item.result == "skipped" and "needs_review" in item.note


def test_missing_folder_returns_nothing(tmp_path):
    assert folder_sync.sync_folder(tmp_path / "nope") == []
