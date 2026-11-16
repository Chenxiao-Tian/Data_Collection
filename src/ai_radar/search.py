"""BM25 + lexical fusion; optional local multilingual dense retrieval."""
from __future__ import annotations
import json
import math
import re
from datetime import datetime, timezone

EXPANSIONS = {
    "融资": "funding raised investment", "估值": "valuation", "创始人": "founder founded",
    "招聘": "careers hiring jobs", "开源": "open source", "推理": "inference reasoning",
    "视频": "video", "语音": "voice speech audio", "芯片": "chip hardware processor",
    "医疗": "healthcare medical", "机器人": "robotics robot", "大模型": "language model llm",
    "智能体": "agent", "编程": "coding developer", "安全": "safety security",
    "搜索": "search retrieval", "企业": "enterprise", "成立": "founded foundation",
}


def expand(query):
    return query + " " + " ".join(v for k, v in EXPANSIONS.items() if k in query)


def tokens(query):
    return list(dict.fromkeys(re.findall(r"[\w-]+", expand(query).lower(), re.UNICODE)))[:32]


def snippet(text, terms, width=320):
    lower = text.lower()
    positions = [lower.find(t) for t in terms if lower.find(t) >= 0]
    pos = max(0, min(positions, default=0) - 70)
    return ("…" if pos else "") + text[pos:pos + width].replace("\n", " ") + ("…" if len(text) > pos + width else "")


def search(store, query, *, limit=20, company_id=None, semantic_model=None):
    query = query.strip()[:500]
    terms = tokens(query)
    if not terms:
        return {"query": query, "mode": "bm25+lexical-rrf", "results": [], "message": "请输入检索词。"}
    docs = [dict(d) for d in store.db.execute("SELECT d.*,c.name,c.aliases FROM documents d JOIN companies c ON c.id=d.company_id WHERE c.active=1" + (" AND c.id=?" if company_id else ""), (company_id,) if company_id else ())]
    by_id = {d["id"]: d for d in docs}
    ranks = []
    match = " OR ".join('"' + t.replace('"', '""') + '"' for t in terms)
    # All FTS input is quoted and bound; no raw MATCH/SQL interpolation.
    rows = store.db.execute("SELECT document_id,bm25(evidence_fts,0,5,3,1) AS relevance FROM evidence_fts WHERE evidence_fts MATCH ? ORDER BY relevance LIMIT 200", (match,)).fetchall()
    ranks.append([r["document_id"] for r in rows if r["document_id"] in by_id])
    lexical = []
    for d in docs:
        title = (d["name"] + " " + d["aliases"] + " " + d["title"]).lower()
        body = d["text"].lower()
        score = sum(3 * (t in title) + (t in body) for t in terms)
        if score:
            lexical.append((d["id"], score))
    ranks.append([k for k, _ in sorted(lexical, key=lambda x: (-x[1], x[0]))[:200]])
    mode = "bm25+lexical-rrf"
    if semantic_model:
        ranks.append(dense_rank(store, docs, query, semantic_model))
        mode += "+multilingual-dense"
    scores = {}
    for rank in ranks:
        for i, key in enumerate(rank):
            scores[key] = scores.get(key, 0) + 1 / (60 + i + 1)
    results = []
    for key, score in sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:max(1, min(limit, 100))]:
        d = by_id[key]
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(d["checked_at"])).total_seconds() / 86400
        results.append({"document_id": key, "company_id": d["company_id"], "company": d["name"], "title": d["title"], "url": d["url"], "snippet": snippet(d["text"], terms), "source_kind": d["kind"], "checked_at": d["checked_at"], "published_at": d["published_at"], "stale": age > 30, "retrieval_score": round(score, 5)})
    return {"query": query, "mode": mode, "results": results,
            "message": "以下为原文检索结果，排序分数不是事实置信度。" if results else "没有找到支持性证据；不能据此判断公司不存在或没有相关业务。"}


_MODELS = {}


def dense_rank(store, docs, query, model_name):
    # Optional install; no credentials and no hosted inference. Explicit CLI opt-in downloads weights.
    from sentence_transformers import SentenceTransformer
    if model_name not in _MODELS:
        _MODELS[model_name] = SentenceTransformer(model_name, trust_remote_code=False)
    model = _MODELS[model_name]
    query_vector = model.encode(query, normalize_embeddings=True).tolist()
    scores = []
    for d in docs:
        cached = store.db.execute("SELECT vector FROM vectors WHERE document_id=? AND content_hash=? AND model=?", (d["id"], d["content_hash"], model_name)).fetchone()
        if cached:
            vector = json.loads(cached["vector"])
        else:
            # Represent the source's lead, not an invented company summary.
            vector = model.encode(d["name"] + "\n" + d["title"] + "\n" + d["text"][:3000], normalize_embeddings=True).tolist()
            with store.db:
                store.db.execute("INSERT OR REPLACE INTO vectors VALUES(?,?,?,?)", (d["id"], d["content_hash"], model_name, json.dumps(vector)))
        similarity = sum(a * b for a, b in zip(query_vector, vector))
        if similarity >= 0.35:
            scores.append((d["id"], similarity))
    return [k for k, _ in sorted(scores, key=lambda x: (-x[1], x[0]))[:100]]
