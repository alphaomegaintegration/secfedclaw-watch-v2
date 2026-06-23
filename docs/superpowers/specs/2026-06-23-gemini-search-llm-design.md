# Speed up Scout search: Gemini Flash LLM + Chromium tuning

Date: 2026-06-23
Status: approved (design)
Branch: `feat/gemini-search-llm`

## Problem

Scout's per-ticker latency is ~32 min median (SRE dashboard). The cost is
`SearchGraph`: for each ticker it DuckDuckGo-searches, renders ~5 result pages
in headless Chromium, then runs the LLM to extract. Two bottlenecks:

1. **LLM** — local Ollama `gemma4` (9.6 GB multimodal, 128k ctx) is slow per
   call, and Ollama serves one request at a time, so parallel scan workers
   queue behind each other.
2. **Chromium** — ~5 page renders (each waits `networkidle`) per ticker search.

## Goal

Make Gemini Flash the default search LLM (fast, concurrent cloud inference — no
single-instance serialization), and cut the Chromium half. Keep local Ollama
and Firecrawl as fallbacks. No behavior change for the `scrape()` path (it needs
no LLM).

Decision (locked with operator): use **Gemini** (`gemini-2.0-flash`), key in
`.env` as `GEMINI_API_KEY` (validated, models reachable). Accept the small
per-scan cost (~$0.10/$0.40 per 1M tokens) and the external dependency for the
search path; local Ollama remains the offline fallback.

## Changes

### `scrape_provider.py`

- **LLM config — add a Gemini branch.** `_llm_config()` currently handles
  `ollama/*` (local) vs everything-else (OpenRouter/OpenAI-compatible). Add: if
  `SGAI_MODEL` names a Gemini model (`gemini*` or `google_genai/*`), build a
  `langchain_google_genai` config: `{"model": "google_genai/<model>",
  "api_key": env["GEMINI_API_KEY"], "max_tokens": SGAI_MAX_TOKENS}`. scrapegraphai
  routes Gemini through `langchain_google_genai`.
- **Default model.** `DEFAULT_MODEL = "gemini-2.0-flash"` (was
  `ollama/gemma4:latest`). Ollama stays available by setting `SGAI_MODEL=ollama/...`.
- **search() key gate.** `_sgai_search` requires a key for non-local models;
  generalize the check: local (`ollama/*`) needs none; Gemini needs
  `GEMINI_API_KEY`; OpenRouter needs `OPENROUTER_API_KEY`. If the required key is
  missing, skip SGAI → Firecrawl → replay (no crash).
- **Chromium tuning.** `SearchGraph(..., max_results=N)` where
  `N = SGAI_SEARCH_RESULTS` (default **3**, was 5) — fewer page renders.
- **Search concurrency cap.** Add a module-level
  `Semaphore(SGAI_MAX_SEARCHES, default 3)` around `_sgai_search`, independent of
  the browser-scrape semaphore, so a wide `--workers` run doesn't fire many
  concurrent SearchGraph pipelines (each of which spawns browsers + LLM calls).

### `preflight.py`

Extend the `scrapegraphai` probe: for a Gemini model, readiness = library
importable AND `GEMINI_API_KEY` present (and optionally a cheap models.list
reachability check). Keep the ollama-daemon and OpenRouter branches.

### Dependencies

Add `langchain-google-genai` to the venv and document it in `requirements.txt`
alongside the optional scrapegraphai stack. It's only needed when `SGAI_MODEL`
is a Gemini model; lazy-imported so its absence degrades to Ollama/Firecrawl.

### Config (new env, all optional)

| Var | Default | Purpose |
|-----|---------|---------|
| `SGAI_MODEL` | `gemini-2.0-flash` | search LLM (gemini\* / ollama/\* / openai/\*) |
| `SGAI_SEARCH_RESULTS` | `3` | pages SearchGraph renders per search |
| `SGAI_MAX_SEARCHES` | `3` | max concurrent SearchGraph pipelines |
| `GEMINI_API_KEY` | — | Google AI Studio key (already in `.env`) |

Existing `SGAI_MAX_TOKENS`, `SGAI_MAX_BROWSERS`, `OLLAMA_BASE_URL`,
`SCRAPE_PROVIDER_ORDER` unchanged.

## Provider/cost model

`search()` order stays scrapegraphai → firecrawl → replay. With Gemini default,
the scrapegraphai leg runs Gemini Flash (fast, concurrent). The LLM-cost view
(`usage.py`) already prices `gemini*` (the `gemini` key → $1.25/$5 per 1M); add a
`gemini-2.0-flash` entry at its real rate ($0.10/$0.40). scrapegraphai's internal
calls remain un-token-metered, so the SRE "local/free" line becomes a
"search via gemini-2.0-flash" provider note (no longer free, but cheap).

## Testing

- `_llm_config`: gemini model → `google_genai/*` config with api_key, no
  ollama base_url; ollama model → keyless local; openai model → OpenRouter.
- `search()` key gate: gemini model without `GEMINI_API_KEY` → skips SGAI
  (falls back), with key → attempts (mocked SearchGraph).
- `SGAI_SEARCH_RESULTS` / `SGAI_MAX_SEARCHES` honored (config + semaphore).
- usage: `gemini-2.0-flash` priced (known, paid).
- Hermetic (fake `scrapegraphai`/`langchain_google_genai` modules); full suite
  green on the stdlib CI interpreter.
- **Live verify:** one real `search($AAPL)` via Gemini returns posts in seconds
  (vs minutes on gemma4); a 2-ticker live scan shows Scout latency down sharply
  in the run manifest / SRE dashboard.

## Out of scope

- Replacing the `scrape()` path's LLM-free ChromiumLoader (unchanged).
- Gemini via OpenRouter (free-tier 402s on these prompts — direct Google key
  only).
- Removing Ollama (kept as the offline/no-cost fallback).
