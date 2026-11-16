"""SQLite evidence store: current sources, bounded revision history and run health."""
from __future__ import annotations
import hashlib
import json
import sqlite3
import re
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def compatible(field, a, b):
    if a == b:
        return True
    if field == "founded_date" and all(re.fullmatch(r"\d{4}(?:-\d{2}){0,2}", x) for x in (a, b)):
        return a.startswith(b + "-") or b.startswith(a + "-")
    return False


class Store:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS companies(
          id TEXT PRIMARY KEY, name TEXT NOT NULL, website TEXT NOT NULL UNIQUE,
          tags TEXT NOT NULL, aliases TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS documents(
          id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
          url TEXT NOT NULL, title TEXT NOT NULL, text TEXT NOT NULL,
          kind TEXT NOT NULL, publisher TEXT NOT NULL, content_hash TEXT NOT NULL,
          first_seen TEXT NOT NULL, changed_at TEXT NOT NULL, checked_at TEXT NOT NULL,
          published_at TEXT, claims TEXT NOT NULL, UNIQUE(company_id,url));
        CREATE VIRTUAL TABLE IF NOT EXISTS evidence_fts USING fts5(
          document_id UNINDEXED, company, title, text, tokenize='unicode61');
        CREATE TABLE IF NOT EXISTS changes(
          id INTEGER PRIMARY KEY, company_id TEXT, document_id TEXT, seen_at TEXT,
          old_hash TEXT, new_hash TEXT, old_claims TEXT, new_claims TEXT);
        CREATE TABLE IF NOT EXISTS runs(
          id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, summary TEXT);
        CREATE TABLE IF NOT EXISTS attempts(
          run_id TEXT, company_id TEXT, url TEXT, status TEXT, reason TEXT, checked_at TEXT);
        CREATE TABLE IF NOT EXISTS candidates(
          id TEXT PRIMARY KEY, name TEXT, website TEXT, source TEXT, discovered_at TEXT,
          status TEXT NOT NULL DEFAULT 'needs_review');
        CREATE TABLE IF NOT EXISTS vectors(
          document_id TEXT, content_hash TEXT, model TEXT, vector TEXT,
          PRIMARY KEY(document_id, model));
        """)

    def close(self):
        self.db.close()

    def register(self, companies):
        with self.db:
            self.db.execute("UPDATE companies SET active=0")
            for c in companies:
                self.db.execute("""INSERT INTO companies VALUES(?,?,?,?,?,1)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, website=excluded.website,
                  tags=excluded.tags, aliases=excluded.aliases, active=1""",
                (c["id"], c["name"], c["website"], json.dumps(c.get("tags", []), ensure_ascii=False), json.dumps(c.get("aliases", []), ensure_ascii=False)))

    def upsert(self, company, url, page, *, kind="official", publisher=None):
        stamp = now()
        key = digest(company["id"] + "\n" + url)
        body_hash = digest(page["text"] + json.dumps(page.get("claims", []), sort_keys=True))
        claims = json.dumps(page.get("claims", []), ensure_ascii=False, sort_keys=True)
        old = self.db.execute("SELECT * FROM documents WHERE id=?", (key,)).fetchone()
        changed = old is None or old["content_hash"] != body_hash
        with self.db:
            self.db.execute("""INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET title=excluded.title,text=excluded.text,
              kind=excluded.kind,publisher=excluded.publisher,content_hash=excluded.content_hash,
              changed_at=excluded.changed_at,checked_at=excluded.checked_at,
              published_at=excluded.published_at,claims=excluded.claims""",
            (key, company["id"], url, page["title"], page["text"], kind,
             publisher or company["id"], body_hash, old["first_seen"] if old else stamp,
             stamp if changed else old["changed_at"], stamp, page.get("published_at"), claims))
            if changed:
                self.db.execute("INSERT INTO changes(company_id,document_id,seen_at,old_hash,new_hash,old_claims,new_claims) VALUES(?,?,?,?,?,?,?)",
                                (company["id"], key, stamp, old["content_hash"] if old else None, body_hash, old["claims"] if old else "[]", claims))
                self.db.execute("DELETE FROM evidence_fts WHERE document_id=?", (key,))
                self.db.execute("INSERT INTO evidence_fts VALUES(?,?,?,?)",
                                (key, company["name"] + " " + " ".join(company.get("aliases", [])), page["title"], page["text"]))
        return key, changed

    def attempt(self, run_id, company_id, url, status, reason=""):
        with self.db:
            self.db.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?)", (run_id, company_id, url, status, reason[:200], now()))

    def start_run(self):
        stamp = now()
        import uuid
        run_id = stamp + "-" + uuid.uuid4().hex[:6]
        with self.db:
            self.db.execute("INSERT INTO runs VALUES(?,?,NULL,NULL)", (run_id, stamp))
        return run_id

    def finish_run(self, run_id, summary):
        with self.db:
            self.db.execute("UPDATE runs SET finished_at=?,summary=? WHERE id=?", (now(), json.dumps(summary), run_id))
            # Bound diagnostic growth without dropping current evidence.
            self.db.execute("DELETE FROM attempts WHERE run_id NOT IN (SELECT id FROM runs ORDER BY started_at DESC LIMIT 90)")
            self.db.execute("DELETE FROM runs WHERE id NOT IN (SELECT id FROM runs ORDER BY started_at DESC LIMIT 90)")
            self.db.execute("DELETE FROM changes WHERE id NOT IN (SELECT id FROM changes ORDER BY id DESC LIMIT 10000)")

    def candidate(self, name, website, source):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO candidates(id,name,website,source,discovered_at) VALUES(?,?,?,?,?)", (digest(website), name, website, source, now()))

    def snapshot(self):
        companies = []
        for row in self.db.execute("SELECT * FROM companies WHERE active=1 ORDER BY name"):
            c = dict(row)
            c["tags"], c["aliases"] = json.loads(c["tags"]), json.loads(c["aliases"])
            docs = [dict(d) for d in self.db.execute("SELECT * FROM documents WHERE company_id=? ORDER BY checked_at DESC", (c["id"],))]
            facts = {}
            sources = []
            for d in docs:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(d["checked_at"])).total_seconds() / 86400
                sources.append({k: d[k] for k in ("id", "url", "title", "kind", "publisher", "content_hash", "first_seen", "changed_at", "checked_at", "published_at")} | {"excerpt": d["text"][:280], "stale": age > 30})
                for claim in json.loads(d["claims"]):
                    key = claim["field"]
                    norm = str(claim["value"]).casefold().strip()
                    values = facts.setdefault(key, {})
                    v = values.setdefault(norm, {"value": claim["value"], "evidence": [], "publishers": set(), "fresh_publishers": set(), "fresh": False})
                    v["evidence"].append({"document_id": d["id"], "url": d["url"], "quote": claim["quote"][:280], "method": claim["method"], "checked_at": d["checked_at"], "stale": age > 30})
                    v["publishers"].add(d["publisher"])
                    if age <= 30:
                        v["fresh_publishers"].add(d["publisher"])
                        v["fresh"] = True
            c["facts"] = {}
            for field, values in facts.items():
                output = []
                fresh_values = [k for k, v in values.items() if v["fresh"]]
                conflict = any(not compatible(field, a, b) for i, a in enumerate(fresh_values) for b in fresh_values[i+1:])
                for v in values.values():
                    n = len(v.pop("publishers"))
                    n_fresh = len(v.pop("fresh_publishers"))
                    fresh = v.pop("fresh")
                    status = "stale" if not fresh else "conflict" if conflict and field not in {"self_description", "page_description"} else "corroborated" if n_fresh >= 2 else "single_source"
                    output.append(v | {"status": status, "publisher_groups": n, "fresh_publisher_groups": n_fresh})
                c["facts"][field] = output
            c["sources"] = sources
            c["last_checked"] = max((d["checked_at"] for d in docs), default=None)
            c["status"] = "no_evidence" if not docs else "stale" if all(s["stale"] for s in sources) else "conflict" if any(v["status"] == "conflict" for a in c["facts"].values() for v in a) else "evidence_available"
            c["unknown_fields"] = [f for f in ("legal_name", "founded_date", "founders", "headquarters", "funding", "valuation", "employee_count") if f not in c["facts"]]
            companies.append(c)
        runs = [dict(r) for r in self.db.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT 10")]
        for r in runs:
            r["summary"] = json.loads(r["summary"] or "{}")
        latest = runs[0]["id"] if runs else ""
        return {"generated_at": now(), "schema_version": 1, "companies": companies,
                "runs": runs, "attempts": [dict(r) for r in self.db.execute("SELECT * FROM attempts WHERE run_id=?", (latest,))],
                "candidates": [dict(r) for r in self.db.execute("SELECT * FROM candidates ORDER BY discovered_at DESC LIMIT 500")],
                "changes": [dict(r) for r in self.db.execute("SELECT company_id,document_id,seen_at,old_hash,new_hash FROM changes ORDER BY id DESC LIMIT 100")]}
