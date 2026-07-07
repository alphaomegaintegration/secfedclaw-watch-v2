"""Small shared IO helpers.

`atomic_write` exists because several outputs (review_queue.json, model.json,
edgar_state.json, the daily summary, agent_status.json) are read by concurrent
processes — the threaded serve.py, a polling dashboard, the next scan. A bare
`Path.write_text` truncates-then-writes, so a reader can catch a half-written
file and raise / serve garbage. Temp-file + os.replace makes the swap atomic on
POSIX and Windows: readers see either the old file or the new one, never a
partial. run_manifest.json already used this pattern by hand; this centralizes it.
"""
from __future__ import annotations

import os
from pathlib import Path


def atomic_write(path: str | Path, text: str) -> None:
    """Write `text` to `path` atomically. The temp file is created in the same
    directory (so os.replace stays a same-filesystem atomic rename) and is
    pid-tagged so two writers never clobber each other's temp."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
    try:
        tmp.write_text(text)
        os.replace(tmp, path)
    finally:
        # If os.replace succeeded the temp is gone; this only cleans up a
        # failed write (e.g. disk full) so we don't leave .tmp litter behind.
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
