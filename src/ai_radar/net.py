"""Bounded public-web access. No credentials, cookies, or browser execution."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.robotparser import RobotFileParser

AGENT = "AICompanyRadar/0.2 (+https://github.com/Chenxiao-Tian/Data_Collection)"


class FetchError(Exception):
    pass


def canonical_url(url: str) -> str:
    p = urlsplit(url)
    if p.scheme not in {"https", "http"} or not p.hostname or p.username or p.password:
        raise FetchError("Only credential-free HTTP(S) URLs are allowed")
    host = p.hostname.encode("idna").decode().lower().rstrip(".")
    if p.port not in {None, 80, 443}:
        raise FetchError("Nonstandard ports are not allowed")
    # Company pages do not need query arguments. API requests retain queries below.
    authority = f"[{host}]" if ":" in host else host
    if p.port:
        authority += f":{p.port}"
    return urlunsplit((p.scheme, authority, p.path or "/", p.query, ""))


def domain(url: str) -> str:
    host = urlsplit(canonical_url(url)).hostname or ""
    return host.removeprefix("www.")


def same_site(url: str, website: str) -> bool:
    host, root = domain(url), domain(website)
    return host == root or host.endswith("." + root)


def validate_public_url(url: str) -> str:
    url = canonical_url(url)
    host = urlsplit(url).hostname
    if host in {"localhost", "metadata.google.internal"} or host.endswith((".local", ".internal", ".localhost")):
        raise FetchError("Local destinations are blocked")
    try:
        addresses = {x[4][0] for x in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise FetchError("DNS lookup failed") from exc
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise FetchError("Non-public destinations are blocked")
    return url


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass
class Response:
    url: str
    text: str
    content_type: str
    sha256: str
    headers: dict


class Client:
    def __init__(self, timeout=15, delay=1.0, max_bytes=2_000_000):
        self.timeout, self.delay, self.max_bytes = timeout, delay, max_bytes
        self.opener = build_opener(NoRedirect())
        self.last = {}
        self.robots = {}

    def get(self, url: str, *, robots=False, headers=None, allowed_site=None) -> Response:
        for _ in range(6):
            url = validate_public_url(url)
            if allowed_site and not same_site(url, allowed_site):
                raise FetchError("Cross-domain redirect requires registry review")
            if robots and not self.allowed(url):
                raise FetchError("robots.txt disallows or cannot authorize this URL")
            host = domain(url)
            for attempt in range(3):
                time.sleep(max(0, self.delay - (time.monotonic() - self.last.get(host, 0))))
                self.last[host] = time.monotonic()
                try:
                    request = Request(url, headers={"User-Agent": AGENT, "Accept": "text/html,application/json,application/xml;q=0.9,*/*;q=0.5", **(headers or {})})
                    with self.opener.open(request, timeout=self.timeout) as response:
                        if int(response.headers.get("Content-Length", 0)) > self.max_bytes:
                            raise FetchError("Response exceeds size budget")
                        body = response.read(self.max_bytes + 1)
                        if len(body) > self.max_bytes:
                            raise FetchError("Response exceeds size budget")
                        encoding = response.headers.get_content_charset() or "utf-8"
                        try:
                            text = body.decode(encoding, errors="replace")
                        except LookupError:
                            text = body.decode("utf-8", errors="replace")
                        return Response(url, text, response.headers.get_content_type(), hashlib.sha256(body).hexdigest(), dict(response.headers))
                except HTTPError as exc:
                    if exc.code in {301, 302, 303, 307, 308}:
                        target = exc.headers.get("Location")
                        if not target:
                            raise FetchError("Redirect without location") from exc
                        new_url = urljoin(url, target)
                        if domain(new_url) != domain(url):
                            headers = None  # Never forward an API authorization header.
                        url = new_url
                        break
                    if exc.code in {429, 500, 502, 503, 504} and attempt < 2:
                        raw = exc.headers.get("Retry-After", "2")
                        pause = float(raw) if raw.isdigit() else 2 ** (attempt + 1)
                        time.sleep(min(pause, 10))
                        continue
                    raise FetchError(f"HTTP {exc.code}") from exc
                except (URLError, TimeoutError, OSError) as exc:
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                        continue
                    raise FetchError(type(exc).__name__) from exc
            else:
                raise FetchError("Retry limit exceeded")
        raise FetchError("Redirect limit exceeded")

    def allowed(self, url):
        p = urlsplit(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin not in self.robots:
            parser = RobotFileParser()
            try:
                response = self.get(origin + "/robots.txt", allowed_site=origin)
                # A login page / HTML response is not a successful robots policy.
                if "<html" in response.text[:500].lower():
                    self.robots[origin] = False
                else:
                    parser.parse(response.text.splitlines())
                    self.robots[origin] = parser
            except FetchError as exc:
                self.robots[origin] = str(exc) in {"HTTP 404", "HTTP 410"}
        rule = self.robots[origin]
        return rule if isinstance(rule, bool) else rule.can_fetch(AGENT, url)

    def json(self, url, params=None, headers=None):
        if params:
            url += ("&" if "?" in url else "?") + urlencode(params)
        response = self.get(url, headers=headers)
        try:
            return json.loads(response.text), response
        except ValueError as exc:
            raise FetchError("Invalid JSON response") from exc
