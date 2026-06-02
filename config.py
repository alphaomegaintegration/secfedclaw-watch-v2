#!/usr/bin/env python3
"""Configuration & environment loading for SECFEDCLAW v0.2.

Resolves the fed_claw root in a path-portable way (an improvement over the
hard-coded /home/ubuntu/fed_claw in production v0.1) and loads .env without
ever printing secret values.
"""
from __future__ import annotations

import os
from pathlib import Path

ALGORITHM_VERSION = "watch_score_v0.2.0"
FINDING_CEILING = "WATCH"

PROHIBITED_ACTIONS = [
    "trading_signal", "market_action", "external_escalation_without_user_approval",
    "autonomous_freeze", "legal_process", "contact_regulator", "contact_broker",
    "contact_suspected_actor", "contact_victim",
]

# Resolve root: env override > fed_claw (parent of this package) > cwd.
def fed_claw_root() -> Path:
    env_root = os.environ.get("SECFEDCLAW_ROOT")
    if env_root:
        return Path(env_root)
    # Standalone repo: data/.env root defaults to the repo directory (which
    # contains this file). Override with SECFEDCLAW_ROOT to point at an
    # existing fed_claw data tree (artifacts/, collections/) for replay.
    return Path(__file__).resolve().parent


def candidate_env_paths(root: Path) -> list[Path]:
    """Where the .env may live, in priority order."""
    return [
        root / ".env",                         # repo-local .env (recommended)
        Path.home() / ".hermes" / ".env",      # hermes production location
        root.parent / "hermes" / ".env",       # next to a checked-out hermes/
    ]


def load_env(root: Path | None = None) -> dict[str, str]:
    """Load KEY=VALUE pairs from the first .env found. Values never logged."""
    root = root or fed_claw_root()
    env: dict[str, str] = {}
    for path in candidate_env_paths(root):
        if path.exists():
            for line in path.read_text(errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
            break
    # Process env overrides file values (so users can export without editing .env).
    for k in list(env) + ["POLYGON_API_KEY", "X_BEARER_TOKEN", "TWITTER_BEARER_TOKEN", "SEC_USER_AGENT"]:
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def has_credential(env: dict[str, str], *names: str) -> bool:
    return any(bool(env.get(n)) for n in names)


# Default candidate universe for the multi-ticker scan. The scanner can also
# derive a universe dynamically from a grouped-daily market snapshot.
DEFAULT_UNIVERSE = ["AAPL", "TSLA", "AMC", "GME", "AMD", "NVDA", "ALB"]
