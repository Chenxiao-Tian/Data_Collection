import json
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from ai_radar.collect import registry, run, wikidata_document
from ai_radar.extract import extract_page
from ai_radar.net import FetchError, Response, canonical_url, same_site, validate_public_url
from ai_radar.search import search
from ai_radar.store import Store
from ai_radar.web import render, export_snapshot

C = {"id": "atlas", "name": "Atlas AI", "website": "https://atlas.example/", "tags": ["推理"], "aliases": ["阿特拉斯"], "wikidata": False}
HTML = '''<html><head><title>Atlas AI</title><meta name="description" content="Atlas builds open source inference tools for developers and research teams."><script type="application/ld+json">{"@type":"Organization","url":"https://atlas.example","legalName":"Atlas Research Ltd","foundingDate":"2020-04-01"}</script></head><body><main><h1>Inference infrastructure for everyone</h1><p>Build and deploy models with transparent open source software for developers and research teams.</p><a href="/about">Company</a><a href="https://evil.example/about">Foreign</a><script>malicious()</script></main></body></html>'''


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "test.sqlite")
    s.register([C])
    yield s
    s.close()


def page(value="2020-04-01"):
    return {"title": "Atlas inference tools", "text": "Atlas AI builds open source inference tools. Founded " + value,
            "claims": [{"field": "founded_date", "value": value, "quote": value, "method": "fixture"}]}


def test_html_evidence_and_links():
    p = extract_page(HTML, C["website"], C)
    assert "malicious()" not in p["text"]
    assert any(c["field"] == "legal_name" for c in p["claims"])
    assert p["links"] == ["https://atlas.example/about"]


def test_foreign_jsonld_not_merged():
    p = extract_page(HTML.replace('"url":"https://atlas.example"', '"url":"https://other.example"'), C["website"], C)
    assert not any(c["field"] == "legal_name" for c in p["claims"])


def test_article_description_is_not_company_description():
    p = extract_page(HTML, C["website"] + "blog/customer-story", C)
    assert any(c["field"] == "page_description" for c in p["claims"])
    assert not any(c["field"] == "self_description" for c in p["claims"])


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://user:password@example.com/", "ftp://example.com", "https://example.com:9000/"])
def test_invalid_urls(url):
    with pytest.raises(FetchError):
        canonical_url(url)


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "192.168.1.2"])
def test_private_destinations_blocked(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", (ip, 0))])
    with pytest.raises(FetchError):
        validate_public_url("https://public.example/")


def test_subdomain_boundary():
    assert same_site("https://www.atlas.example/about", C["website"])
    assert not same_site("https://atlas.example.evil.org/", C["website"])


def test_idempotency_and_history(store):
    key, changed = store.upsert(C, C["website"], page())
    assert changed
    assert not store.upsert(C, C["website"], page())[1]
    assert store.db.execute("SELECT count(*) FROM changes").fetchone()[0] == 1
    store.upsert(C, C["website"], page("2021-02-01"))
    assert store.db.execute("SELECT count(*) FROM documents").fetchone()[0] == 1
    assert store.db.execute("SELECT count(*) FROM changes").fetchone()[0] == 2
    assert store.snapshot()["companies"][0]["facts"]["founded_date"][0]["value"] == "2021-02-01"


def test_conflicting_evidence_never_overwritten(store):
    store.upsert(C, C["website"], page())
    store.upsert(C, C["website"] + "about", page("2021-02-01"))
    values = store.snapshot()["companies"][0]["facts"]["founded_date"]
    assert len(values) == 2
    assert all(v["status"] == "conflict" for v in values)


def test_same_publisher_not_independent(store):
    store.upsert(C, C["website"], page())
    store.upsert(C, C["website"] + "about", page())
    v = store.snapshot()["companies"][0]["facts"]["founded_date"][0]
    assert v["status"] == "single_source"
    assert v["publisher_groups"] == 1


def test_partial_date_precision_is_not_a_conflict(store):
    store.upsert(C, C["website"], page("2020-04"))
    store.upsert(C, C["website"] + "about", page("2020-04-01"))
    assert all(v["status"] == "single_source" for v in store.snapshot()["companies"][0]["facts"]["founded_date"])


def test_independent_groups_corroborate(store):
    store.upsert(C, C["website"], page())
    store.upsert(C, "https://reviewed.example/article", page(), kind="reviewed_external", publisher="independent-reviewer")
    assert store.snapshot()["companies"][0]["facts"]["founded_date"][0]["status"] == "corroborated"


def test_stale_support_not_counted_as_fresh_corroboration(store):
    key, _ = store.upsert(C, C["website"], page())
    store.upsert(C, "https://reviewed.example/article", page(), publisher="reviewer")
    old = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()
    with store.db:
        store.db.execute("UPDATE documents SET checked_at=? WHERE id=?", (old, key))
    assert store.snapshot()["companies"][0]["facts"]["founded_date"][0]["status"] == "single_source"


def test_unknown_is_not_zero(store):
    c = store.snapshot()["companies"][0]
    assert c["status"] == "no_evidence"
    assert "funding" in c["unknown_fields"] and "funding" not in c["facts"]


def test_bilingual_search_and_injection(store):
    store.upsert(C, C["website"], page())
    assert search(store, "推理")["results"][0]["company_id"] == "atlas"
    assert search(store, "阿特拉斯")["results"]
    assert search(store, "zzzxxyyunknown")["results"] == []
    search(store, '\") OR 1=1 --')
    assert store.db.execute("SELECT count(*) FROM companies").fetchone()[0] == 1


def test_export_escapes_script_injection(store, tmp_path):
    store.upsert(C, C["website"], page('</script><script>alert(1)</script>'))
    output = render(store.snapshot())
    assert '</script><script>alert(1)</script>' not in output
    export_snapshot(store.snapshot(), tmp_path / "out")
    assert (tmp_path / "out/index.html").exists()
    assert json.loads((tmp_path / "out/companies.json").read_text())["schema_version"] == 1


def test_partial_failure_keeps_previous_evidence(store):
    store.upsert(C, C["website"], page())
    class Broken:
        def get(self, *a, **kw):
            raise FetchError("HTTP 503")
    result = run(store, [C], client=Broken(), discover_new=False)
    assert result["status"] == "failed"
    assert len(store.snapshot()["companies"][0]["sources"]) == 1
    assert store.snapshot()["attempts"][0]["status"] == "failed"


def test_collection_and_search_end_to_end(store):
    class FixtureClient:
        def get(self, url, **kw):
            return Response(url, HTML, "text/html", "sha", {})
    result = run(store, [C], client=FixtureClient(), discover_new=False, max_pages=2)
    assert result["successful_sources"] == 2
    assert search(store, "inference")["results"]
    assert store.snapshot()["companies"][0]["facts"]["legal_name"][0]["value"] == "Atlas Research Ltd"


def test_registry_rejects_duplicate_domain(tmp_path):
    p = tmp_path / "registry.json"
    p.write_text(json.dumps([C, C | {"id": "different"}]))
    with pytest.raises(ValueError):
        registry(p)


def test_wikidata_name_match_alone_is_rejected():
    class Fake:
        def json(self, url, params, **kw):
            if params["action"] == "wbsearchentities":
                return {"search": [{"id": "Q1"}]}, None
            return {"entities": {"Q1": {"claims": {"P856": [{"mainsnak": {"datavalue": {"value": "https://other.example/"}}}]}}}}, None
    assert wikidata_document(Fake(), C) is None


def test_challenge_not_used_as_company_fact():
    with pytest.raises(ValueError):
        extract_page('<html><title>Just a moment</title><body>'+('verify your identity '*20)+'</body></html>', C["website"], C)
