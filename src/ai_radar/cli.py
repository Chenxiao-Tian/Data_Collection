from __future__ import annotations
import argparse
import json
from pathlib import Path
from .collect import registry, run
from .store import Store
from .search import search


def main():
    parser = argparse.ArgumentParser(description="AI Company Radar — evidence-first company retrieval")
    parser.add_argument("--db", default="data/radar.sqlite")
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("collect")
    collect.add_argument("--registry", default="config/companies.json")
    collect.add_argument("--max-pages", type=int, default=3)
    collect.add_argument("--no-discover", action="store_true")
    collect.add_argument("--limit", type=int, default=0, help="Diagnostic subset; remaining companies stay registered")
    find = commands.add_parser("search")
    find.add_argument("query")
    find.add_argument("--company")
    find.add_argument("--limit", type=int, default=20)
    find.add_argument("--semantic-model", help="Optional local sentence-transformers model ID (downloads weights)")
    export = commands.add_parser("export")
    export.add_argument("--out", default="radar-output")
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8080)
    commands.add_parser("status")
    args = parser.parse_args()
    store = Store(args.db)
    try:
        if args.command == "collect":
            companies = registry(args.registry)
            if args.limit > 0:
                # A diagnostic run is explicitly scoped; register full inventory again afterwards.
                result = run(store, companies[:args.limit], max_pages=args.max_pages, discover_new=not args.no_discover)
                store.register(companies)
            else:
                result = run(store, companies, max_pages=args.max_pages, discover_new=not args.no_discover)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if result["status"] == "failed":
                raise SystemExit(2)
        elif args.command == "search":
            print(json.dumps(search(store, args.query, company_id=args.company, limit=args.limit, semantic_model=args.semantic_model), ensure_ascii=False, indent=2))
        elif args.command == "export":
            from .web import export_snapshot
            export_snapshot(store.snapshot(), Path(args.out))
            print(str(Path(args.out).resolve() / "index.html"))
        elif args.command == "status":
            s = store.snapshot()
            print(json.dumps({"companies": len(s["companies"]), "sources": sum(len(c["sources"]) for c in s["companies"]), "runs": s["runs"]}, ensure_ascii=False, indent=2))
        elif args.command == "serve":
            from .web import serve
            store.close()
            store = None
            serve(args.db, args.port)
    finally:
        if store:
            store.close()


if __name__ == "__main__":
    main()
