# LLM cost fix + SRE observability dashboard

Date: 2026-06-23
Status: approved (design)
Branch: `feat/sre-observability-dashboard`

## Goal

Two linked operability improvements:

1. **Fix LLM usage cost** so local-Ollama calls price correctly as free
   (currently they read as "unknown pricing"), and the cost view splits paid
   (OpenRouter/Anthropic) vs free (local) spend.
2. **Turn the Status tab into a full SRE observability dashboard** of the
   integrations, the agents, and how they are performing — built statically per
   scan from data the pipeline already produces (`run_manifest.json`,
   `review_queue.json` `source_health`, preflight, usage ledger).

Decisions (locked with the operator): local = $0 known-free with a paid/free
split (no fragile token scraping of scrapegraphai's internal calls); full SRE
view (SLO header + integration matrix + agent performance + LLM cost); rendered
statically per scan like the rest of the dashboard.

## 1. LLM cost fix — `usage.py`

- Add `"ollama": (0.0, 0.0)` and `"local": (0.0, 0.0)` to `DEFAULT_PRICING`.
  `price_for("ollama/gemma4:latest")` then matches → `(0, 0, known=True)`
  instead of `known=False`. Add `is_free(model)` = matched a zero-price key.
- `summary()` gains: `paid_cost_usd`, `paid_calls`, `local_free_calls`
  (recorded calls whose cost is 0 and model matched a free key). Existing keys
  (`total_cost_usd`, `by_model`, …) unchanged — additive.
- scrapegraphai's SearchGraph runs on local Ollama and is **not token-metered**
  (by decision), so its free usage is surfaced in the dashboard from the
  manifest `providers` map (count of `x`/`social_web` served by `scrapegraphai`
  = local searches this run, $0), labeled "not token-metered". The usage ledger
  still correctly prices any local call that *is* recorded (e.g. a local
  Explainer).

## 2. Per-agent performance — `agents.py` + `scan.py`

- Time each orchestrator stage and map to the agent that owns it:
  gather→**Scout**, enrich+score→**Analyst**, adversary→**Adversary**,
  explain→**Explainer**, package→**Packager**. Add `stage_ms: {agent: ms}` to
  the run summary. Wrap with `time.monotonic()`; a stage that is skipped/failed
  records its elapsed time and the existing error path is unchanged.
- `scan.py`: include `stage_ms` per ticker in `run_manifest.json` (additive,
  next to `fetches`/`providers`).

## 3. Status assembler — `agent_status.py`

- **Agents:** add `latency_ms` (`{p50, max}` aggregated across tickers from
  `stage_ms`), `runs`, `errors`. Refresh `AGENT_DEPS`: Scout gains the
  scrape/search sources (discord, instagram, facebook, social_web, openinsider,
  glint) and the provider chain note (scrapegraphai → firecrawl); Explainer
  notes the local-Ollama option.
- **Integrations:** `integration_health` gains `success_pct`
  (`ok/total*100`) and `provider` (the provider that served it, from
  `source_health[k].provider`; majority across tickers).
- **System SLO:** add `integrations_live_pct`, `last_run_age_s`, `error_rate`
  (errors/total tickers) to the `system` block.
- **LLM:** add `paid_cost_usd`, `paid_calls`, `local_free_calls`, and
  `local_search_calls` (from the manifest providers map).
- `build()` reads `run_manifest.json` (new) in addition to its current inputs.

## 4. SRE panel — `dashboard_v2.py` (Status tab)

Upgrade `agent_status_panel` to render `agent_status.build(queue)` at generation
time (always fresh, offline). Sections, using existing card/table/badge styles:

- **SLO header cards:** integrations-live % · last-run freshness · error rate ·
  paid LLM spend.
- **Integration health matrix** (table): source · state badge
  (live/replay/unavailable) · ok% · live/replay counts · provider · last status.
- **Agent performance** (table): agent · state · role · latency p50/max · errors.
- **LLM cost:** paid $ by model + "local/free: N search calls via Ollama ($0,
  not token-metered)".

No new tab; the existing `status` tab is upgraded in place. `llm_cost_panel`
keeps its detailed ledger view; the SRE panel links to it.

## Data flow

```
scan.py
  → orch.run(ticker)            # stage timing + source_health[].provider
  → run_manifest.json           # + stage_ms, + providers (already)
  → review_queue.json           # source_health (already)
agent_status.build(queue)       # aggregates manifest + queue + preflight + usage
  → agent_status.json
dashboard_v2.build_html         # renders SRE panel from agent_status
```

## Testing

- `usage`: `ollama/*` prices to `(0,0,known=True)`; `is_free` true for local,
  false for paid; `summary()` paid/free split correct on a mixed ledger.
- `agent_status`: integration `success_pct`/`provider` aggregation; agent
  `latency_ms` p50/max from `stage_ms`; SLO fields; llm split. Hermetic
  (synthetic queue + manifest fixtures) — no live deps.
- `agents`: `stage_ms` present in summary and keyed by the five agents.
- `dashboard`: SRE panel renders from a sample `agent_status` without raising;
  contains the section headers.
- Full suite stays green.

## Out of scope

- Token-metering scrapegraphai's internal SearchGraph calls (decision: local is
  free, surfaced via provider counts).
- Live/real-time polling (decision: static per scan; the Runs tab already covers
  live polling).
- Historical time-series / charts of performance — single-run snapshot only.
