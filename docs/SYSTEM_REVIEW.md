# SECFEDCLAW — System Review (2026-07)

A four-dimension review of the system (human-centered design, architecture/engineering,
data sources / engineering / data science, and entity resolution), plus a prioritized
improvement roadmap. Findings are grounded in the code at the time of review.

Cross-cutting theme across all four reviews: **the system is well-architected but degrades
silently** — several failure modes leave it running on stale/empty data while reporting
healthy. That, plus a couple of "dead wires" that bias the corroboration gate, and a
circular backtest, are the highest-value things to fix.

---

## 1. Human-Centered Design (examiner UX)

**Strengths.** The trust/defensibility layer is genuinely strong: persistent WATCH-boundary
banner, per-package custody (SHA-256) + limitations drill-down, non-accusatory rationale,
single-source definitions reused as tooltips, and a closed in-app loop (drill-down → label →
retrain → rerun) with graceful `file://` degradation.

**Top findings.**
- **High — stale packages mix into review.** `render()` globs *every* `*_watch_v2.json`
  (weeks of history, duplicate tickers) and cards show no timestamp, so an examiner can
  review/label weeks-old evidence as if current. (`dashboard_v2.py` render + `package_cards`)
- **High — queue → evidence dead-end.** The Overview queue doesn't link to a ticker's card;
  Packages shows only top-24 across all history with no search/filter, so a queued ticker may
  have no reachable card.
- **High — post-run staleness.** After a dashboard-triggered rerun, the open page never tells
  the examiner to reload; Runs says "finished" while every other tab shows the old snapshot.
- **High — labeling is a partial slice.** UI exposes 3 of 5 ledger labels (missing
  `missed_event`, `insufficient_evidence`), no note field (though the API accepts one),
  labeled state isn't persisted (reload forgets it → double-labels).
- **High — Network tab is a dark-theme leftover on a light page** (near-invisible labels,
  no resize redraw, no per-ticker focus, no AT access).
- **High — nav tabs are keyboard-inaccessible `<div onclick>`** (508 problem for a federal tool).
- **Med** — hardcoded "facts" (feature importances, label counts) drift from the live model;
  no "why" column in the queue; in-app UI still teaches the CLI; empty states dead-end.

---

## 2. Architecture & Engineering

**Strengths.** Clean live/replay custody model, role-bounded agent pipeline, threaded server
with single-flight locks, broadly good test suite (~230 tests).

**Top findings.**
- **High — non-atomic writes.** Only `run_manifest.json` used temp-then-rename;
  `review_queue.json`, `model.json`, `edgar_state.json`, ledger, usage were bare writes →
  corruption races under the threaded server + concurrent scans. **[Fixed in Wave 1]**
- **High — `_http_text` had no retry / no rate limit** (carries SEC/Nasdaq/Reddit-RSS feeds) →
  SEC fair-access risk + silent degradation on any blip. **[Fixed in Wave 1]**
- **High — model.json read/write race**: retrain writes non-atomically while a scan reads it;
  a corrupt read is swallowed (advisory silently disappears). **[Write side fixed in Wave 1]**
- **High — `edgar_pipeline` → `agents` circular import** (`CIK_MAP` lives in `agents`).
- **Med** — `dashboard_v2.py` is a 1,480-line god-file; serve.py/`CIK_MAP` module globals are
  unguarded/test-hostile; `daily.py` lockfile is non-atomic.
- **Med** — `out/` path drift: every module hardcodes its own `out/`; `scan.py --out` desyncs
  the dashboard/model/ledger.

---

## 3. Data Sources / Engineering / Data Science

**Strengths.** Uniform live→replay→unavailable fallback with full custody; honest preflight
(reads Firecrawl credit balance, walks flatfiles back over the T+1 lag); careful `robust_stats`;
no lookahead leakage in market baselines; sound rules-primary / model-advisory split with
abstention gates and deliberate anti-leak bootstrap.

**Top findings.**
- **High — one transient failure flips the whole run to replay.** `_http_json` set the shared
  `_live_ok=False` on any host's failure → all subsequent Polygon fetches silently replay.
  **[Fixed in Wave 1 — scoped to the Polygon probe.]**
- **High — Reddit RSS success stores raw XML; `normalize_posts` only parses dicts** → zero
  Reddit posts, but `reddit_unavailable=False`, so coverage is silently fictional and the
  evidence-quality penalty is suppressed.
- **High — dead wire #1: `_is_issuer_specific` is never called** → every non-promo post counts
  as issuer-specific, inflating the social-burst + cross-platform inputs to the corroboration gate.
- **High — dead wire #2: `official_scores` has no recency filter** → nearly any active filer
  lights `issuer_context ≥ 30`, giving a near-free second family and collapsing the
  "≥2 independent families" HIGH/CRITICAL gate to ≈1.
- **High — non-monotonic market score**: raw 100.1 → ~83.9 while 99.9 → 99.9 (a stronger
  signal can score lower).
- **High — circular validation.** Synthetic pump text is built from the detector's own
  `PROMO_TERMS`, and the real SEC-case corpus ships with empty windows → reported P/R/F1 and
  model AUC measure self-consistency, not detection power. The shipped model is
  synthetic-trained; the advisory doesn't disclose `n_real_labels`.
- **Med** — no probability calibration despite the "calibrated" claim; grouped-daily uses a
  calendar (not trading) day; replay artifacts have unbounded age; swallowed scraper errors
  (Firecrawl 402 == empty page); LLM-shaped SearchGraph posts feed coordination (homogenized
  text inflates near-dup clusters; no timestamps → burst-blind); several fetched-but-unused
  sources (social_web, FMP×3, glint) cost money with zero scoring effect.

---

## 4. Entity Resolution (+ UI)

**Core finding: the identity signal is computed and then thrown away.** Coordination features
compute `author_concentration_hhi`, `unique_authors`, and per-cluster `author_id`s, but none
of these reach disk — `coordination_detail` persists only cluster post-ids, shared domains, and
max burst. So the ~267-package / ~85-ticker corpus already in `out/` cannot be read as an
entity graph. The only persistent cross-run identity today is issuer CIK (EDGAR) and the
enforcement-feed recurrence signal.

**What real entity resolution requires (none exists):** a persistent entity store across runs
(accounts, domains, issuers, and content-cluster *script fingerprints*), fuzzy linking, a
recurrence signal ("this promoter cluster has appeared on N tickers over M weeks"), a scoring
hook, and a UI to explore an entity's cross-ticker footprint.

**Smallest high-value slice:** (1) persist the identity fields; (2) a JSONL `entities.py` store
+ `observe()` mirroring `ledger.py`; (3) a `--rebuild` backfill over the existing corpus;
(5) an Entities dashboard tab with per-entity cross-ticker footprints. Steps 7-8 (fuzzy
content-cluster merge + a gated `entity_recurrence_score`) make it *smart* once plumbing proves out.

---

## Improvement roadmap (discrete, tested PRs)

| Wave | Theme | Risk | Changes scores? | Status |
|---|---|---|---|---|
| **1** | Reliability & integrity + PII scrub | Low | No | **Done** (#40) |
| **2** | Entity resolution + UI (persist → store → backfill → Entities tab) | Med | Adds only | **Done** (#41) |
| **3** | Scoring correctness (issuer-specific wire, 90-day recency gate, monotonic map) | Med-High | **Yes — re-baselined** | **Done** |
| **4** | HCD loop (queue↔evidence links, latest-per-ticker + timestamps, finish labeling, keyboard nav) | Low-Med | No | **Done** (#42) |
| **5** | De-circularize validation **(done)**; real probability calibration, split `dashboard_v2.py`, unify `out/` path, decouple `edgar_pipeline`/`CIK_MAP`, Reddit RSS parse | High | Yes | **Done** |

### Wave 3 — delivered (with the Wave-5 backtest de-circularization it depends on)
- **De-circularized the backtest first** (Wave-5 dependency): synthetic pump text no longer reuses the detector's `PROMO_TERMS` — coordinated pumps are near-duplicate scripts in an independent vocabulary, so detection must rest on coordination *structure* + market double-confirmation. Honest re-baseline result: **recall stays 1.000** even without lexicon overlap (detection isn't just wordlist memorization), and **thin-microcap precision improved 0.31 → 0.40** with no recall loss.
- **Wired the dead `_is_issuer_specific`** — off-ticker / irrelevant chatter no longer counts toward the issuer-specific burst or the cross-platform flag that feed corroboration.
- **90-day issuer recency gate** (`_ISSUER_RECENCY_DAYS`) — a stale filing no longer lights a near-free second family; the ≥2-family HIGH/CRITICAL gate is meaningful again.
- **Monotonic market map** — `min(score,100)`; the ≤100 band region is unchanged, extreme raw scores saturate at 100 instead of folding back below weaker ones.

**Wave 5 — delivered so far:** backtest de-circularization (above); **unified `out/` path** (`config.output_root()` + `SECFEDCLAW_OUT_DIR`, applied across all 9 modules — fixes the `scan.py --out` desync); **decoupled `CIK_MAP`** into a thread-safe `cik_registry.py` (breaks the `edgar_pipeline`→`agents` import cycle, adds the missing load lock).

**Wave 5 — complete.** De-circularized backtest; unified `output_root()`; thread-safe `cik_registry` (cycle broken); Reddit RSS parsing; honest Platt calibration; and the `dashboard_v2.py` god-file fully decomposed — CSS/JS → `dashboard_assets.py`, shared helpers → `dashboard_common.py`, panel renderers → `dashboard_panels.py`, leaving `dashboard_v2.py` a 156-line orchestrator (from 1619). Every step verified behavior-preserving.

### Wave 1 — delivered
- `io_util.atomic_write` (temp + `os.replace`) applied to `review_queue.json`, `model.json`,
  `edgar_state.json` + issuer features, the daily summary, and `agent_status.json`.
- `_http_text` brought to parity with `_http_json` (per-host rate limit + transient-only retry).
- Scoped the live→replay flip to the Polygon probe (a single source failure no longer poisons
  the whole run).
- Serialized `ledger`/`usage` JSONL appends behind a lock (threaded-server safety).
- Scrubbed a personal email + account from `connectors.py`; added a PII regression test.
