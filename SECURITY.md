# Security & responsible-use notes

## Credentials
This project reads API credentials from a `.env` file at runtime (Polygon, X,
SEC user-agent, FINRA, etc.). **No credential values are stored in this
repository.** `.env`, history files, tokens, and `*.db`/custody artifacts are
excluded by `.gitignore`. Never commit secrets; if one is committed, rotate it
immediately and scrub history.

## Scope & operating boundary (WATCH-only)
SECFEDCLAW produces **review-priority** signals for authorized human review.
It is governed by a strict operating boundary:

- It does **not** produce trading signals or recommend market actions.
- It does **not** conclude fraud, manipulation, or any legal violation.
- It does **not** contact regulators, brokers, victims, or suspected actors.
- It does **not** freeze assets or initiate legal process.
- Findings are capped at **WATCH** (LOW / MEDIUM / HIGH / CRITICAL_REVIEW), and
  HIGH/CRITICAL only mean "urgent human review of the evidence package."

Outputs include coordination/social features that have high false-positive
rates by design; all clusters are emitted for human verification. Any external
use or escalation requires separate lawful human authorization.

## Reporting
Open a private security advisory or contact the repository owner directly.
