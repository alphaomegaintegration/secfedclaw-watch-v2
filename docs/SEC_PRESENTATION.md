# SECFEDCLAW — Presentation Script (SEC briefing)

A spoken walkthrough script for presenting SECFEDCLAW to an SEC audience
(enforcement analysts, market-surveillance staff, and their technical
reviewers). It is written to be **driven live against the dashboard** — each
section names the tab to open and what to click, with the talk track beneath.

- **Audience:** SEC enforcement / market-abuse surveillance staff + technical reviewers.
- **Format:** ~20–25 min live demo + 10 min Q&A. Cut the *Operations* and
  *Learning* sections if you only have 15 minutes.
- **Setup before you walk in:** run a live scan over a universe with promotable
  (thin / micro-cap) names so the Packages tab shows at least one MEDIUM+ case —
  `python scan.py --live --discover 25`. Confirm the dashboard is served
  (`python serve.py`) and the Status tab reads mostly *live*. Have this script
  and the *SEC case studies* tab open in a second window.

> **The one rule that governs everything you'll say:** SECFEDCLAW produces
> **review priority, never accusations.** It surfaces evidence and ranks where a
> human should look first. It does not assert fraud, generate trading signals,
> or take any enforcement action. Say this early, and let the product prove it.

---

## 0. Cold open (60 seconds) — the problem, in their language

> "An analyst who suspects a coordinated pump-and-dump today works the way they
> worked ten years ago: memory, plus Ctrl-F across static case files, filings,
> and spreadsheets. There is no cross-source, cross-case way to ask *'where is
> coordinated promotion lining up with an abnormal market move and an issuer
> event — right now?'* The signals exist, but they live in eight different
> places and nobody has the hours to fuse them by hand.
>
> SECFEDCLAW does that fusion every day, over a whole ticker universe, and hands
> the analyst a ranked, evidence-cited, **non-accusatory** review queue. It
> doesn't decide anything. It decides *what to look at first* — and shows its
> work."

Pause. Then: "Let me show you, against live data."

---

## 1. What it is (90 seconds) — Tab: **Overview**

**Open the Overview tab. Point to the banner first.**

> "Notice the banner at the top of every screen: *'WATCH ceiling — produces
> review-priority context for authorized human review only. Does not assert
> fraud, recommend trades, freeze assets, or initiate legal process.'* That
> ceiling is not a disclaimer we bolted on — it's enforced in the code, in
> every agent, on every output. I'll show you where."

> "In one sentence: SECFEDCLAW fuses **social, market, official (SEC / FINRA /
> Nasdaq), and market-microstructure** signals into a single calibrated
> review-priority score per ticker, with the evidence and the plausible benign
> explanations attached to every score."

**Point to the priority bands / counts on Overview.**

> "Everything is ranked into four bands — LOW, MEDIUM, HIGH, CRITICAL. The
> analyst starts at the top and stops when their time runs out. That's the whole
> value proposition: **reduce time-to-review**, with a defensible trail behind
> every ranking."

---

## 2. A real review package (5 minutes) — Tab: **Packages** — *the core of the demo*

**Open Packages. Open the highest-priority card (cards ≥ MEDIUM are expanded by default).**

> "This is the unit of work the analyst actually consumes — one ticker, one
> review package. Walk through it with me, because this is where the WATCH
> boundary becomes concrete."

**Click into the drill-down sections, narrating each:**

1. **Review questions** —
   > "It doesn't tell the analyst a conclusion. It hands them the *questions* a
   > reviewer should answer — framed as questions, on purpose."

2. **Coordination evidence** —
   > "Here's *why* it flagged: near-duplicate promotional posts clustered across
   > platforms, shared domains, synchronized bursts. Each item is evidence, not
   > a verdict."

3. **Market anomaly basis** —
   > "The price and volume z-scores against the name's own baseline — and note
   > it requires **both** price *and* volume to be abnormal, calibrated to the
   > name's liquidity class. A thin micro-cap and a mega-cap are not held to the
   > same yardstick."

4. **Limitations & gaps** —
   > "This is the section that should earn your trust. The tool **states what it
   > could not see** — hidden beneficial ownership, off-platform coordination,
   > data it couldn't fetch live. It does not paper over its blind spots."

5. **Custody & raw artifacts** —
   > "Every external response is persisted and **SHA-256 hashed**. You can trace
   > any number on this screen back to the raw artifact it came from. The package
   > tells you whether each source was fetched **live** this run or replayed from
   > custody — so the provenance is never ambiguous."

6. **WATCH boundary** —
   > "And it restates, per package, what it is *not* claiming."

**Land the point:**

> "So an analyst can open this, follow the evidence down to the raw hashed
> artifact, answer the review questions, and either escalate through their own
> lawful process or dismiss it — and there's an audit trail for whichever they
> choose."

---

## 3. How the evidence is built (3 minutes) — Tab: **Agents** (and **How it works**)

**Open the Agents tab. Point to the five-stage pipeline.**

> "Every ticker flows through a **five-agent pipeline**, and the separation of
> duties is the integrity story:
>
> - **Scout** pulls the data feeds — live where possible, replay from custody
>   otherwise — and records health and custody for each.
> - **Analyst** normalizes, engineers features, and runs the scoring algorithms.
> - **Adversary** red-teams the result. Critically, the Adversary **can only
>   lower a priority or add caveats — never raise it.** The system is structurally
>   biased *against* over-flagging.
> - **Explainer** writes the plain-language summary.
> - **Packager** assembles the custody-preserving WATCH package.
>
> No agent can trade, contact anyone, freeze anything, or exceed the WATCH
> ceiling. That's enforced as a role boundary, not a guideline."

**Optional — open How it works** for the data-source inventory:

> "Under the hood that's social platforms, market-data providers, and official /
> regulatory feeds — SEC EDGAR, FINRA, Nasdaq, SEC litigation — fused per ticker."

---

## 4. The scoring discipline (2 minutes) — Tab: **Methodology**

**Open Methodology. Point to the bands and the corroboration rule.**

> "Two design choices matter to a regulator:
>
> 1. **Corroboration gating.** A case cannot reach HIGH or CRITICAL on a single
>    family of evidence. It needs **two or more independent corroborating
>    families** — say, coordinated promotion *and* a confirmed abnormal market
>    move. Social chatter alone is capped. This is deliberately conservative.
>
> 2. **Benign explanations reduce the score.** A real catalyst — earnings, an
>    approval, a contract — is treated as exculpatory and lowers the band. The
>    system is built to *talk itself down*, not up."

**Point to the 'What it does NOT do' card:**

> "No fraud determination. No trading signal. No contact with regulators,
> brokers, issuers, or investors. No asset freeze. No legal process. Findings
> are bounded by the artifacts available at runtime and **require human
> adjudication.**"

---

## 5. Credibility — it speaks your case law (2 minutes) — Tab: **SEC case studies**

**Open SEC case studies. This is the trust-builder for this specific audience.**

> "We validated the thresholds against real SEC matters — these are public
> actions, and we assert no new findings about them. For each, we show which
> SECFEDCLAW thresholds *would* have fired and why:
>
> - **Coordinated social influencers** — SEC 2022-221
> - **Single promoter, penny stock** — SEC 2021-214
> - **Newsletter micro-cap promotion** — SEC 2014-256
> - **Offshore nominee pump-and-dump** — SEC 2022-62
>
> The point isn't that we'd have 'caught' these — it's that the patterns your
> enforcement actions describe map cleanly onto the evidence families this tool
> ranks on. We're surfacing the same tells, earlier, across the whole universe."

---

## 6. Coordination, visualized (90 seconds) — Tab: **Network**

**Open Network. Hover over the largest / highest-scoring ticker node.**

> "This is the coordination evidence as a graph — tickers, the platforms they're
> promoted on, near-duplicate clusters, shared domains, and corroborating
> families. Hover any node" — *do it* — "and you can inspect it and trace its
> connections. It's the same evidence the scoring engine uses, made legible — so
> an analyst can see a coordinated cluster at a glance instead of reading a
> table."

---

## 7. Operational maturity (2 minutes — optional) — Tabs: **Status**, **LLM cost**, **Runs**

**Open Status (the SRE view).**

> "This is not a prototype that runs on someone's laptop and hopes. The Status
> tab is a live operations view — which of our data integrations are reachable,
> per-source success rates, per-agent latency, error rates, and our preflight
> readiness verdict before every live run. If a source is down, you see it; the
> package tells you it fell back to replay. **We never silently sell you stale
> data as live.**"

**Open LLM cost.**

> "And we track cost-to-run transparently — every model call is metered by model
> and by component. A daily scan over a real universe costs cents. For a public
> agency that has to account for spend, there are no surprises."

---

## 8. It gets better with your judgment (90 seconds — optional) — Tab: **Learning**

> "There's a human-in-the-loop feedback cycle. When an analyst labels an
> outcome — *useful watch, false positive, benign-explained* — those labels
> train a model that adds an **advisory** probability to future packages. But
> note the discipline: the interpretable **rules engine always stays primary**,
> and the model **abstains until it has enough labeled evidence**. The machine
> learning assists the analyst's ranking; it never replaces the explainable
> logic or the human decision."

---

## 9. The benefit — close (90 seconds)

> "So what does SECFEDCLAW actually buy you?
>
> 1. **Time-to-review collapses.** A daily, ranked, evidence-cited queue over a
>    whole universe instead of manual, one-name-at-a-time hunting.
> 2. **Everything is defensible.** Every score cites hashed artifacts, names its
>    limitations, and lists benign explanations. It's built for the scrutiny an
>    enforcement-adjacent decision attracts.
> 3. **It respects the line your office has to respect.** WATCH-only,
>    non-accusatory, human-adjudicated — by construction, not by policy.
> 4. **It's honest about provenance and cost.** Live-vs-replay is always stated;
>    spend is metered; sources are health-checked.
>
> It doesn't try to be the analyst. It tries to give the analyst the first hour
> of their day back — pointed at the right names, with the evidence already
> assembled."

---

## 10. Anticipated Q&A — have these ready

**"Are you making fraud determinations?"**
> No. The system produces review priority and evidence only. It cannot and does
> not conclude wrongdoing — that's the WATCH ceiling, enforced in every agent.

**"What about false positives?"**
> Three structural defenses: corroboration gating (≥2 independent families for
> HIGH/CRITICAL), an Adversary stage that can *only* lower priority, and benign
> explanations that reduce the band. The system is biased against over-flagging,
> and every flag is human-adjudicated before anything happens.

**"Where does the data come from, and is it lawful to use?"**
> Public signals only — social, market data, and official SEC/FINRA/Nasdaq
> feeds. For this use it does **not** ingest any non-public order or trade data.
> Each source's response is hashed and retained for custody.

**"Can we audit a specific score?"**
> Yes — that's the custody trail. Drill down from any package to the raw,
> SHA-256-hashed artifact, and see whether it was fetched live or replayed.

**"Does the AI/ML make the decision?"**
> No. The interpretable rules engine is always primary; the learned model is an
> advisory add-on that abstains until sufficiently trained. A human always
> adjudicates.

**"What can't it see?" / "What are the limits?"**
> Hidden beneficial ownership, off-platform/private-channel coordination, and
> anything it couldn't fetch at runtime. The tool states these gaps *in each
> package* rather than hiding them. It surfaces public-market symptoms; it cannot
> substitute for lawful records access.

**"Does it work offline / on our infrastructure?"**
> Yes — it's offline-capable and provenance-preserving; the dashboard renders as
> a self-contained artifact, and runs can replay entirely from custody.

---

## Appendix — quick technical reference for the room's engineers

- **Pipeline:** Scout → Analyst → Adversary → Explainer → Packager (role-bounded; Adversary is monotonic-down only).
- **Evidence families:** market anomaly, coordination, issuer event (EDGAR daily-diff), enforcement history, social burst.
- **Bands:** LOW (<25), MEDIUM (25–49), HIGH (50–74), CRITICAL (≥75). HIGH/CRITICAL require ≥2 independent families.
- **Calibration:** liquidity-class-specific thresholds (thin micro-cap → large cap); both price AND volume z must exceed class threshold.
- **Custody:** every external response persisted + SHA-256 hashed; per-source live/replay state recorded per package.
- **Operations:** preflight readiness verdict, per-source health + success rate, per-agent latency, error rate, metered LLM cost by model/component.
- **Learning:** operator labels → gradient-boosted advisory model; abstains until enough labels; rules engine stays primary.
- **Boundary (enforced, not advisory):** no fraud finding, no trading signal, no outbound contact, no asset action, no legal process.
