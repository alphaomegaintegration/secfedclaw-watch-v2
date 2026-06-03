#!/usr/bin/env python3
"""Authorized social-export importer for SECFEDCLAW v0.2 (Discord / Telegram).

IMPORTANT — lawful-authorization boundary (SOUL.md §6, §7):
This module NEVER scrapes private Discord/Telegram channels and performs NO
unauthorized access. It only ingests data the operator has LAWFULLY obtained and
PLACED in the import directory — e.g. an official Telegram Desktop export, a
Discord data export / DiscordChatExporter dump of a channel the operator owns or
lawfully participates in, or a generic JSONL the operator curated. Ingestion is
OFF unless the operator opts in (`SECFEDCLAW_AUTHORIZED_SOCIAL=1`) AND drops
files into the import dir. This keeps private-channel data behind explicit human
authorization, exactly as required for enforcement-adjacent work.

Imported messages are normalized into the same post schema used by
`features/social.py`, so they flow through the coordination graph, social split,
and sentiment/cross-platform features automatically.
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import fed_claw_root  # noqa: E402

IMPORT_DIRNAME = "social_import"  # under the package dir


def import_dir() -> Path:
    return Path(__file__).resolve().parent / "out" / IMPORT_DIRNAME


def authorized() -> bool:
    """Opt-in gate. Must be explicitly enabled by the operator."""
    return os.environ.get("SECFEDCLAW_AUTHORIZED_SOCIAL", "").strip() in ("1", "true", "yes")


def _txt(v: Any) -> str:
    if isinstance(v, list):  # Telegram text can be a list of segments
        return "".join(seg.get("text", "") if isinstance(seg, dict) else str(seg) for seg in v)
    return str(v or "")


def parse_telegram_export(data: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for m in (data.get("messages") or []):
        if not isinstance(m, dict) or m.get("type") not in (None, "message"):
            continue
        out.append({
            "platform": "telegram", "id": f"tg_{m.get('id')}",
            "text": _txt(m.get("text")), "created_at": m.get("date"),
            "author_id": str(m.get("from_id") or m.get("from") or ""),
            "sentiment": None, "engagement": 0.0,
            "channel": data.get("name"),
        })
    return out


def parse_discord_export(data: dict[str, Any]) -> list[dict[str, Any]]:
    chan = (data.get("channel") or {}).get("name") if isinstance(data.get("channel"), dict) else None
    out = []
    for m in (data.get("messages") or []):
        if not isinstance(m, dict):
            continue
        author = m.get("author") or {}
        rxn = sum(int(r.get("count") or 0) for r in (m.get("reactions") or []) if isinstance(r, dict))
        out.append({
            "platform": "discord", "id": f"dc_{m.get('id')}",
            "text": _txt(m.get("content")), "created_at": m.get("timestamp"),
            "author_id": str(author.get("id") or author.get("name") or ""),
            "sentiment": None, "engagement": float(rxn),
            "channel": chan,
        })
    return out


def parse_jsonl(text: str) -> list[dict[str, Any]]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        out.append({
            "platform": d.get("platform", "imported"), "id": str(d.get("id") or len(out)),
            "text": _txt(d.get("text") or d.get("body")), "created_at": d.get("created_at"),
            "author_id": str(d.get("author_id") or d.get("author") or ""),
            "sentiment": d.get("sentiment"), "engagement": float(d.get("engagement") or 0),
            "channel": d.get("channel"),
        })
    return out


def parse_csv(text: str) -> list[dict[str, Any]]:
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        out.append({
            "platform": row.get("platform", "imported"), "id": str(row.get("id") or len(out)),
            "text": row.get("text") or row.get("body") or "", "created_at": row.get("created_at"),
            "author_id": str(row.get("author_id") or row.get("author") or ""),
            "sentiment": (row.get("sentiment") or None), "engagement": float(row.get("engagement") or 0),
            "channel": row.get("channel"),
        })
    return out


def _parse_file(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text(errors="replace")
    if path.suffix == ".jsonl":
        return parse_jsonl(raw)
    if path.suffix == ".csv":
        return parse_csv(raw)
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if isinstance(data, dict) and "messages" in data:
        # Telegram exports have "type"/"from_id"; Discord have "author"/"timestamp"
        msgs = data["messages"]
        if msgs and isinstance(msgs[0], dict) and ("author" in msgs[0] or "timestamp" in msgs[0]):
            return parse_discord_export(data)
        return parse_telegram_export(data)
    if isinstance(data, list):
        return parse_jsonl("\n".join(json.dumps(x) for x in data))
    return []


def load_authorized(ticker: str | None = None, directory: Path | None = None) -> list[dict[str, Any]]:
    """Load + normalize operator-authorized imports. Returns [] unless opted in."""
    if not authorized():
        return []
    d = directory or import_dir()
    if not d.exists():
        return []
    posts: list[dict[str, Any]] = []
    for p in sorted(d.iterdir()):
        if p.is_file() and p.suffix in (".json", ".jsonl", ".csv"):
            posts.extend(_parse_file(p))
    if ticker:
        up = ticker.upper()
        posts = [pt for pt in posts if up in (pt.get("text") or "").upper()
                 or f"${up}" in (pt.get("text") or "").upper()]
    return posts


def status() -> dict[str, Any]:
    d = import_dir()
    files = [p.name for p in d.iterdir() if p.is_file()] if d.exists() else []
    return {"authorized": authorized(), "import_dir": str(d), "files_present": files,
            "note": "Set SECFEDCLAW_AUTHORIZED_SOCIAL=1 and place lawful exports here. "
                    "No autonomous private-channel access is performed."}
