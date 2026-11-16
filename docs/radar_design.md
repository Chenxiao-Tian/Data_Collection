# Architecture and operating boundaries

## Data flow

`config/companies.json` → bounded official-site crawler / domain-matched Wikidata enrichment → SQLite documents + claims + FTS5 → reciprocal-rank retrieval → local API / self-contained dashboard / CSV + JSON.

Discovery runs separately: Wikidata AI-industry companies → candidate queue → human verifies company identity and official domain → registry edit → collection. Discovery is automatic; promotion is deliberately reviewed. A persisted cursor rotates through ordered Wikidata result pages, resets on exhaustion, deduplicates candidates by source entity, and excludes already tracked website domains.

## Identity and evidence

Company IDs and approved website domains are unique. No fuzzy-name automatic merge. Only exact normalized website-domain matches can enrich from Wikidata; multiple domain matches are rejected. Cross-domain website redirects require review. Products and parent companies are not automatically merged.

Each current document has a stable ID derived from company ID and URL, content hash, source kind, publisher group, text, title, first_seen, changed_at, checked_at, optional published_at, and extracted claims. Claim status is determined from the current source set. Past changes retain old/new claim payloads and hashes (last 10,000 events); the database does not retain every historic full HTML response. Current normalized text is capped at 60,000 characters per page; exported source previews and quotes are capped at 280 characters each. Static exports are not a full-text index.

`single_source` is not verified. Repeated official pages have one publisher group. Wikidata is conservatively placed in that same group because it can cite the company's own material. Only deliberately supplied independent publisher groups can yield `corroborated`. The built-in collector does not manufacture independence. Different self-descriptions are page-specific marketing copy, not automatically conflicts. Other differing string values are marked conflict. Compatible date precision (2023 vs 2023-04 vs 2023-04-28) is retained without a false conflict. Homepage descriptions and article/page descriptions are separate fields.

## Retrieval

1. Quote and bind user terms to SQLite FTS5 MATCH; BM25 weights company names and page titles.
2. Lexical matching adds multilingual aliases and a small explicit Chinese/English research vocabulary.
3. Merge ranked lists with RRF, `sum(1/(60+rank))`.
4. Optional local sentence-transformers adds a normalized-vector ranking, cached by document hash and model ID. Dense candidates below cosine 0.35 are dropped. This heuristic is not a calibrated confidence threshold.
5. Results are literal source snippets with citations and timestamps. No generated factual answers. Empty retrieval means insufficient evidence, not absence of the business or activity.

No learned cross-encoder, hosted embeddings, general-purpose Chinese-to-English translation, financial inference, or universal web search is enabled. The optional dense mode represents the first 3,000 source characters and has not been benchmarked on an independently labeled corpus. An enterprise deployment should add licensed data, an evaluated corpus, page-level chunking, reviewed corroboration sources, and authenticated deployment after measuring the actual gaps.

## Network / security

Public HTTP(S) only, no credential URLs or nonstandard ports; IP/DNS checks reject non-global destinations before every request and redirect. Redirects are bounded and authorization headers stripped on host changes. Source pages respect robots policies, have a per-host delay, retry/time/size budgets, and never execute JavaScript or shell instructions. Failed or ambiguous robots policies fail closed. Dynamic/challenge/login pages can be unavailable.

The standard-library resolver validation is not DNS-pinned at the transport layer; a hostile DNS rebinding race is a residual limitation. Keep the registry trusted, the service loopback-only, and use egress restrictions for an untrusted multi-user deployment. Do not expose this development HTTP server directly to the internet.

HTML is embedded using JSON escapes; UI strings use textContent. CSV export escapes formula-leading characters. The HTTP server exposes only known read-only routes, not files or arbitrary URL fetching. No secrets are required by the new collector. The workflow GITHUB_TOKEN is used only for repository artifact retrieval and data-branch publication.

## Persistence / scheduling

GitHub Actions restores the last nonexpired database artifact, collects sequentially with bounded page counts, exports summaries even on partial failure, uploads the new database, and updates a dedicated `ai-radar-data` branch without force-push. Concurrent collectors are serialized. Source code remains on main. Reports and snapshots explicitly expose failures. If artifact retrieval fails, the run fails rather than silently resetting state. Report commit failure does not erase the already uploaded database artifact.

Artifact retention is 90 days; the export branch has ordinary Git history. There is no claim of 24/7 exact-time SLA. GitHub can delay scheduled jobs or disable inactive public-repository schedules.

## Official references

- [GitHub scheduled events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [Wikidata data access](https://www.wikidata.org/wiki/Wikidata:Data_access)
- [Wikibase API and claim qualifiers](https://www.mediawiki.org/wiki/Wikibase/API)
- [SQLite FTS5](https://www.sqlite.org/fts5.html)
