"""Official-source research bridge; no unrestricted browsing or memory store.

Search is an injected tool callback. All proposed URLs are validated before a
bounded, redirect-free fetch. Unavailable evidence is reported as unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from html.parser import HTMLParser
from itertools import islice
from typing import Callable, Iterable
from urllib.parse import urlparse
from urllib.request import build_opener, HTTPRedirectHandler, Request

from .controller import DocFinding


ALLOWED_DOC_HOSTS = frozenset({
    "docs.python.org", "developer.mozilla.org", "nodejs.org", "react.dev",
    "expressjs.com", "docs.docker.com", "www.sqlite.org", "sqlite.org",
    "www.typescriptlang.org", "developer.chrome.com",
})


@dataclass(frozen=True)
class SearchHit:
    url: str
    title: str = ""


def allowed_url(url: str, allow_hosts: frozenset[str] = ALLOWED_DOC_HOSTS) -> bool:
    try:
        parsed = urlparse(url)
        return (parsed.scheme == "https" and parsed.hostname in allow_hosts
                and parsed.port in (None, 443) and not parsed.username
                and not parsed.password and not parsed.fragment)
    except ValueError:
        return False


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_official_page(url: str, max_bytes: int = 60_000) -> str:
    """Fetch only validated HTTPS docs; follow no redirects or off-site links."""
    if not allowed_url(url):
        raise ValueError("Blocked non-official documentation URL")
    opener = build_opener(_NoRedirect())
    request = Request(url, headers={"User-Agent": "Qwen-Research-Harness/0.1"})
    with opener.open(request, timeout=7) as response:
        content_type = response.headers.get("Content-Type", "").lower()
        if not ("text/html" in content_type or "text/plain" in content_type):
            raise ValueError("Expected text/html or text/plain documentation")
        raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError("Documentation exceeded the download budget")
    return raw.decode("utf-8", "replace")


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ignored = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self.ignored += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self.ignored:
            self.ignored -= 1

    def handle_data(self, data):
        if not self.ignored and data.strip():
            self.parts.append(data.strip())


class OfficialDocsResearch:
    """Search a trusted index, then fetch and cite the first usable official page."""

    def __init__(self, search: Callable[[str], Iterable[SearchHit]],
                 fetch: Callable[[str], str] = fetch_official_page):
        self.search = search
        self.fetch = fetch

    def lookup(self, query: str) -> DocFinding | None:
        # Search results are untrusted: source validation precedes fetch.
        for hit in islice(self.search(query), 5):
            if not allowed_url(hit.url):
                continue
            try:
                raw = self.fetch(hit.url)
            except (OSError, ValueError, TimeoutError):
                continue
            plain = _PlainText()
            plain.feed(raw[:60_000])
            excerpt = " ".join(plain.parts)[:1400]
            if len(excerpt) < 30:
                continue
            return DocFinding(query=query, source_url=hit.url,
                              excerpt=excerpt, content_sha256=sha256(raw.encode("utf-8")).hexdigest())
        return None
