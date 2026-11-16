"""Source adapters and incremental collection. Discovered entities need review."""
from __future__ import annotations
import json
import re
from pathlib import Path
from .extract import extract_page, clean
from .net import Client, FetchError, canonical_url, domain, same_site

WIKIDATA = "https://www.wikidata.org/w/api.php"


def registry(path):
    companies = json.loads(Path(path).read_text())
    ids, domains = set(), set()
    for c in companies:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", c["id"]):
            raise ValueError("Invalid company id")
        c["website"] = canonical_url(c["website"])
        d = domain(c["website"])
        if c["id"] in ids or d in domains:
            raise ValueError("Duplicate company id/domain: review entity identity")
        ids.add(c["id"]); domains.add(d)
        for page in c.get("pages", []):
            if not same_site(page, c["website"]):
                raise ValueError("Registry page must match the company's approved domain")
    return companies


def wikidata_document(client, company):
    # Never join on a fuzzy name alone. Exact approved website domain is mandatory.
    data, _ = client.json(WIKIDATA, {"action": "wbsearchentities", "search": company["name"], "language": "en", "format": "json", "limit": 5})
    ids = [x["id"] for x in data.get("search", []) if re.fullmatch(r"Q\d+", x.get("id", ""))]
    if not ids:
        return None
    data, _ = client.json(WIKIDATA, {"action": "wbgetentities", "ids": "|".join(ids), "props": "labels|descriptions|claims", "languages": "en|zh", "format": "json"})
    matches = []
    for qid, entity in data.get("entities", {}).items():
        claims = entity.get("claims", {})
        websites = [x.get("mainsnak", {}).get("datavalue", {}).get("value") for x in claims.get("P856", []) if x.get("rank") != "deprecated"]
        valid_sites = []
        for site in websites:
            try:
                if isinstance(site, str) and domain(site) == domain(company["website"]):
                    valid_sites.append(site)
            except FetchError:
                pass
        if not valid_sites:
            continue
        result = []
        text = [company["name"], entity.get("descriptions", {}).get("en", {}).get("value", "")]
        for statement in claims.get("P571", []):
            if statement.get("rank") == "deprecated":
                continue
            # End-dated facts are historical; do not silently label current.
            if "P582" in statement.get("qualifiers", {}):
                continue
            value = statement.get("mainsnak", {}).get("datavalue", {}).get("value", {})
            date = value.get("time", "")
            precision = value.get("precision", 0)
            if date.startswith("+") and precision >= 9:
                formatted = date[1:11] if precision >= 11 else date[1:8] if precision == 10 else date[1:5]
                result.append({"field": "founded_date", "value": formatted, "quote": date, "method": "wikidata:P571"})
                text.append("Founded: " + formatted)
        # Wikidata may repeat the company's own source, so it is not independent corroboration.
        matches.append(("https://www.wikidata.org/wiki/" + qid,
                        {"title": company["name"] + " — Wikidata", "text": "\n".join(text), "claims": result}))
    if len(matches) != 1:
        return None
    return matches[0]


def discover(client, store, limit=50):
    query = """SELECT DISTINCT ?company ?companyLabel ?website WHERE {
      ?company wdt:P452 wd:Q11660; wdt:P856 ?website.
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en,zh". }
    } LIMIT """ + str(min(max(limit, 1), 200))
    data, _ = client.json("https://query.wikidata.org/sparql", {"query": query, "format": "json"}, headers={"Accept": "application/sparql-results+json"})
    count = 0
    for row in data.get("results", {}).get("bindings", []):
        try:
            website = canonical_url(row["website"]["value"])
            store.candidate(row["companyLabel"]["value"], website, row["company"]["value"])
            count += 1
        except (KeyError, FetchError):
            continue
    return count


def run(store, companies, *, max_pages=3, discover_new=True, client=None):
    if not 1 <= max_pages <= 10:
        raise ValueError("max_pages must be between 1 and 10")
    client = client or Client()
    store.register(companies)
    run_id = store.start_run()
    summary = {"companies": len(companies), "successful_sources": 0, "failed_sources": 0, "changed_sources": 0, "discovered_candidates": 0}
    for company in companies:
        queue = list(dict.fromkeys([company["website"], *company.get("pages", [])]))
        seen = set()
        while queue and len(seen) < max_pages:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            try:
                response = client.get(url, robots=True, allowed_site=company["website"])
                if response.content_type not in {"text/html", "application/xhtml+xml"}:
                    raise FetchError("Unsupported content type")
                page = extract_page(response.text, response.url, company)
                _, changed = store.upsert(company, response.url, page)
                store.attempt(run_id, company["id"], url, "ok")
                summary["successful_sources"] += 1
                summary["changed_sources"] += int(changed)
                queue.extend(x for x in page["links"] if x not in seen and x not in queue)
            except (FetchError, ValueError) as exc:
                summary["failed_sources"] += 1
                store.attempt(run_id, company["id"], url, "failed", str(exc))
        if company.get("wikidata", True):
            try:
                item = wikidata_document(client, company)
                if item:
                    url, page = item
                    _, changed = store.upsert(company, url, page, kind="knowledge_base", publisher=company["id"])
                    summary["successful_sources"] += 1
                    summary["changed_sources"] += int(changed)
                    store.attempt(run_id, company["id"], url, "ok")
                else:
                    store.attempt(run_id, company["id"], WIKIDATA, "unmatched", "No unique website-domain match; not merged")
            except (FetchError, ValueError, KeyError) as exc:
                summary["failed_sources"] += 1
                store.attempt(run_id, company["id"], WIKIDATA, "failed", str(exc))
    if discover_new:
        try:
            summary["discovered_candidates"] = discover(client, store)
            store.attempt(run_id, "discovery", "https://query.wikidata.org/sparql", "ok")
        except (FetchError, ValueError, KeyError) as exc:
            summary["discovery_error"] = str(exc)
            store.attempt(run_id, "discovery", "https://query.wikidata.org/sparql", "failed", str(exc))
    summary["status"] = "failed" if not summary["successful_sources"] else "partial" if summary["failed_sources"] or summary.get("discovery_error") else "ok"
    store.finish_run(run_id, summary)
    return summary
