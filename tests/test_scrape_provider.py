"""Tests for the ScrapeGraphAI-primary scrape/search provider.

Hermetic: never requires the real scrapegraphai/Playwright stack. The SGAI legs
are exercised by injecting fake `scrapegraphai.*` + `html2text` modules into
sys.modules; the Firecrawl fallback is exercised by stubbing urlopen. So these
pass on the stdlib-only CI interpreter exactly as on the dev venv.
"""
import io
import json
import sys
import types
import contextlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scrape_provider as sp
from scrape_provider import ScrapeProvider, ScrapeResult, coerce_search_to_posts


# ---- fake-module helpers --------------------------------------------------

@contextlib.contextmanager
def fake_sgai(html=None, search_out=None):
    """Inject fake scrapegraphai docloaders/graphs + html2text into sys.modules."""
    saved = {k: sys.modules.get(k) for k in
             ("scrapegraphai", "scrapegraphai.docloaders", "scrapegraphai.graphs", "html2text")}

    class _Doc:
        def __init__(self, content): self.page_content = content

    class FakeChromiumLoader:
        def __init__(self, urls, **kw): self.urls = urls
        def load(self): return [_Doc(html)] if html is not None else []

    class FakeSearchGraph:
        def __init__(self, prompt=None, config=None, schema=None): pass
        def run(self): return search_out

    class FakeHTML2Text:
        def __init__(self): self.ignore_links = True; self.body_width = 79
        def handle(self, h): return "MD:" + h  # deterministic, marks the SGAI path

    pkg = types.ModuleType("scrapegraphai")
    docl = types.ModuleType("scrapegraphai.docloaders"); docl.ChromiumLoader = FakeChromiumLoader
    graphs = types.ModuleType("scrapegraphai.graphs"); graphs.SearchGraph = FakeSearchGraph
    h2t = types.ModuleType("html2text"); h2t.HTML2Text = FakeHTML2Text
    pkg.docloaders = docl; pkg.graphs = graphs
    sys.modules.update({"scrapegraphai": pkg, "scrapegraphai.docloaders": docl,
                        "scrapegraphai.graphs": graphs, "html2text": h2t})
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


class _Resp:
    def __init__(self, payload, status=200):
        self._b = json.dumps(payload).encode(); self.status = status
    def read(self): return self._b
    def __enter__(self): return self
    def __exit__(self, *a): return False


def stub_firecrawl(monkeypatch, payload, record=None):
    def fake_urlopen(req, timeout=None):
        if record is not None:
            record.append(req.full_url)
        return _Resp(payload)
    monkeypatch.setattr(sp.urllib.request, "urlopen", fake_urlopen)


# ---- coerce_search_to_posts ----------------------------------------------

def test_coerce_from_posts_key():
    data = {"posts": [{"text": "to the moon $AMC", "platform": "x", "author": "u1", "url": "http://x/1"}]}
    posts = coerce_search_to_posts(data, platform="x")
    assert len(posts) == 1
    p = posts[0]
    assert p["platform"] == "x" and p["text"] == "to the moon $AMC" and p["author_id"] == "u1"
    assert p["sentiment"] is None and p["engagement"] == 0.0

def test_coerce_from_bare_list_and_alt_keys():
    data = [{"snippet": "hype", "url": "http://r/1"}, {"nope": 1}]
    posts = coerce_search_to_posts(data, platform="web")
    assert len(posts) == 1 and posts[0]["platform"] == "web" and posts[0]["text"] == "hype"

def test_coerce_empty_for_unusable():
    assert coerce_search_to_posts({"summary": "no list here"}) == []
    assert coerce_search_to_posts(None) == []
    assert coerce_search_to_posts("a string") == []


# ---- scrape(): provider order + fallback ---------------------------------

def test_scrape_sgai_primary_used_first(monkeypatch):
    called = []
    monkeypatch.setattr(sp, "_scrapegraphai_installed", lambda: True)
    stub_firecrawl(monkeypatch, {"success": True, "data": {"markdown": "x" * 80}}, record=called)
    with fake_sgai(html="<p>" + "hello world " * 10 + "</p>"):
        prov = ScrapeProvider(env={"FIRECRAWL_API_KEY": "k"})
        res = prov.scrape("http://openinsider.com/search?q=AMC")
    assert res is not None and res.provider == "scrapegraphai"
    assert res.markdown.startswith("MD:")
    assert called == []  # firecrawl never touched when sgai succeeds

def test_scrape_falls_back_to_firecrawl_when_sgai_absent(monkeypatch):
    monkeypatch.setattr(sp, "_scrapegraphai_installed", lambda: False)
    stub_firecrawl(monkeypatch, {"success": True, "data": {"markdown": "y" * 120}})
    prov = ScrapeProvider(env={"FIRECRAWL_API_KEY": "k"})
    res = prov.scrape("http://example.com")
    assert res is not None and res.provider == "firecrawl" and len(res.markdown) == 120

def test_scrape_returns_none_when_both_unavailable(monkeypatch):
    monkeypatch.setattr(sp, "_scrapegraphai_installed", lambda: False)
    prov = ScrapeProvider(env={})  # no firecrawl key either
    assert prov.scrape("http://example.com") is None

def test_scrape_order_override_firecrawl_first(monkeypatch):
    monkeypatch.setattr(sp, "_scrapegraphai_installed", lambda: True)
    stub_firecrawl(monkeypatch, {"success": True, "data": {"markdown": "z" * 90}})
    with fake_sgai(html="<p>" + "content " * 30 + "</p>"):
        prov = ScrapeProvider(env={"FIRECRAWL_API_KEY": "k",
                                   "SCRAPE_PROVIDER_ORDER": "firecrawl,scrapegraphai"})
        res = prov.scrape("http://example.com")
    assert res.provider == "firecrawl"

def test_scrape_skips_trivial_sgai_then_firecrawl(monkeypatch):
    # SGAI returns too-short content -> provider rejects it and falls through
    monkeypatch.setattr(sp, "_scrapegraphai_installed", lambda: True)
    stub_firecrawl(monkeypatch, {"success": True, "data": {"markdown": "F" * 100}})
    with fake_sgai(html="<p>hi</p>"):  # html2text -> "MD:<p>hi</p>" < 50 chars
        prov = ScrapeProvider(env={"FIRECRAWL_API_KEY": "k"})
        res = prov.scrape("http://example.com")
    assert res.provider == "firecrawl"


# ---- search(): SearchGraph primary + firecrawl fallback ------------------

def test_search_sgai_primary(monkeypatch):
    monkeypatch.setattr(sp, "_scrapegraphai_installed", lambda: True)
    out = {"posts": [{"text": "$AMC squeeze", "platform": "x"}]}
    with fake_sgai(search_out=out):
        prov = ScrapeProvider(env={"OPENROUTER_API_KEY": "k"})
        res = prov.search("$AMC stock")
    assert res is not None and res.provider == "scrapegraphai"
    assert coerce_search_to_posts(res.data, "x")[0]["text"] == "$AMC squeeze"

def test_search_falls_back_to_firecrawl(monkeypatch):
    monkeypatch.setattr(sp, "_scrapegraphai_installed", lambda: False)
    stub_firecrawl(monkeypatch, {"success": True, "data": [{"title": "t", "url": "u"}]})
    prov = ScrapeProvider(env={"FIRECRAWL_API_KEY": "k", "OPENROUTER_API_KEY": "k"})
    res = prov.search("$AMC")
    assert res is not None and res.provider == "firecrawl"

def test_search_openai_model_without_key_skips_sgai(monkeypatch):
    # A hosted (openai/openrouter) model with no key skips SGAI search.
    monkeypatch.setattr(sp, "_scrapegraphai_installed", lambda: True)
    with fake_sgai(search_out={"posts": [{"text": "x"}]}):
        prov = ScrapeProvider(env={"SGAI_MODEL": "openai/gpt-4o-mini"})  # no key, no firecrawl
        assert prov.search("$AMC") is None

def test_search_local_ollama_needs_no_key(monkeypatch):
    # Default model is ollama/* -> search runs locally with no API key at all.
    monkeypatch.setattr(sp, "_scrapegraphai_installed", lambda: True)
    with fake_sgai(search_out={"posts": [{"text": "y"}]}):
        prov = ScrapeProvider(env={})  # no OPENROUTER key, no firecrawl
        res = prov.search("$AMC")
    assert res is not None and res.provider == "scrapegraphai"

def test_llm_config_local_vs_hosted():
    local = ScrapeProvider(env={})._llm_config()["llm"]  # default ollama
    assert local["model"].startswith("ollama/") and "api_key" not in local
    assert "localhost" in local["base_url"]
    hosted = ScrapeProvider(env={"SGAI_MODEL": "openai/gpt-4o-mini",
                                 "OPENROUTER_API_KEY": "k"})._llm_config()["llm"]
    assert hosted["api_key"] == "k" and "openrouter" in hosted["base_url"]


# ---- config plumbing ------------------------------------------------------

def test_env_config_defaults_and_overrides():
    p = ScrapeProvider(env={})
    assert p.model == sp.DEFAULT_MODEL and p.order == sp.DEFAULT_ORDER
    p2 = ScrapeProvider(env={"SGAI_MODEL": "openai/gpt-5", "SCRAPE_PROVIDER_ORDER": "firecrawl"})
    assert p2.model == "openai/gpt-5" and p2.order == ("firecrawl",)


# ---- connector wiring: methods route through self.scraper ----------------

class _FakeScraper:
    def __init__(self, scrape_md=None, search_data=None):
        self.scrape_md = scrape_md; self.search_data = search_data
        self.scrape_calls = []; self.search_calls = []
    def scrape(self, url, prompt=None):
        self.scrape_calls.append(url)
        if self.scrape_md is None: return None
        return ScrapeResult(markdown=self.scrape_md,
                            data={"markdown": self.scrape_md, "url": url, "provider": "scrapegraphai"},
                            source=url, provider="scrapegraphai")
    def search(self, query, prompt=None):
        self.search_calls.append(query)
        if self.search_data is None: return None
        return ScrapeResult(markdown=json.dumps(self.search_data), data=self.search_data,
                            source="scrapegraphai:search", provider="scrapegraphai")


def _conn(tmp_path, fake):
    import connectors
    c = connectors.DataConnector(root=tmp_path, prefer_live=True)
    c.scraper = fake
    return c


def test_openinsider_uses_scraper_markdown(tmp_path):
    fake = _FakeScraper(scrape_md="Insider sale table\n" + "row " * 40)
    c = _conn(tmp_path, fake)
    f = c.openinsider_trades("AMC")
    assert f.mode == "live" and f.data["markdown"].startswith("Insider sale table")
    assert any("openinsider.com" in u for u in fake.scrape_calls)

def test_glint_and_myfxbook_use_scraper(tmp_path):
    fake = _FakeScraper(scrape_md="signal " * 40)
    c = _conn(tmp_path, fake)
    assert c.glint_trade_signals("AMC").mode == "live"
    assert c.myfxbook_community("AMC").mode == "live"
    assert any("glint.trade" in u for u in fake.scrape_calls)
    assert any("myfxbook.com" in u for u in fake.scrape_calls)

def test_x_recent_search_feeds_posts(tmp_path):
    fake = _FakeScraper(search_data={"posts": [
        {"text": "$AMC to the moon", "platform": "x", "author": "u1", "url": "http://x/1"}]})
    c = _conn(tmp_path, fake)
    f = c.x_recent("AMC")
    assert f.mode == "live" and isinstance(f.data["data"], list) and len(f.data["data"]) == 1
    assert f.data["data"][0]["text"] == "$AMC to the moon"
    assert fake.search_calls  # used search(), not scrape()

def test_connectors_fall_back_to_replay_when_scraper_empty(tmp_path):
    fake = _FakeScraper(scrape_md=None, search_data=None)
    c = _conn(tmp_path, fake)
    # no live result and no replay artifact under tmp -> unavailable, never crashes
    assert c.openinsider_trades("AMC").mode in ("replay", "unavailable")
    assert c.x_recent("AMC").mode in ("replay", "unavailable")
