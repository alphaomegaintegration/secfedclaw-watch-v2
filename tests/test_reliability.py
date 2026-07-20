#!/usr/bin/env python3
"""Wave-1 reliability & integrity fixes: atomic writes, _http_text retry parity,
scoped live->replay, concurrent-append safety, and a PII regression guard."""
import json
import sys
import threading
import unittest
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import io_util
import connectors
import usage


class TestAtomicWrite(unittest.TestCase):
    def test_writes_and_overwrites(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "sub" / "x.json"          # parent doesn't exist yet
            io_util.atomic_write(p, '{"a":1}')
            self.assertEqual(json.loads(p.read_text()), {"a": 1})
            io_util.atomic_write(p, '{"a":2}')        # overwrite
            self.assertEqual(json.loads(p.read_text()), {"a": 2})
            # no .tmp litter left behind
            self.assertEqual(list(p.parent.glob(".*tmp")), [])

    def test_reader_never_sees_partial(self):
        # atomic_write must replace, never truncate-in-place: an old reader sees
        # the full old content right up until the atomic swap.
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "q.json"
            io_util.atomic_write(p, '{"n":1}')
            before = p.read_text()
            io_util.atomic_write(p, '{"n":2}')
            self.assertIn(before, ('{"n":1}',))
            self.assertEqual(json.loads(p.read_text())["n"], 2)


class TestHttpTextParity(unittest.TestCase):
    """_http_text must retry transient URLErrors, like _http_json (it carries
    SEC/Nasdaq/Reddit-RSS feeds)."""
    def test_retries_transient_then_succeeds(self):
        c = connectors.DataConnector.__new__(connectors.DataConnector)
        c.timeout = 1; c._live_ok = None; c._http_attempts = 3; c._http_backoff = 0.0
        calls = {"n": 0}

        class _Resp:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b"hello"

        def fake_urlopen(req, timeout=None):
            calls["n"] += 1
            if calls["n"] < 3:
                raise urllib.error.URLError("transient")
            return _Resp()

        orig = connectors.urllib.request.urlopen
        connectors.urllib.request.urlopen = fake_urlopen
        try:
            status, text = c._http_text("https://www.sec.gov/x")
        finally:
            connectors.urllib.request.urlopen = orig
        self.assertEqual(status, 200)
        self.assertEqual(text, "hello")
        self.assertEqual(calls["n"], 3)


class TestLiveOkScoped(unittest.TestCase):
    """A single source fetch failure must NOT poison the whole run's live flag."""
    def test_source_failure_does_not_flip_global_live(self):
        c = connectors.DataConnector.__new__(connectors.DataConnector)
        c.timeout = 1; c._live_ok = None; c._http_attempts = 1; c._http_backoff = 0.0

        def always_fail(req, timeout=None):
            raise urllib.error.URLError("down")

        orig = connectors.urllib.request.urlopen
        connectors.urllib.request.urlopen = always_fail
        try:
            status, data = c._http_json("https://stocktwits.example/api")
        finally:
            connectors.urllib.request.urlopen = orig
        self.assertEqual((status, data), (None, None))     # that source falls back
        self.assertIsNone(c._live_ok)                      # global flag untouched


class TestConcurrentAppend(unittest.TestCase):
    """Concurrent JSONL appends under the threaded server must not corrupt lines."""
    def test_usage_record_is_thread_safe(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            led = Path(td) / "u.jsonl"
            N = 60

            def worker(i):
                usage.record("ollama/x", 1, 1, component=f"c{i}", path=led)

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
            for t in threads: t.start()
            for t in threads: t.join()

            lines = [l for l in led.read_text().splitlines() if l.strip()]
            self.assertEqual(len(lines), N)
            for l in lines:               # every line is a complete, parseable row
                json.loads(l)

    def test_both_ledgers_have_append_lock(self):
        import ledger
        self.assertTrue(hasattr(usage, "_APPEND_LOCK"))
        self.assertTrue(hasattr(ledger, "_APPEND_LOCK"))


class TestNoPII(unittest.TestCase):
    """Regression guard: no personal email / account creds in source."""
    def test_no_personal_email_in_connectors(self):
        src = (ROOT / "connectors.py").read_text()
        self.assertNotIn("robert.david.brown@gmail.com", src)
        self.assertNotIn("browngeek666", src)
        self.assertNotIn("gmail.com", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestGroupedDailyTradingDay(unittest.TestCase):
    """grouped-daily must walk back past weekend/holiday empties to a real
    trading day, instead of caching an empty set as a live success."""
    def test_walks_back_past_empty_day(self):
        c = connectors.DataConnector.__new__(connectors.DataConnector)
        c._live_ok = True
        c.env = {"POLYGON_API_KEY": "k"}
        calls = {"n": 0}

        def fake_http_json(url, headers=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return 200, {"resultsCount": 0, "results": []}      # weekend/holiday
            return 200, {"resultsCount": 2, "results": [{"T": "AAA"}, {"T": "BBB"}]}

        c._http_json = fake_http_json
        f = c.polygon_grouped_daily()
        self.assertEqual(f.mode, "live")
        self.assertEqual(calls["n"], 2)                              # skipped the empty day
        self.assertEqual((f.data or {}).get("resultsCount"), 2)
