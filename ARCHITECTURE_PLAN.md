# SECFEDCLAW v0.2 — Architecture Evolution Plan

> Status: proposal (revised after independent review). Supersedes the initial
> "migrate to Temporal + vector DB" sketch. WATCH-only context throughout.

## 1. Goals

1. A **better architecture** for the agentic pipeline (`agents.py` / `scan.py`).
2. An operational surface to **view and manage** runs/agents.
3. Optional **LLM + agentic social-intelligence** for pump-and-dump signals
   (urgency/FOMO language, cross-platform copy-paste coordination, ticker
   verification against volume/price moves, coordinated-push detection).

## 2. Governing principles (unchanged)

- **Deterministic core stays deterministic.** `scoring_v2.build_package`,
  `features/coordination.py`, and `AdversaryAgent` are not modified by this
  plan. Same inputs → same scores.
- **Auditability / provenance first.** Every record keeps `source + mode +
  sha256 + redacted URL`. A run must be reproducible and explainable months
  later, offline, without depending on a vendor's moving-target model.
- **Stdlib-first.** New third-party/runtime deps are a cost paid only when they
  buy something the stdlib genuinely can't. The no-deps footprint is a
  compliance asset (small supply chain, easy to vendor and audit).
- **LLM is subordinate to invariants.** Any LLM emits *bounded, cited features*
  only; the deterministic scorer turns features → score; the LLM never sets a
  priority. The ≥2-family HIGH gate, the adversary-only-lowers rule, and the
  WATCH ceiling are inviolable.

## 3. Decisions (and reversals from the first sketch)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **No Temporal / no workflow engine** (for now). | 6–60 tickers/day, ~25 fetches each, finishing in minutes on one host hits none of the break-evens (multi-hour runs, thousands concurrent, mid-flow human waits). It would also discard the stdlib-only footprint for capability we won't use. |
| D2 | **In-process concurrency instead.** `ThreadPoolExecutor` fan-out + per-source rate limiting + retries + a content-addressed custody cache (already present) as the checkpoint + a run-manifest. | Captures ~all the real benefit (parallel fetches, retries, idempotent re-runs, durable status) at a fraction of the cost, staying stdlib. |
| D3 | **If we ever scale up → Dagster, not Temporal.** | Surveillance is asset/lineage-shaped (fetch = versioned asset, partitioned by ticker×date). Re-evaluate only when the universe grows to thousands or cadence goes intraday. |
| D4 | **"View & manage" = live domain dashboard**, not a workflow console. | A compliance operator needs in-flight/done/errored status, *why* a ticker scored, re-run/toggle controls — not activity-retry timelines. Extend the HTML dashboard we already emit. |
| D5 | **MinHash/Jaccard is the primary coordination mechanism; vector DB is not.** | Verbatim cross-platform copy-paste is a lexical near-dup problem; shingling beats cosine similarity on it and is reproducible forever. We already have k-shingle Jaccard. |
| D6 | **Embeddings only as an optional *secondary* paraphrase signal, with a version-pinned, self-hosted model.** Never a hosted moving-target API as a trigger. | Hosted embeddings can't be regenerated to defend an old WATCH package; that's disqualifying for an audit trail. |
| D7 | **LLM social node kept (features-not-verdicts), but hardened.** | See §5.5: persist full I/O, deterministic grounding verifier, prompt-injection threat model, family-independence quarantine. |
| D8 | **`sc-research` (and any scraping) gated on legal/ToS review.** | npm dep + Node runtime in a stdlib regulated tool, and X/Reddit ToS likely prohibit scraping. Prefer official APIs; isolate behind a lower-trust connector. |
| D9 | **Do NOT build a pluggable equities/crypto market-verifier yet.** | The crypto framing (CoinGecko/DexScreener/tokens) is for an equities system. Build only the Polygon/FMP equities verifier unless/until crypto scope is confirmed. |

## 4. Target architecture

```
scan.py (run manager)
  │  build universe (explicit | default | --discover movers)
  │  open run-manifest  (run_id, started_utc, mode)
  ▼
RunPool ── ThreadPoolExecutor(max_workers=N) ── one task per ticker
  │            each task = Orchestrator.run(ticker)  (UNCHANGED control flow)
  │            per-ticker status streamed into the manifest
  ▼
Orchestrator.run(ticker)
  ├─ ScoutAgent.gather() ........ NOW concurrent fetches (per-source rate-limited, retried)
  ├─ AnalystAgent.score() ....... scoring_v2 UNCHANGED (pure)
  ├─ if MEDIUM+:
  │     ├─ ScoutAgent.enrich() .. concurrent (existing)
  │     ├─ SocialIntelAgent ..... ★ optional, env-gated (§5.5)
  │     └─ AnalystAgent.score() . re-score with intel as a CAPPED feature
  ├─ AdversaryAgent.review() .... only-lowers invariant UNCHANGED
  ├─ ExplainerAgent.explain() ... existing guardrailed LLM narrative
  └─ PackagerAgent.write() ...... custody JSON + sha256 UNCHANGED
  ▼
review_queue.json  +  run-manifest.json  →  live dashboard reads both
```

The agent *roles and sequence* are unchanged. What changes is **how work is
scheduled (concurrency + manifest)** and **one new optional evidence source**.

## 5. Component design

### 5.1 Concurrency + rate limiting (D2) — the core upgrade

- A small `concurrency.py`:
  - `RateLimiter` per source (token-bucket; EDGAR needs ≤ documented rate +
    required `User-Agent`; Polygon/FINRA/social each own a bucket).
  - `retry(fn, attempts=3, backoff=2.0, retry_on=(URLError, TimeoutError, HTTP5xx, HTTP429))`.
- `ScoutAgent.gather()` submits its ~25 fetches to a `ThreadPoolExecutor`
  (I/O-bound, stdlib `urllib` is blocking) instead of calling them serially.
  Each fetch passes through its source's `RateLimiter` then `retry`.
- `scan.py` runs tickers through a second bounded pool. Failure of one ticker
  still never aborts the scan (existing behavior preserved).

> Net effect: the single biggest latency win, plus real retry/backoff, with
> **zero** new external dependencies.

### 5.2 Custody cache as checkpoint (D2)

The existing live→replay custody fallback is the checkpoint. Key cached
records by `sha256(source + normalized_params)`. A re-run of the same day skips
already-fetched records and is idempotent. No new state store needed.

### 5.3 Run-manifest (D2 / D4)

`out/run_manifest.json`, written incrementally during the run:

```json
{
  "run_id": "2026-06-16T19:00Z",
  "mode": "live",
  "universe": ["AAPL", "..."],
  "started_utc": "...", "finished_utc": "...",
  "tickers": {
    "AAPL": {"status": "done", "priority": "LOW",  "ms": 1840,
             "fetches": {"polygon_daily_range": "live", "x": "replay", "...": "..."}},
    "GME":  {"status": "error", "error": "TimeoutError: polygon_trades"}
  },
  "social_intel_enabled": false
}
```

This is the durable run record (replaces what a workflow engine's history would
give us) **and** the data source for the live dashboard.

### 5.4 Live dashboard + control plane (D4)

- The dashboard reads `review_queue.json` **and** `run_manifest.json`; it shows
  in-flight / done / errored per ticker and links each to its package + the
  families that fired and what the adversary lowered.
- A tiny **localhost-only** control endpoint in `serve.py` (already localhost-
  bound, token-gated) exposes: re-run a ticker, re-run failed only, toggle
  `social_intel` for the next run, edit the universe. No new platform.
- Engineering-side LLM call tracing (prompt/response/tokens/cost) goes to
  **Langfuse (self-host)** *only if/when* §5.5 ships — kept separate from the
  operator dashboard. `usage.py` already tracks cost and can feed it.

### 5.5 SocialIntelAgent (optional, env-gated `SECFEDCLAW_SOCIAL_INTEL=1`)

Behind the existing MEDIUM+ cost gate. Four steps; only one uses an LLM.

1. **Collect** — official APIs preferred (Reddit API, X API tier) + existing
   StockTwits/operator-provided Telegram/Discord exports. `sc-research` only if
   it clears D8; if used, isolate behind a connector flagged *lower-trust* and
   marked as such in provenance. Normalize → `{platform, author, ts, text, id,
   url, sha256}`.
2. **Coordination (deterministic, no LLM)** — **MinHash + LSH** (or the existing
   k-shingle Jaccard) over the 24h window. A cluster with `jaccard ≥ τ`,
   `platforms ≥ 2`, `unique_authors ≥ K` is the *coordinated-push* evidence.
   Fully reproducible from the retained corpus. This is the primary signal.
3. **Urgency/FOMO (LLM, the only non-deterministic step)** — temp 0, **structured
   output**, must cite `post_id`s. Returns bounded features + an *advisory*
   verdict enum. Hardening (mandatory):
   - **Persist full I/O** (model+version, prompt, raw response, ts) into the
     custody record — the LLM output is *recorded evidence*, not a reproducible
     computation. Temp 0 ≠ determinism.
   - **Grounding verifier (deterministic):** for every claimed urgency phrase,
     confirm it is actually a substring/fuzzy-match of the cited post; drop
     unverifiable claims before they reach the scorer.
   - **Prompt-injection threat model:** inputs are hostile by definition
     (pump-and-dumpers author them). Features-only + verifier mitigates; must be
     explicitly tested.
   - Reuse `explainer.py`'s guardrail (reject fraud/accusation/trading language).
4. **Market verification (deterministic)** — align the push window to a real
   move via Polygon snapshot/trades + FMP. Equities only (D9). This is what
   lets a social cluster corroborate into a higher band — i.e. it lights the
   `market` family, satisfying the ≥2-family gate the *right* way.

- **Optional secondary paraphrase signal (D6):** a version-pinned, self-hosted
  embedding model (e.g. a vendored sentence-transformers checkpoint, model id +
  dim recorded in custody) over the same corpus, brute-force cosine — added
  *only if* MinHash measurably underperforms on real data. Never a hosted API,
  never a trigger on its own.

### 5.6 Scoring integration (keeps determinism + the safety gate)

`SocialIntelAgent` writes `fetches["coordination_intel"]` = bounded features +
cited evidence. A new **deterministic** mapping turns those features into a
**capped** contribution to the existing `coordination_score`. The LLM's
advisory verdict + narrative flow only to the Explainer, never to the score.

**Family independence (must decide — see §6):** LLM/social-intel signals are
*correlated* with the existing social connectors. Default stance: quarantine
them as **non-independent** for the ≥2-family HIGH gate, so social-only
coordination still cannot reach HIGH without independent `market`/`issuer_event`
corroboration. This preserves the crown-jewel invariant.

## 6. Open gates — resolve BEFORE coding the social node

- **G1 (legal/ToS):** Is scraping X/Reddit (incl. via `sc-research`) permissible
  for this use? If not, official APIs only. Blocks §5.5 step 1.
- **G2 (scope):** Is the universe actually expanding to crypto? If no, drop the
  pluggable verifier abstraction; build Polygon/FMP only (D9).
- **G3 (invariant):** Confirm the family-independence stance in §5.6 with
  whoever owns the scoring policy. Getting it wrong silently weakens the HIGH gate.

(§7 Phase 0–1 do **not** depend on these gates and can start immediately.)

## 7. Phased rollout

| Phase | Scope | Depends on | Risk |
|-------|-------|------------|------|
| **0** | Concurrency layer (§5.1) + run-manifest (§5.3). Parity test: `review_queue.json` byte-identical to today on a fixed replay corpus. | — | Low (no scoring change) |
| **1** | Live dashboard reads manifest; localhost control endpoint (§5.4). | 0 | Low |
| **2** | `SocialIntelAgent` steps 1–2 + 4 (collection + MinHash + market verify), **no LLM yet**, behind `SECFEDCLAW_SOCIAL_INTEL=1`, capped feature into scorer (§5.6). | G1, G2, G3 | Medium |
| **3** | LLM urgency node (§5.5 step 3) with full hardening + Langfuse tracing. | 2 | Medium (audit + injection) |
| **4** | Optional embedding secondary signal (§5.6), only if measured need. | 3 | Low |
| **(later)** | Dagster migration — only if scale/cadence outgrows in-process (D3). | metrics | re-evaluate |

## 8. Testing & acceptance

- **Phase 0 gate:** `review_queue.json` byte-identical to current pipeline on a
  pinned replay corpus; `tests/test_v2.py` stays green (scoring untouched).
- **Concurrency:** per-source rate limits respected (assert no source exceeds
  its bucket under fan-out); one ticker's failure never aborts the scan.
- **Social node:** deterministic clustering tests on fixture corpora;
  grounding-verifier test (LLM claims a phrase not in the cited post → dropped);
  prompt-injection fixture (hostile post tries to force "benign" → no effect on
  score); full LLM I/O persisted and hash-linked in the package.
- **Reproducibility:** re-running a stored corpus reproduces the deterministic
  features bit-for-bit; LLM-derived fields are present as *recorded* evidence
  with model+version stamped.

## 9. Explicitly NOT doing (and the trigger to revisit)

- **Temporal / Airflow / Prefect** — revisit only at thousands of tickers,
  intraday cadence, or genuine mid-run human-approval needs → then **Dagster**.
- **Vector DB as a primary mechanism** — revisit embeddings only as a measured
  secondary signal with a self-hosted pinned model.
- **Autonomous agent frameworks (CrewAI/AutoGen/agentic LangGraph)** — wrong fit
  for a deterministic compliance pipeline; not on the roadmap.
- **Pluggable crypto market-verifier** — only if G2 confirms crypto scope.
