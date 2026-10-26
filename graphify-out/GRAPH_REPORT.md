# Graph Report - secfedclaw-watch-v2  (2026-10-26)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 1749 nodes · 3465 edges · 101 communities (83 shown, 18 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 186 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `b6e97ccd`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- DataConnector
- esc
- _post
- backtest.py
- FlatFilesClient
- pathlib
- serve.py
- connectors.py
- test_social_intel_llm.py
- with
- model.py
- Per-Security-Class Calibrated Thresholds
- edgar.py
- config.py
- Component Inventory
- daily
- social_import.py
- _pkg
- observe
- edgar_pipeline.py
- json
- _FakeConnector
- env
- build_x_searches
- test_sre_observability.py
- robust_stats.py
- build_package
- scan.py
- test_scrape_provider.py
- fake_sgai
- TODOS — SECFEDCLAW v0.2
- test_scoring_correctness.py
- ScrapeProvider
- market.py
- SECFEDCLAW v0.2 — agentic WATCH-level pump-and-dump review scorer
- .__init__
- steps
- SECFEDCLAW v0.2 — Architecture Evolution Plan
- ScrapeGraphAI-primary scrape/search provider
- preflight.py
- _parse_openinsider
- daily.py
- SECFEDCLAW — Presentation Script (SEC briefing)
- Authorized Social Import + Review-Priority Model
- explain
- ._sgai_scrape
- ScrapeResult
- flatfiles.py
- Speed up Scout search: Gemini Flash LLM + Chromium tuning
- Deployment and Monitoring
- enforcement.py
- TestConcurrencyUtils
- _Resp
- price_for
- Orchestrator
- official.py
- _synthetic_daily
- .gather
- Home.md
- TestSocialIntelScoring
- coordination.py
- SECFEDCLAW — System Review (2026-07)
- Polygon Flat Files Integration
- default_prober
- record
- Architecture Overview
- Multi-Platform Social Signals
- social_features
- normalize_posts
- CLI Reference
- Running the System
- coordination_score
- ledger.py
- SECFEDCLAW — Quick Demo Narrative (~2–3 min)
- LLM cost fix + SRE observability dashboard
- social_scores
- coordination_features
- .test_http_json_retries_transient_url_errors
- _call_bedrock
- 14. Going live (replay → live)
- Monitoring
- Historical Replay (historical.py)
- Training (`train_model.py`)
- Authorized Social Import (`social_import.py`)
- RateLimiter
- .search
- Security & responsible-use notes
- ._f
- TestGBM
- TestConcurrentAppend
- ._f
- retry
- CLAUDE.md
- Architecture
- TestGroupedDailyTradingDay
- TestLiveOkScoped
- 0. Quickstart
- hhi
- TestLedger
- TestNoPII
- schedule_install.sh

## God Nodes (most connected - your core abstractions)
1. `DataConnector` - 62 edges
2. `build_package()` - 56 edges
3. `ScrapeProvider` - 41 edges
4. `Fetch` - 35 edges
5. `esc()` - 27 edges
6. `fed_claw_root()` - 24 edges
7. `load_env()` - 21 edges
8. `_post()` - 21 edges
9. `build_html()` - 20 edges
10. `SECFEDCLAW v0.2 — agentic WATCH-level pump-and-dump review scorer` - 19 edges

## Surprising Connections (you probably didn't know these)
- ``agents.py`` --references--> `PackagerAgent`  [INFERRED]
  docs/wiki/Security-Class-Thresholds.md → agents.py
- ``FlatFilesClient(root=None, prefer_live=True, timeout=30)`` --references--> `fed_claw_root()`  [INFERRED]
  docs/wiki/Polygon-Flat-Files-Integration.md → config.py
- ``tests/test_social_import.py` (4 tests)` --references--> `load_authorized()`  [INFERRED]
  docs/wiki/Social-Import-and-Model.md → social_import.py
- `4. Entity Resolution (+ UI)` --references--> `observe()`  [INFERRED]
  docs/SYSTEM_REVIEW.md → entities.py
- `Wave 1 — delivered` --references--> `atomic_write()`  [INFERRED]
  docs/SYSTEM_REVIEW.md → io_util.py

## Import Cycles
- None detected.

## Communities (101 total, 18 thin omitted)

### Community 0 - "DataConnector"
Cohesion: 0.07
Nodes (11): DataConnector, _once(), _once(), Fetch, _limiter_for(), redact(), sha256_bytes(), Reddit OAuth Flow (+3 more)

### Community 1 - "esc"
Cohesion: 0.05
Nodes (41): bar(), _dd(), esc(), _fmt_age(), _fmt_ms(), info(), load(), pill() (+33 more)

### Community 2 - "_post"
Cohesion: 0.08
Nodes (9): TestDaily, _post(), _start(), TestControlEndpoint, TestDefaultRunnerIntegration, TestLabelEndpoint, TestRetrainEndpoint, fire_first() (+1 more)

### Community 3 - "backtest.py"
Cohesion: 0.06
Nodes (22): _class_balanced_sample(), _daily_baseline(), _F, _fetches(), _grouped_with(), _iso(), per_class_breakdown(), _promo_posts() (+14 more)

### Community 4 - "FlatFilesClient"
Cohesion: 0.07
Nodes (21): `credentials_present() → bool`, FlatFilesClient API, `FlatFilesClient(root=None, prefer_live=True, timeout=30)`, `get_day_aggs(day: str) → dict`, `market_fetches(ticker, event_date, lookback_days=70) → dict`, Testing, day_aggs_key(), _FF (+13 more)

### Community 6 - "serve.py"
Cohesion: 0.07
Nodes (8): _failed_tickers(), Handler, main(), make_server(), _retrain_model(), RunManager, TestServe, TestServeHardening

### Community 7 - "connectors.py"
Cohesion: 0.08
Nodes (11): _provider_from_note(), entity_id(), _load_seen(), _norm_domain(), _build_urgency_messages(), classify_urgency(), _default_providers(), _parse_json_obj() (+3 more)

### Community 8 - "test_social_intel_llm.py"
Cohesion: 0.10
Nodes (11): attach_urgency(), coordination_intel(), verify_urgency(), _caller(), _post(), _posts(), TestAttachUrgency, TestScoringIntegration (+3 more)

### Community 9 - "with"
Cohesion: 0.05
Nodes (38): runs-on, steps, env, IMAGE, jobs, build-and-test, publish, name (+30 more)

### Community 10 - "model.py"
Cohesion: 0.09
Nodes (11): auc(), feature_vector(), GradientBoosting, kfold_auc(), kfold_oof_decision(), load_scorer(), score_package(), _sigmoid() (+3 more)

### Community 11 - "Per-Security-Class Calibrated Thresholds"
Cohesion: 0.07
Nodes (23): `agents.py`, Class-Specific Thresholds, Dashboard Upgrades, Design Principle, `features/market.py`, Liquidity Class Column, Liquidity Classification, Operator KPI Cards (+15 more)

### Community 12 - "edgar.py"
Cohesion: 0.09
Nodes (18): CLI, Connection Modes, EDGAR Daily-Diff Pipeline, Filing Categories, Issuer Features Output, Overview, Pipeline Flow, Scoring Integration (+10 more)

### Community 13 - "config.py"
Cohesion: 0.11
Nodes (13): candidate_env_paths(), fed_claw_root(), load_env(), output_root(), compose_digest(), dashboard_url(), deliver(), main() (+5 more)

### Community 14 - "Component Inventory"
Cohesion: 0.06
Nodes (30): Accessibility, AI Slop Blacklist — Patterns Removed, Border Radius, Borders, Brand (USWDS blue-60v + SEC.gov navy), Cards (`.card`), Color Tokens, Component Inventory (+22 more)

### Community 15 - "daily"
Cohesion: 0.07
Nodes (30): context, target, build, command, env_file, image, profiles, restart (+22 more)

### Community 16 - "social_import.py"
Cohesion: 0.13
Nodes (13): authorized(), import_dir(), load_authorized(), parse_csv(), parse_discord_export(), _parse_file(), parse_jsonl(), parse_telegram_export() (+5 more)

### Community 17 - "_pkg"
Cohesion: 0.13
Nodes (4): _pkg(), TestNetworkGraphEdges, TestNetworkGraphNodes, TestNetworkGraphStats

### Community 18 - "observe"
Cohesion: 0.14
Nodes (13): aggregate(), _load_packages(), main(), observations_for(), add(), observe(), observe_dir(), recurrence_for_package() (+5 more)

### Community 19 - "edgar_pipeline.py"
Cohesion: 0.12
Nodes (12): _load(), main(), _business_days(), _load_state(), main(), _now(), _recent(), run() (+4 more)

### Community 20 - "json"
Cohesion: 0.14
Nodes (11): main(), _call_anthropic(), _call_openrouter(), main(), _parse_cases(), main(), main(), _bootstrap_samples() (+3 more)

### Community 21 - "_FakeConnector"
Cohesion: 0.09
Nodes (8): cik_for(), _FakeConnector, _FakeFetch, _normalize(), TestScanParity, TestTickerParallelism, TestCikRegistry, sec_company_tickers()

### Community 22 - "env"
Cohesion: 0.08
Nodes (25): FIRECRAWL_API_KEY, FMP_API_KEY, POLYGON_API_KEY, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, SEC_USER_AGENT, SECFEDCLAW_DAILY_NOLOCK, TWITTER_BEARER_TOKEN (+17 more)

### Community 23 - "build_x_searches"
Cohesion: 0.14
Nodes (5): build_case_brief(), build_x_searches(), submit_to_nousangels(), TestBuildCaseBrief, TestBuildXSearches

### Community 24 - "test_sre_observability.py"
Cohesion: 0.11
Nodes (13): _age_seconds(), agent_perf(), build(), integration_health(), 3. Status assembler — `agent_status.py`, _queue(), test_agent_perf_empty_manifest(), test_agent_perf_p50_max_and_errors() (+5 more)

### Community 25 - "robust_stats.py"
Cohesion: 0.17
Nodes (11): cross_sectional_z(), ewma(), gini(), _isnan(), mad(), median(), _quantile(), robust_z() (+3 more)

### Community 26 - "build_package"
Cohesion: 0.15
Nodes (13): enabled(), llm_enabled(), corroboration(), _band_down(), _benign_review(), build_package(), evidence_quality(), _evidence_rows() (+5 more)

### Community 27 - "scan.py"
Cohesion: 0.16
Nodes (8): run_concurrent(), discover_movers(), _iso_utc(), main(), run_scan(), _process(), _write_manifest(), TestRunManifest

### Community 28 - "test_scrape_provider.py"
Cohesion: 0.15
Nodes (10): coerce_search_to_posts(), fake_sgai_loader(), _make_record(), test_coerce_empty_for_unusable(), test_coerce_from_bare_list_and_alt_keys(), test_coerce_from_posts_key(), test_noise_filter_drops_handled_race_keeps_others(), test_scrape_gives_up_after_retries_then_none() (+2 more)

### Community 29 - "fake_sgai"
Cohesion: 0.12
Nodes (10): fake_sgai(), stub_firecrawl(), test_bedrock_search_needs_no_api_key(), test_scrape_falls_back_to_firecrawl_when_sgai_absent(), test_scrape_order_override_firecrawl_first(), test_scrape_sgai_primary_used_first(), test_scrape_skips_trivial_sgai_then_firecrawl(), test_search_records_gemini_usage() (+2 more)

### Community 30 - "TODOS — SECFEDCLAW v0.2"
Cohesion: 0.11
Nodes (18): Dashboard, Data Sources, Fixed, Go-to-market / strategy, Infrastructure, P0 — Security / Correctness, P1, P1 (+10 more)

### Community 31 - "test_scoring_correctness.py"
Cohesion: 0.13
Nodes (4): _parse_reddit_rss(), TestBacktestDecircularized, TestMarketMonotonic, TestRedditRSSCoverage

### Community 32 - "ScrapeProvider"
Cohesion: 0.18
Nodes (7): ScrapeProvider, test_env_config_defaults_and_overrides(), test_llm_config_bedrock(), test_llm_config_gemini_default(), test_llm_config_local_and_hosted(), test_scrape_returns_none_when_both_unavailable(), test_search_results_and_concurrency_config()

### Community 33 - "market.py"
Cohesion: 0.17
Nodes (8): _best(), cross_sectional_anomaly(), _daily_results(), market_anomaly_score(), microstructure(), _series(), time_series_anomaly(), latest_z()

### Community 34 - "SECFEDCLAW v0.2 — agentic WATCH-level pump-and-dump review scorer"
Cohesion: 0.12
Nodes (16): 10. Multi-platform social signals (implemented — `connectors.py`, `features/social.py`), 11. Per-security-class calibration (implemented — `features/security_class.py`), 12. Authorized Discord/Telegram import (implemented — `social_import.py`), 15. Enforcement history, per-class calibration, agent status & LLM cost, 16. Roadmap (next, in priority order), 2. Data sources — live status, 3. Algorithm upgrades (implemented here), 4. Agentic architecture (+8 more)

### Community 35 - ".__init__"
Cohesion: 0.16
Nodes (5): AdversaryAgent, AnalystAgent, ExplainerAgent, PackagerAgent, 2. Governing principles (unchanged)

### Community 36 - "steps"
Cohesion: 0.12
Nodes (15): jobs, test, name, branches, branches, name, run, uses (+7 more)

### Community 37 - "SECFEDCLAW v0.2 — Architecture Evolution Plan"
Cohesion: 0.13
Nodes (14): 1. Goals, 3. Decisions (and reversals from the first sketch), 4. Target architecture, 5.2 Custody cache as checkpoint (D2), 5.3 Run-manifest (D2 / D4), 5.4 Live dashboard + control plane (D4), 5.5 SocialIntelAgent (optional, env-gated `SECFEDCLAW_SOCIAL_INTEL=1`), 5.6 Scoring integration (keeps determinism + the safety gate) (+6 more)

### Community 38 - "ScrapeGraphAI-primary scrape/search provider"
Cohesion: 0.20
Nodes (14): Build & execute checklist, Configuration (new env, all optional), Decisions (locked with the operator), Dependencies / build, Error handling / custody, Goal, New module: `scrape_provider.py`, Out of scope (+6 more)

### Community 39 - "preflight.py"
Cohesion: 0.18
Nodes (3): main(), run_preflight(), TestPreflight

### Community 41 - "daily.py"
Cohesion: 0.27
Nodes (9): _acquire_lock(), _log(), main(), _now(), _release_lock(), run(), _run(), main() (+1 more)

### Community 42 - "SECFEDCLAW — Presentation Script (SEC briefing)"
Cohesion: 0.14
Nodes (13): 0. Cold open (60 seconds) — the problem, in their language, 10. Anticipated Q&A — have these ready, 1. What it is (90 seconds) — Tab: **Overview**, 2. A real review package (5 minutes) — Tab: **Packages** — *the core of the demo*, 3. How the evidence is built (3 minutes) — Tab: **Agents** (and **How it works**), 4. The scoring discipline (2 minutes) — Tab: **Methodology**, 5. Credibility — it speaks your case law (2 minutes) — Tab: **SEC case studies**, 6. Coordination, visualized (90 seconds) — Tab: **Network** (+5 more)

### Community 43 - "Authorized Social Import + Review-Priority Model"
Cohesion: 0.14
Nodes (13): API, Authorized Social Import + Review-Priority Model, Calibration Ledger (`ledger.py`), Design, Feature Vector, Labels, Output, Overview (+5 more)

### Community 44 - "explain"
Cohesion: 0.23
Nodes (8): _build_messages(), explain(), _facts(), llm_enabled(), _passes_guardrail(), template_explain(), TestGuardrail, TestTemplate

### Community 45 - "._sgai_scrape"
Cohesion: 0.16
Nodes (6): _browser_semaphore(), _install_asyncio_noise_filter(), _quiet_sgai_noise(), _scrapegraphai_installed(), _search_semaphore(), test_noise_filter_is_idempotent()

### Community 46 - "ScrapeResult"
Cohesion: 0.21
Nodes (8): redact(), ScrapeResult, _conn(), _FakeScraper, test_connectors_fall_back_to_replay_when_scraper_empty(), test_glint_and_myfxbook_use_scraper(), test_openinsider_uses_scraper_markdown(), test_x_recent_search_feeds_posts()

### Community 47 - "flatfiles.py"
Cohesion: 0.22
Nodes (3): main(), _operator_email(), _make_day()

### Community 48 - "Speed up Scout search: Gemini Flash LLM + Chromium tuning"
Cohesion: 0.15
Nodes (12): Build note (2026-06-23), Changes, Config (new env, all optional), Dependencies, Goal, Out of scope, `preflight.py`, Problem (+4 more)

### Community 49 - "Deployment and Monitoring"
Cohesion: 0.15
Nodes (13): Daily Digest (`notify.py`), Dashboard deep-link, Dashboard Server (`serve.py`), Delivery channels, Deployment and Monitoring, Deployment Overview, Install (Linux cron), Install (macOS launchd) (+5 more)

### Community 50 - "enforcement.py"
Cohesion: 0.26
Nodes (4): enforcement_score(), match_releases(), parse_releases(), TestEnforcement

### Community 52 - "_Resp"
Cohesion: 0.15
Nodes (4): TestHttpTextParity, fake_urlopen(), _Resp, fake_urlopen()

### Community 53 - "price_for"
Cohesion: 0.22
Nodes (7): test_gemini_flash_priced_paid(), test_ollama_prices_known_free(), test_paid_model_not_free(), TestUsage, cost(), is_free(), price_for()

### Community 54 - "Orchestrator"
Cohesion: 0.21
Nodes (5): Orchestrator, score_case(), _mock_http_json(), _mock_http_text(), TestLiveFlow

### Community 55 - "official.py"
Cohesion: 0.30
Nodes (5): _matches(), official_context(), official_scores(), _records(), TestIssuerRecencyGate

### Community 56 - "_synthetic_daily"
Cohesion: 0.24
Nodes (3): _synthetic_daily(), TestComposite, TestMarket

### Community 57 - ".gather"
Cohesion: 0.18
Nodes (3): ScoutAgent, 5.1 Concurrency + rate limiting (D2) — the core upgrade, load_cik_map()

### Community 58 - "Home.md"
Cohesion: 0.27
Nodes (3): Pages, Quick Start, SECFEDCLAW v0.2 — Project Wiki

### Community 59 - "TestSocialIntelScoring"
Cohesion: 0.24
Nodes (4): _daily(), _f(), _fetches(), TestSocialIntelScoring

### Community 60 - "coordination.py"
Cohesion: 0.27
Nodes (4): content_fingerprint(), _norm_tokens(), _shingles(), TestContentFingerprint

### Community 61 - "SECFEDCLAW — System Review (2026-07)"
Cohesion: 0.22
Nodes (9): 1. Human-Centered Design (examiner UX), 2. Architecture & Engineering, 3. Data Sources / Engineering / Data Science, 4. Entity Resolution (+ UI), Improvement roadmap (discrete, tested PRs), SECFEDCLAW — System Review (2026-07), Wave 1 — delivered, Wave 3 — delivered (with the Wave-5 backtest de-circularization it depends on) (+1 more)

### Community 62 - "Polygon Flat Files Integration"
Cohesion: 0.20
Nodes (10): Architecture, Connection Modes, Credentials, Data Format, Integration with Scoring Engine, Overview, Polygon Flat Files Integration, SigV4 Signing (+2 more)

### Community 63 - "default_prober"
Cohesion: 0.36
Nodes (10): default_prober(), finra(), flatfiles(), fmp(), polygon(), reddit(), sec(), stocktwits() (+2 more)

### Community 64 - "record"
Cohesion: 0.29
Nodes (6): TestLLMPathRecordsUsage, test_summary_paid_free_split(), _by_day(), load(), record(), summary()

### Community 65 - "Architecture Overview"
Cohesion: 0.22
Nodes (9): Agentic Pipeline, Architecture Overview, Connection Modes, Currently Wired, Data Sources, Feature Modules, Output Artifacts, Scoring Engine (scoring_v2.py) (+1 more)

### Community 66 - "Multi-Platform Social Signals"
Cohesion: 0.22
Nodes (9): Credentials, Deduplication, Engagement Metrics, Evidence Gaps (documented), Multi-Platform Social Signals, Overview, Platform Coverage, Post Normalization (+1 more)

### Community 67 - "social_features"
Cohesion: 0.22
Nodes (6): Issuer-Specific Detection, Promotional Term Detection, Social Features (`features/social.py`), social_features(), TestIssuerSpecificWired, TestFeatures

### Community 68 - "normalize_posts"
Cohesion: 0.36
Nodes (4): Testing, normalize_posts(), TestDiscordNormalize, TestNormalize

### Community 69 - "CLI Reference"
Cohesion: 0.22
Nodes (9): Backtest / Calibration, CLI Reference, Daily Run + Monitoring, Dashboard, EDGAR Daily-Diff Pipeline, Full Pipeline (one command), Historical Flat-File Replay, Multi-Ticker Scan (+1 more)

### Community 70 - "Running the System"
Cohesion: 0.22
Nodes (9): Environment Variables, Live Mode (default), Offline / Degraded, Operational Modes, Output Files, Prerequisites, Replay Mode, Running the System (+1 more)

### Community 71 - "coordination_score"
Cohesion: 0.22
Nodes (7): coordination_score(), 13. Review-priority model + calibration ledger (implemented — `model.py`, `ledger.py`, `train_model.py`, `label_cases.py`), 1. Review findings (what prompted this), Components, Learned feature importances, Performance, Training data

### Community 72 - "ledger.py"
Cohesion: 0.42
Nodes (5): add_label(), label_to_y(), load_labels(), summary(), to_xy()

### Community 73 - "SECFEDCLAW — Quick Demo Narrative (~2–3 min)"
Cohesion: 0.25
Nodes (7): 0. Cold open — Overview (~25s), 1. Entities — the differentiator (~50s) ← spend the most time here, 2. A package — evidence + custody + the loop (~40s) — Packages tab, open the top card, 3. Network — coordination, visualized (~20s), 4. Status — operationally honest (~20s), Close (~15s), SECFEDCLAW — Quick Demo Narrative (~2–3 min)

### Community 74 - "LLM cost fix + SRE observability dashboard"
Cohesion: 0.25
Nodes (7): 1. LLM cost fix — `usage.py`, 2. Per-agent performance — `agents.py` + `scan.py`, Data flow, Goal, LLM cost fix + SRE observability dashboard, Out of scope, Testing

### Community 75 - "social_scores"
Cohesion: 0.25
Nodes (5): Scoring Integration, Sentiment → Coordination Nudge, Social Scores, social_scores(), TestSocial

### Community 76 - "coordination_features"
Cohesion: 0.32
Nodes (5): coordination_features(), find(), union(), _jaccard(), TestCoordination

### Community 79 - "14. Going live (replay → live)"
Cohesion: 0.29
Nodes (7): 14. Going live (replay → live), Daily digest (`notify.py`), Deploy on AWS (EC2), Deploy with Docker, LLM via AWS Bedrock (no API keys, instance-role auth), Schedule a daily live run (`daily.py`, `deploy/`), View / publish the dashboard (`serve.py`)

### Community 80 - "Monitoring"
Cohesion: 0.33
Nodes (6): Daily run summary fields, Health check commands, Key indicators, Log locations, Monitoring, Troubleshooting

### Community 81 - "Historical Replay (historical.py)"
Cohesion: 0.33
Nodes (6): CLI, Historical Replay (historical.py), Limitations, Output, Purpose, Validated Performance

### Community 82 - "Training (`train_model.py`)"
Cohesion: 0.33
Nodes (6): Abstention, Bootstrap Strategy, CLI, Output, Training (`train_model.py`), Validation

### Community 83 - "Authorized Social Import (`social_import.py`)"
Cohesion: 0.33
Nodes (6): API, Authorized Social Import (`social_import.py`), Credentials, Integration, Lawful-Authorization Boundary, Supported Formats

### Community 85 - ".search"
Cohesion: 0.40
Nodes (4): test_search_falls_back_to_firecrawl(), test_search_gemini_default_without_key_skips_sgai(), test_search_local_ollama_needs_no_key(), test_search_openai_model_without_key_skips_sgai()

### Community 86 - "Security & responsible-use notes"
Cohesion: 0.40
Nodes (4): Credentials, Reporting, Scope & operating boundary (WATCH-only), Security & responsible-use notes

### Community 93 - "Architecture"
Cohesion: 0.50
Nodes (4): Architecture, Concurrency / Playwright safety, `connectors.py` refactor, LLM config (OpenRouter, OpenAI-compatible)

### Community 96 - "0. Quickstart"
Cohesion: 0.67
Nodes (3): 0. Quickstart, Local install & development, Run it the way you'll demo it

## Knowledge Gaps
- **18 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `build_package()` connect `build_package` to `backtest.py`, `FlatFilesClient`, `test_social_intel_llm.py`, `model.py`, `Per-Security-Class Calibrated Thresholds`, `edgar.py`, `social_import.py`, `json`, `market.py`, `.__init__`, `_parse_openinsider`, `enforcement.py`, `official.py`, `_synthetic_daily`, `TestSocialIntelScoring`, `Polygon Flat Files Integration`, `social_features`, `normalize_posts`, `coordination_score`, `social_scores`, `coordination_features`, `._f`, `._f`?**
  _High betweenness centrality (0.078) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `DataConnector` (e.g. with `Orchestrator` and `ScoutAgent`) actually correct?**
  _`DataConnector` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Should `DataConnector` be split into smaller, more focused modules?**
  _Cohesion score 0.06865401987353206 - nodes in this community are weakly interconnected._
- **Why does `DataConnector` connect `DataConnector` to `ScrapeProvider`, `.__init__`, `connectors.py`, `edgar_pipeline.py`, `json`, `Orchestrator`, `.gather`, `scan.py`?**
  _High betweenness centrality (0.073) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `build_package()` (e.g. with `2. Governing principles (unchanged)` and `Integration with Scoring Engine`) actually correct?**
  _`build_package()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Should `esc` be split into smaller, more focused modules?**
  _Cohesion score 0.050949367088607596 - nodes in this community are weakly interconnected._
- **Why does `ScrapeProvider` connect `ScrapeProvider` to `DataConnector`, `connectors.py`, `._sgai_scrape`, `ScrapeResult`, `.search`, `test_scrape_provider.py`, `fake_sgai`?**
  _High betweenness centrality (0.055) - this node is a cross-community bridge._