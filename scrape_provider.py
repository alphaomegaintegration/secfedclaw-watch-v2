#!/usr/bin/env python3
"""ScrapeGraphAI-primary scrape/search provider for SECFEDCLAW v0.2.

Primary provider: the open-source ``scrapegraphai`` library
(https://github.com/ScrapeGraphAI/Scrapegraph-ai) driving Playwright/Chromium
and an OpenRouter LLM. Fallback provider: Firecrawl's hosted ``/v1/scrape`` API.
If neither answers, ``scrape`` / ``search`` return ``None`` and the caller
degrades to cached custody replay, exactly as before.

Two surfaces:

* ``scrape(url)`` — render a page and return its **markdown** text. This is the
  true Firecrawl-equivalent: it uses scrapegraphai's ``ChromiumLoader`` to
  render JS, then ``html2text`` to produce markdown. No LLM cost, and tables /
  numbers / usernames survive verbatim for the downstream markdown parsers
  (e.g. ``scoring_v2._parse_openinsider``).
* ``search(query)`` — LLM web search across the open web *and* social media
  (including X/Twitter) via scrapegraphai's ``SearchGraph``. Resilient to X's
  auth wall and dead Nitter mirrors because it searches indexed content rather
  than scraping X directly.

The heavy dependencies (``scrapegraphai`` + Playwright + Chromium) are imported
lazily inside each leg. If they are not installed, or a browser fails to launch,
the provider transparently skips to Firecrawl — the scan never hard-fails on the
optional dependency. No secret values are logged; source URLs are redacted.
"""
from __future__ import annotations

import importlib.util
import json
import re
import threading
import urllib.request
from dataclasses import dataclass
from typing import Any

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-4o-mini"
DEFAULT_MAX_TOKENS = 2048
DEFAULT_MAX_BROWSERS = 2
DEFAULT_ORDER = ("scrapegraphai", "firecrawl")
_MIN_CONTENT = 50  # markdown shorter than this is treated as "no real content"

# Module-global cap on concurrent Chromium instances. The scan runs tickers in
# a thread pool (``--workers``); without this a wide run would launch one
# browser per worker. Created once, sized by the first provider instance.
_browser_sem: threading.Semaphore | None = None
_browser_sem_lock = threading.Lock()


def _browser_semaphore(max_browsers: int) -> threading.Semaphore:
    global _browser_sem
    with _browser_sem_lock:
        if _browser_sem is None:
            _browser_sem = threading.Semaphore(max(1, max_browsers))
        return _browser_sem


def _scrapegraphai_installed() -> bool:
    try:
        return importlib.util.find_spec("scrapegraphai") is not None
    except Exception:
        return False


def redact(url: str) -> str:
    return re.sub(r"(apiKey|api_key|token|key)=[^&\s]+", r"\1=<redacted>", url, flags=re.I)


@dataclass
class ScrapeResult:
    """Outcome of a scrape/search, tagged with which provider answered."""
    markdown: str
    data: Any
    source: str
    provider: str  # "scrapegraphai" | "firecrawl"


class ScrapeProvider:
    """Tries providers in ``order`` (default: scrapegraphai then firecrawl)."""

    def __init__(self, env: dict[str, str] | None = None, timeout: int = 12,
                 max_browsers: int | None = None, order: tuple[str, ...] | None = None):
        self.env = env or {}
        self.timeout = timeout
        self.model = self.env.get("SGAI_MODEL") or DEFAULT_MODEL
        self.max_browsers = int(self.env.get("SGAI_MAX_BROWSERS") or max_browsers
                                or DEFAULT_MAX_BROWSERS)
        order_str = self.env.get("SCRAPE_PROVIDER_ORDER")
        self.order = (tuple(o.strip() for o in order_str.split(",") if o.strip())
                      if order_str else (order or DEFAULT_ORDER))

    # ---- public surface --------------------------------------------------
    def scrape(self, url: str, prompt: str | None = None) -> ScrapeResult | None:
        for prov in self.order:
            r = (self._sgai_scrape(url) if prov == "scrapegraphai"
                 else self._firecrawl_scrape(url) if prov == "firecrawl" else None)
            if r is not None:
                return r
        return None

    def search(self, query: str, prompt: str | None = None) -> ScrapeResult | None:
        for prov in self.order:
            r = (self._sgai_search(query, prompt) if prov == "scrapegraphai"
                 else self._firecrawl_search(query) if prov == "firecrawl" else None)
            if r is not None:
                return r
        return None

    # ---- scrapegraphai (primary) ----------------------------------------
    def _llm_config(self) -> dict[str, Any]:
        # Cap output tokens: scrapegraphai defaults to 16384, which is wasteful
        # and overflows small OpenRouter budgets. Configurable via SGAI_MAX_TOKENS.
        max_tokens = int(self.env.get("SGAI_MAX_TOKENS") or DEFAULT_MAX_TOKENS)
        return {"llm": {"model": self.model,
                        "api_key": self.env.get("OPENROUTER_API_KEY", ""),
                        "base_url": OPENROUTER_BASE,
                        "max_tokens": max_tokens},
                "headless": True, "verbose": False}

    def _sgai_scrape(self, url: str) -> ScrapeResult | None:
        if not _scrapegraphai_installed():
            return None
        sem = _browser_semaphore(self.max_browsers)
        sem.acquire()
        try:
            from scrapegraphai.docloaders import ChromiumLoader
            import html2text
            docs = ChromiumLoader([url], backend="playwright", headless=True,
                                  timeout=self.timeout).load()
            html = docs[0].page_content if docs else ""
            if not html:
                return None
            conv = html2text.HTML2Text()
            conv.ignore_links = False
            conv.body_width = 0
            md = conv.handle(html).strip()
            if len(md) < _MIN_CONTENT:
                return None
            return ScrapeResult(markdown=md,
                                data={"markdown": md, "url": url, "provider": "scrapegraphai"},
                                source=redact(url), provider="scrapegraphai")
        except Exception:
            return None
        finally:
            sem.release()

    def _sgai_search(self, query: str, prompt: str | None = None) -> ScrapeResult | None:
        if not _scrapegraphai_installed() or not self.env.get("OPENROUTER_API_KEY"):
            return None
        sem = _browser_semaphore(self.max_browsers)
        sem.acquire()
        try:
            from scrapegraphai.graphs import SearchGraph
            ask = prompt or (
                f"Find recent public posts and discussion about {query} across "
                "X/Twitter, Reddit, StockTwits and stock forums from the past week. "
                "Return a JSON list named 'posts'; each item has: text, platform, "
                "author, url.")
            graph = SearchGraph(prompt=ask, config={**self._llm_config(), "max_results": 5})
            out = graph.run()
            md = out if isinstance(out, str) else json.dumps(out, default=str)
            if not md or len(md) < 20:
                return None
            return ScrapeResult(markdown=md, data=out,
                                source="scrapegraphai:search", provider="scrapegraphai")
        except Exception:
            return None
        finally:
            sem.release()

    # ---- firecrawl (fallback) -------------------------------------------
    def _firecrawl_scrape(self, url: str) -> ScrapeResult | None:
        key = self.env.get("FIRECRAWL_API_KEY")
        if not key:
            return None
        try:
            body = json.dumps({"url": url, "formats": ["markdown"], "waitFor": 3000}).encode()
            req = urllib.request.Request(
                "https://api.firecrawl.dev/v1/scrape", data=body,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                         "User-Agent": "secfedclaw-watch/2.0"})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read())
            if data.get("success"):
                md = (data.get("data") or {}).get("markdown", "")
                if len(md) >= _MIN_CONTENT:
                    return ScrapeResult(markdown=md, data=data,
                                        source=redact("https://api.firecrawl.dev/v1/scrape"),
                                        provider="firecrawl")
        except Exception:
            return None
        return None

    def _firecrawl_search(self, query: str) -> ScrapeResult | None:
        key = self.env.get("FIRECRAWL_API_KEY")
        if not key:
            return None
        try:
            body = json.dumps({"query": query, "limit": 5}).encode()
            req = urllib.request.Request(
                "https://api.firecrawl.dev/v1/search", data=body,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read())
            if data.get("success"):
                return ScrapeResult(markdown=json.dumps(data.get("data") or data, default=str),
                                    data=data,
                                    source=redact("https://api.firecrawl.dev/v1/search"),
                                    provider="firecrawl")
        except Exception:
            return None
        return None


def coerce_search_to_posts(data: Any, platform: str = "x") -> list[dict[str, Any]]:
    """Best-effort: turn a SearchGraph result into normalize_posts-shaped items.

    SearchGraph output is LLM-shaped and varies; we look for a list of dicts
    carrying 'text' (under common keys) and map them to the post schema the
    social scorer expects. Returns [] when nothing usable is found (the caller
    then keeps the raw payload purely as custody)."""
    items: list[Any] = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for k in ("posts", "results", "items", "data", "content"):
            v = data.get(k)
            if isinstance(v, list):
                items = v
                break
    posts: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        text = it.get("text") or it.get("content") or it.get("snippet") or it.get("title")
        if not text:
            continue
        posts.append({
            "platform": it.get("platform") or platform,
            "id": str(it.get("id") or it.get("url") or text[:40]),
            "text": str(text),
            "created_at": it.get("created_at") or it.get("date"),
            "author_id": str(it.get("author") or it.get("author_id") or ""),
            "sentiment": None,
            "engagement": float(it.get("engagement") or 0) if str(it.get("engagement") or "").replace(".", "", 1).isdigit() else 0.0,
        })
    return posts
