"""Portable dashboard export and a loopback-only, read-only search API."""
from __future__ import annotations
import csv
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from .store import Store
from .search import search


def render(snapshot):
    template = Path(__file__).with_name("dashboard.html").read_text()
    payload = json.dumps(snapshot, ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return template.replace("/*__RADAR_DATA__*/null", payload)


def export_snapshot(snapshot, out):
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(render(snapshot), encoding="utf-8")
    (out / "companies.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    with (out / "companies.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["company", "website", "status", "source_count", "last_checked", "unknown_fields"])
        for c in snapshot["companies"]:
            values = [c["name"], c["website"], c["status"], len(c["sources"]), c["last_checked"] or "", ";".join(c["unknown_fields"])]
            # Spreadsheet formula injection prevention for external text.
            writer.writerow(["'" + x if isinstance(x, str) and x.startswith(("=", "+", "-", "@", "\t", "\r")) else x for x in values])
    s = snapshot["runs"][0]["summary"] if snapshot["runs"] else {}
    lines = ["# AI Company Radar — latest collection", "", f"Generated: {snapshot['generated_at']}", "", f"Companies: {len(snapshot['companies'])}; successful sources this run: {s.get('successful_sources', 0)}; failed sources: {s.get('failed_sources', 0)}.", "", "Download `index.html` and open it locally for the searchable dashboard. Full-text API search: `ai-radar serve`. CSV/JSON contain source links and missing-field labels.", "", "| Company | Evidence state | Sources |", "|---|---|---:|"]
    for c in snapshot["companies"]:
        name = c["name"].replace("|", "\\|")
        lines.append(f"| [{name}]({c['website']}) | {c['status']} | {len(c['sources'])} |")
    (out / "README.md").write_text("\n".join(lines) + "\n")


def serve(db_path, port=8080):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlsplit(self.path)
            store = Store(db_path)
            try:
                if parsed.path == "/":
                    data = render(store.snapshot()).encode()
                    content_type = "text/html; charset=utf-8"
                elif parsed.path == "/api/companies":
                    data = json.dumps(store.snapshot(), ensure_ascii=False).encode()
                    content_type = "application/json; charset=utf-8"
                elif parsed.path == "/api/search":
                    params = parse_qs(parsed.query)
                    data = json.dumps(search(store, params.get("q", [""])[0], company_id=params.get("company", [None])[0]), ensure_ascii=False).encode()
                    content_type = "application/json; charset=utf-8"
                elif parsed.path == "/health":
                    data = b'{"status":"ok"}'
                    content_type = "application/json"
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src data:; base-uri 'none'; frame-ancestors 'none'")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            finally:
                store.close()

    print(f"AI Company Radar: http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
