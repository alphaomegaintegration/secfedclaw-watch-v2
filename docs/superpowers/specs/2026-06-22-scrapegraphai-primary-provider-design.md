# ScrapeGraphAI-primary scrape/search provider

Date: 2026-06-22
Status: approved (design)
Branch: `feat/scrapegraphai-primary-provider`

## Goal

Make the open-source **ScrapeGraphAI** library (`scrapegraphai`,
https://github.com/ScrapeGraphAI/Scrapegraph-ai) the **primary** web + social
scrape/search provider for SECFEDCLAW, with **Firecrawl** demoted to a
**fallback**. ScrapeGraphAI must serve the same function Firecrawl does today
(URL → extracted text) and additionally cover all web + social-media
searches/scrapes — including X/Twitter — via its LLM web-search graph.

This directly addresses the current production gap: Firecrawl is at 0/1000
credits (HTTP 402) and X API requires a paid tier, so the social/scrape
connectors are degrading to replay. A ScrapeGraphAI primary that drives its own
browser + LLM (using the existing `OPENROUTER_API_KEY`) restores live coverage
without paying for Firecrawl or the X API.

## Decisions (locked with the operator)

1. **Integration mode:** OSS library `scrapegraphai` (not the hosted SaaS),
   using the existing `OPENROUTER_API_KEY` for the LLM. No new SaaS key.
2. **X/Twitter + social coverage:** `SearchGraph` (LLM web search). Resilient —
   does not depend on scraping X directly or on dead Nitter mirrors.
3. **Page loader:** full browser (Playwright/Chromium), scrapegraphai default.
   Resource-bounded under the parallel scan (see Concurrency).
4. **Scope:** all 8 current Firecrawl call sites route through one shared
   provider: ScrapeGraphAI primary → Firecrawl fallback → replay.

## Architecture

### New module: `scrape_provider.py`

Single responsibility: given a URL or a search query, return extracted
text + source + which provider answered, trying providers in configured order.

```
@dataclass
class ScrapeResult:
    markdown: str          # extracted/visible text (markdown-ish)
    data: Any              # structured payload (dict from SGAI, or firecrawl json)
    source: str            # redacted source URL / "scrapegraphai:search"
    provider: str          # "scrapegraphai" | "firecrawl"

class ScrapeProvider:
    def __init__(self, env, timeout, max_browsers=None, order=None): ...
    def scrape(self, url, prompt=None) -> ScrapeResult | None
    def search(self, query, prompt=None) -> ScrapeResult | None
```

- **`scrape(url)`** tries providers in `order`:
  - `scrapegraphai`: `SmartScraperGraph(prompt or DEFAULT_EXTRACT, source=url,
    config).run()`. Non-empty → `ScrapeResult(provider="scrapegraphai")`.
  - `firecrawl`: existing `POST https://api.firecrawl.dev/v1/scrape`
    `{url, formats:[markdown], waitFor}` → `ScrapeResult(provider="firecrawl")`.
  - none succeed → `None` (caller degrades to replay).
- **`search(query)`** tries:
  - `scrapegraphai`: `SearchGraph(prompt=query, config).run()`.
  - `firecrawl`: `POST .../v1/search` if available, else skipped.
  - none → `None`.
- **Lazy import**: `import scrapegraphai` happens inside the method, wrapped in
  try/except. If the package is absent or Chromium fails to launch, the provider
  silently skips to Firecrawl. The scan never hard-fails on the heavy dep.

### LLM config (OpenRouter, OpenAI-compatible)

```
config = {
  "llm": {
    "model": SGAI_MODEL,                       # default "openai/gpt-4o-mini"
    "api_key": env["OPENROUTER_API_KEY"],
    "base_url": "https://openrouter.ai/api/v1",
  },
  "headless": True,
  "verbose": False,
  "loader_kwargs": {"timeout": timeout},
}
```

If the installed scrapegraphai rejects `base_url` for the `openai/` provider,
the build step verifies and falls back to the documented provider syntax; this
is a build-time verification, not a runtime branch.

### `connectors.py` refactor

`DataConnector.__init__` constructs `self.scraper = ScrapeProvider(self.env,
self.scrape_timeout)`. Each of the 8 methods replaces its inline Firecrawl block
with one call:

| Connector method        | Call                                  |
|-------------------------|---------------------------------------|
| `x_recent`              | `self.scraper.search("$TICKER ...")`  |
| `social_web_search`     | `self.scraper.search(...)`            |
| `discord_search`        | `self.scraper.scrape(disboard_url)`   |
| instagram               | `self.scraper.scrape(picuki_url)`     |
| stock forums            | `self.scraper.scrape(forum_url)`      |
| `openinsider_trades`    | `self.scraper.scrape(openinsider_url)`|
| `glint_trade_signals`   | `self.scraper.scrape(glint_url)`      |
| (+1 remaining site)     | `self.scraper.scrape(url)`            |

Custody wrapping (`_live` / `_replay`), `redact()`, `scrape_timeout`, and the
existing `warnings.warn(...)` on failure are all preserved. The X API v2 first
path in `x_recent` stays (free if it ever works); SearchGraph is the new
second path before replay.

### Concurrency / Playwright safety

`graph.run()` uses asyncio internally; in ThreadPool scan workers (no running
loop) `asyncio.run` is safe. Chromium use is bounded by a module-level
`threading.Semaphore(SGAI_MAX_BROWSERS, default 2)` around browser scrapes so a
`--workers 6` scan does not launch 6 Chromiums at once. Any browser/launch
exception → Firecrawl fallback.

## Configuration (new env, all optional)

| Var                     | Default                        | Purpose                              |
|-------------------------|--------------------------------|--------------------------------------|
| `SGAI_MODEL`            | `openai/gpt-4o-mini`           | OpenRouter model for extraction      |
| `SGAI_MAX_BROWSERS`     | `2`                            | Max concurrent Chromium instances    |
| `SCRAPE_PROVIDER_ORDER` | `scrapegraphai,firecrawl`      | Provider priority / disable a leg    |

Reuses existing `OPENROUTER_API_KEY` and `FIRECRAWL_API_KEY`.

## Preflight

Add a `scrapegraphai` probe (import check + `OPENROUTER_API_KEY` presence)
reported as the **primary** provider. Keep the existing `firecrawl` probe,
relabeled conceptually as backup. Neither is in `CORE`, so they do not change
the GO_LIVE verdict (market core = polygon).

## Error handling / custody

Unchanged custody model: provider tags `source`; mode stays `live`/`replay`.
With Firecrawl at 0 credits, SGAI carries the load; if SGAI also fails →
replay. No secrets logged; source URLs run through `redact()`.

## Dependencies / build

- Add `scrapegraphai` to `requirements.txt` (optional-but-recommended note) and
  `requirements-dev.txt` (so tests of the live path can run).
- Document `playwright install chromium` as a post-install step (heavy: Chromium
  download). Update README + the daily launchd plist note.
- Python 3.13 compatibility is verified in the build step before wiring; if
  scrapegraphai does not support 3.13, the lazy-import design still degrades to
  Firecrawl, and the build documents the supported interpreter.

## Testing

- **Unit (mocked, in CI):** monkeypatch `SmartScraperGraph` / `SearchGraph` and
  the Firecrawl HTTP call. Assert: provider order (SGAI → Firecrawl → replay),
  `ScrapeResult` wrapping, `redact()` on source, semaphore gating, and graceful
  fallback when `scrapegraphai` import raises.
- **Wiring:** assert all 8 connectors call `self.scraper` (no inline
  `api.firecrawl.dev` left in those methods).
- **Live smoke (opt-in, network, NOT in CI):** behind `SGAI_LIVE_SMOKE=1`, one
  real `search("$AAPL ...")` and one `scrape(url)`; asserts a non-empty result
  from `provider == "scrapegraphai"`.
- Full existing suite stays green (172+).

## Build & execute checklist

1. `pip install scrapegraphai` + `playwright install chromium`; verify import +
   OpenRouter `base_url` config on Python 3.13.
2. Implement `scrape_provider.py`; refactor the 8 connectors; add preflight
   probe; update requirements/README.
3. Write + run unit tests; run full suite.
4. `python3 preflight.py` — expect `scrapegraphai` primary live, `firecrawl`
   backup (402).
5. `python3 scan.py --live --workers 6` — confirm X/social connectors now report
   `provider=scrapegraphai` live even with Firecrawl at 0 credits.

## Out of scope

- The hosted ScrapeGraphAI SaaS / `scrapegraph-py` SDK.
- Replacing non-scrape connectors (polygon, sec_edgar, finra, fmp, reddit,
  stocktwits) — those keep their dedicated clients.
- Raw-tweet fidelity from X directly (SearchGraph returns indexed/aggregated
  social content, by decision #2).

## Target coverage expectations (added 2026-06-23, #19)

Live scrape/search coverage is target-dependent. Observed on calm-tape runs
after the navigating-page fix (PR #20). All misses degrade gracefully to
cached replay — none are fatal.

| Connector | Path | Expected | Notes |
|-----------|------|----------|-------|
| forums (facebook_search) | scrape | live, reliable | public stock-forum mirrors |
| instagram | scrape | live (thin) | Picuki/Imginn; small payloads |
| openinsider | scrape | live (recovered in PR #20) | needs `networkidle`; was racing |
| x_recent | search (LLM) | live | local Ollama SearchGraph |
| social_web | search (LLM) | intermittent | LLM sometimes returns < content threshold |
| discord | scrape | best-effort | Disboard often bot-blocks headless; Firecrawl fallback gets it when it has credits; the Discord bot-API path is the real source |
| glint | scrape | **replay-only by design** | Cloudflare-protected React SPA; deferred to enrich() for MEDIUM+ and usually blocks headless |
| myfxbook | scrape | replay-only | forex-oriented; low equity signal, not in default scout set |

Which provider serves a best-effort source varies per run with target behavior
and Firecrawl credit availability. `run_manifest.json` now records a per-ticker
`providers` map (`{source: scrapegraphai|firecrawl}`) alongside `fetches`
(mode), so coverage and the provider that served each live fetch are observable
per run — e.g. a 2026-06-23 run showed openinsider/instagram/x via scrapegraphai
and discord/facebook/social_web via the Firecrawl fallback (its credits had
reset).
