"""Web retrieval: URL fetching with SSRF protection, and pluggable search backends.

Search results are recorded as ``web_search_snippet`` sources (the snippet text only).
Agents are instructed to fetch a page before relying on it; a fetched page is a
``web`` source and its full extracted text is what citations are verified against.
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import urljoin, urlparse

import httpx
from pydantic import BaseModel

from adversi.errors import ConfigurationError, ToolError
from adversi.protocol.evidence import SourceType
from adversi.tools.base import SourceDraft, Tool, ToolOutput

USER_AGENT = "AdverSI/0.1 (+https://github.com/Yashjindal11/adversi)"
_ALLOWED_TYPES = ("text/html", "text/plain", "application/json", "application/xhtml+xml")


# -- HTML -> text -------------------------------------------------------------------


class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style", "noscript", "svg", "template", "head"}
    _BLOCK = {
        "p",
        "div",
        "br",
        "li",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "tr",
        "section",
        "article",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title: str | None = None
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title and self.title is None:
            self.title = data.strip() or None
        if not self._skip_depth:
            self.parts.append(data)


def html_to_text(html: str) -> tuple[str, str | None]:
    parser = _TextExtractor()
    parser.feed(html)
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if line), parser.title


# -- SSRF guard ---------------------------------------------------------------------


async def assert_public_url(url: str) -> None:
    """Reject non-http(s) URLs and hosts resolving to private/loopback/link-local ranges.

    Note: a DNS answer can change between this check and the connection (rebinding).
    Deployments exposed to untrusted users should also enforce egress rules at the
    network layer.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ToolError("only absolute http(s) URLs are allowed")
    host = parsed.hostname
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ToolError(f"could not resolve host {host}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise ToolError(f"refusing to fetch non-public address for host {host}")


async def fetch_text(
    url: str,
    *,
    max_bytes: int = 2_000_000,
    timeout_s: float = 20.0,
    allow_private: bool = False,
    max_redirects: int = 5,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[str, str | None, str]:
    """Return (text, title, final_url)."""
    async with httpx.AsyncClient(
        timeout=timeout_s,
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT},
        transport=transport,
    ) as client:
        for _ in range(max_redirects + 1):
            if not allow_private:
                await assert_public_url(url)
            async with client.stream("GET", url) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ToolError("redirect without location")
                    url = urljoin(url, location)
                    continue
                if not response.is_success:
                    raise ToolError(f"HTTP {response.status_code} for {url}")
                ctype = response.headers.get("content-type", "").split(";")[0].strip().lower()
                if ctype and not ctype.startswith(_ALLOWED_TYPES):
                    raise ToolError(f"unsupported content type {ctype}")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        break
                text = body[:max_bytes].decode(response.encoding or "utf-8", errors="replace")
                if ctype in ("text/html", "application/xhtml+xml") or text.lstrip().startswith("<"):
                    content, title = html_to_text(text)
                    return content, title, url
                return text, None, url
        raise ToolError("too many redirects")


def fetch_url_tool(*, allow_private: bool = False, max_chars: int = 30_000) -> Tool:
    async def fetch_url(url: str) -> ToolOutput:
        text, title, final_url = await fetch_text(url, allow_private=allow_private)
        text = text[:max_chars]
        return ToolOutput(
            content=f"{title or final_url}\n\n{text}",
            sources=[
                SourceDraft(content=text, source_type=SourceType.WEB, uri=final_url, title=title)
            ],
        )

    return Tool(
        "fetch_url",
        "Fetch a public web page and return its readable text. The page is recorded as a "
        "citable source; quote from it verbatim when citing.",
        fetch_url,
        timeout_s=30.0,
        max_output_chars=max_chars + 500,
    )


# -- search -------------------------------------------------------------------------


class SearchHit(BaseModel):
    title: str
    url: str
    snippet: str = ""


class SearchBackend(Protocol):
    name: str

    async def search(self, query: str, max_results: int) -> list[SearchHit]: ...


class BraveSearchBackend:
    """Brave Search API (https://api.search.brave.com). Requires BRAVE_API_KEY."""

    name = "brave"
    endpoint = "https://api.search.brave.com/res/v1/web/search"

    def __init__(
        self, api_key: str | None = None, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.api_key = api_key or os.environ.get("BRAVE_API_KEY")
        if not self.api_key:
            raise ConfigurationError("BraveSearchBackend requires BRAVE_API_KEY")
        self._transport = transport

    async def search(self, query: str, max_results: int) -> list[SearchHit]:
        async with httpx.AsyncClient(timeout=20, transport=self._transport) as client:
            response = await client.get(
                self.endpoint,
                params={"q": query, "count": max_results},
                headers={"X-Subscription-Token": self.api_key or "", "Accept": "application/json"},
            )
        if not response.is_success:
            raise ToolError(f"search failed with HTTP {response.status_code}")
        results = (response.json().get("web") or {}).get("results") or []
        return [
            SearchHit(
                title=r.get("title", ""), url=r.get("url", ""), snippet=r.get("description", "")
            )
            for r in results[:max_results]
        ]


class StaticSearchBackend:
    """Returns fixed hits. For tests, offline demos and reproducible experiments."""

    name = "static"

    def __init__(self, hits: dict[str, list[SearchHit]] | list[SearchHit]) -> None:
        self.hits = hits

    async def search(self, query: str, max_results: int) -> list[SearchHit]:
        if isinstance(self.hits, list):
            return self.hits[:max_results]
        return self.hits.get(query, [])[:max_results]


def web_search_tool(backend: SearchBackend, *, max_results: int = 5) -> Tool:
    async def web_search(query: str) -> ToolOutput:
        hits = await backend.search(query, max_results)
        if not hits:
            return ToolOutput(content="No results.")
        lines = []
        drafts = []
        for i, hit in enumerate(hits, 1):
            lines.append(f"{i}. {hit.title}\n   {hit.url}\n   {hit.snippet}")
            drafts.append(
                SourceDraft(
                    content=hit.snippet,
                    source_type=SourceType.WEB_SEARCH_SNIPPET,
                    uri=hit.url,
                    title=hit.title,
                )
            )
        return ToolOutput(content="\n".join(lines), sources=drafts)

    return Tool(
        "web_search",
        "Search the web. Returns titles, URLs and short snippets. Snippets are weak "
        "evidence; fetch the page with fetch_url before relying on it.",
        web_search,
        timeout_s=30.0,
    )
