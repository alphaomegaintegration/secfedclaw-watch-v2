# SECFEDCLAW — Quick Demo Narrative (~2–3 min)

A short spoken walkthrough for a live demo against the running dashboard
(`http://127.0.0.1:8787/dashboard_v2.html?token=…`). Grounded in the current
scan's actual data. For the full briefing use `SEC_PRESENTATION.md`.

**Order of the demo:** Overview → **Entities (lead here — the differentiator)** →
Packages → Network → Status. Entities is the strongest live beat, so open there.

---

## 0. Cold open — Overview (~25s)

> "An analyst hunting coordinated pump-and-dumps today works one name at a time —
> memory and Ctrl-F across filings, market data, and social. The signals exist,
> but they live in eight places and nobody has the hours to fuse them. SECFEDCLAW
> fuses them every day over a whole universe and returns a ranked, evidence-cited,
> **non-accusatory** review queue. Notice the banner on every screen: this
> produces *review priority*, never accusations. It decides what to look at
> first — and shows its work."

Point at the top of the ranked queue:
> "Today, twelve names cleared the corroboration bar into MEDIUM — PSNYW, XNCR,
> AMC, GRML, LEDS and others — each with two-to-four independent evidence
> families. The analyst starts at the top and stops when their hour is up."

*(Fallback for a quiet tape when everything's LOW: "nothing clears the bar
today — that's the system being conservative, not broken" — then go to Entities.)*

## 1. Entities — the differentiator (~50s) ← spend the most time here

> "This is what pump-and-dump detection actually hinges on: the same actors
> recurring across *different* tickers. Most tools look at one ticker in
> isolation and miss it. Here's the cross-run entity graph SECFEDCLAW builds from
> the evidence it already collects."

Point to the recurring-entities table:
> "Look at the top row: a single promoter **account** — `962572` — posting across
> **six different tickers** today: AMWL, BNRG, CNF, LEDS, LVLU, XNCR. And the same
> promotional **script**, 'Top Gainers PT2', reused across four of them. That's
> one actor running the same play on a basket of names. No single-ticker view
> catches that — this is cross-ticker actor resolution, built from the evidence
> the scanner already collects, updated on today's live scan."

**The connective beat (this is the one that lands):**
> "Now watch this — LEDS, LVLU and XNCR are also sitting in our MEDIUM review
> queue. So this isn't an abstract graph: the coordination flagging those names
> for review is being *driven by an actor we've now seen on five others*. That's
> the difference between 'this ticker looks noisy' and 'this is a campaign.'"

*(Also worth a mention: `tapeboard.com` across CGTL/GRML/NAMI/WBX, and the
`$AMC $BTC $ETH $DOGE $GME 🥳` cashtag script spanning AMC + GME.)*

## 2. A package — evidence + custody + the loop (~40s) — Packages tab, open the top card

> "This is the unit of work: one ticker, one package. It doesn't hand the analyst
> a verdict — it hands them the *questions*, the coordination evidence, the
> price-and-volume anomaly, and" — *expand the drill-down* — "the limitations it
> admits to, plus a custody trail: every raw artifact with a SHA-256 hash. The
> priority band means 'look here first,' not 'this is manipulation.' And the
> analyst labels the outcome right here" — *point to the label row* — "which
> trains the advisory model. Note the model says how many *real* labels it's seen
> — it doesn't pretend to be more calibrated than it is."

## 3. Network — coordination, visualized (~20s)

> "The same coordination evidence as a graph — hover any ticker to trace its
> clusters, the platforms, and the families that corroborate it."

## 4. Status — operationally honest (~20s)

> "And it's honest about itself: live-vs-replay per source, per-agent latency,
> and metered cost — a full scan runs in cents. Nothing here is a black box."

## Close (~15s)

> "So: it collapses time-to-review from one-name-at-a-time to a daily ranked
> queue; every score is defensible down to a hashed artifact; it recognizes
> actors *across* tickers, not just within one; and it respects the WATCH line by
> construction — evidence, not accusation. It doesn't replace the analyst. It
> gives them the first hour of their day back, pointed at the right names."

---

**Prep checklist (day of):**
- `python3 scan.py --live --discover 25` in the morning for a fresh queue + entities.
- Confirm the server is up and grab the token: `python3 -u serve.py` (or check the log).
- Have the **Entities** tab open first — it's the beat that lands.
- Access URL: `http://127.0.0.1:8787/dashboard_v2.html?token=<token>`
