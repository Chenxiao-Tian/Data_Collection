"""Conservative HTML extraction; unsupported fields stay absent."""
from __future__ import annotations
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit
from .net import canonical_url, same_site


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.in_title = False
        self.in_ld = False
        self.ld_parts = []
        self.ld = []
        self.parts = []
        self.title_parts = []
        self.meta = {}
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip += 1
        if tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self.in_ld = True
            self.ld_parts = []
        if tag == "title":
            self.in_title = True
        if tag == "meta":
            self.meta[(attrs.get("property") or attrs.get("name") or "").lower()] = clean(attrs.get("content"))
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag in {"p", "div", "h1", "h2", "h3", "li", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "script" and self.in_ld:
            self.ld.append("".join(self.ld_parts))
            self.in_ld = False
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip = max(0, self.skip - 1)
        if tag == "title":
            self.in_title = False

    def handle_data(self, text):
        if self.in_ld:
            self.ld_parts.append(text)
        if self.in_title:
            self.title_parts.append(text)
        if not self.skip:
            self.parts.append(text + " ")


def objects(value):
    if isinstance(value, list):
        for x in value:
            yield from objects(x)
    elif isinstance(value, dict):
        yield value
        if "@graph" in value:
            yield from objects(value["@graph"])


def extract_page(html, url, company):
    parser = PageParser()
    parser.feed(html)
    title = clean(" ".join(parser.title_parts))[:400]
    description = parser.meta.get("description") or parser.meta.get("og:description")
    claims = []
    # Marketing copy is attributed as self-description, never treated as objective performance.
    if description:
        claims.append({"field": "self_description", "value": description[:1200], "quote": description[:1200], "method": "html_meta"})
    for raw in parser.ld:
        try:
            nodes = objects(json.loads(raw))
            for obj in nodes:
                types = obj.get("@type", [])
                types = [types] if isinstance(types, str) else types
                if not set(types or []).intersection({"Organization", "Corporation"}):
                    continue
                subject_url = obj.get("url")
                if not isinstance(subject_url, str):
                    continue
                try:
                    if not same_site(subject_url, company["website"]):
                        continue
                except Exception:
                    continue
                for key, field in [("legalName", "legal_name"), ("foundingDate", "founded_date")]:
                    value = obj.get(key)
                    if isinstance(value, str) and 0 < len(value) < 400:
                        claims.append({"field": field, "value": clean(value), "quote": clean(value), "method": f"jsonld:{key}"})
        except (ValueError, TypeError):
            continue
    lines = [clean(x) for x in "".join(parser.parts).splitlines()]
    text = "\n".join(dict.fromkeys(x for x in lines if len(x) > 25))
    text = (title + "\n" + (description or "") + "\n" + text)[:60_000]
    # Block / consent / JS shells are not evidence of the company.
    blocked = re.search(r"just a moment|access denied|verify you are human|attention required", title, re.I)
    if blocked or len(text.strip()) < 100:
        raise ValueError("Page has insufficient content or is a challenge page")
    links = []
    for href in parser.links:
        try:
            target = canonical_url(urljoin(url, href))
            p = urlsplit(target)
            target = urlunsplit((p.scheme, p.netloc, p.path, "", ""))
            if same_site(target, company["website"]) and re.search(r"/(about|company|news|blog|research|careers|jobs)(/|$|-)", p.path, re.I):
                links.append(target)
        except Exception:
            pass
    return {"title": title, "text": text, "claims": claims, "links": list(dict.fromkeys(links)), "published_at": parser.meta.get("article:published_time") or None}
