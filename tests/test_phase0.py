#!/usr/bin/env python3
"""Phase 0 tests: concurrency layer + run-manifest + scan parity.

Covers the ARCHITECTURE_PLAN.md Phase 0 acceptance bar:
  - concurrency.py units (RateLimiter, retry, run_concurrent) — new behavior
  - scan.run_scan() emits a run-manifest — new behavior
  - review_queue.json is byte-identical (modulo run-clock-volatile fields) to
    the pre-refactor golden — proves concurrent fetching did NOT change results.

Deterministic / stdlib unittest. Runs in replay mode (no network).
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "parity_review_queue.json"


def _normalize(queue: dict) -> dict:
    """Drop run-clock-volatile fields so the comparison isolates computed results."""
    for r in queue.get("review_queue", []):
        r.pop("package_path", None)   # embeds generated_utc timestamp
        r.pop("package_sha256", None)  # hashes the timestamped package
    return queue


class _FakeFetch:
    """A minimal Fetch-like stub: every source is 'unavailable'."""

    def __init__(self, name: str):
        self.name = name
        self.mode = "unavailable"
        self.status = None
        self.data = None

    def ok(self) -> bool:
        return False


class _FakeConnector:
    """Deterministic, machine-independent connector for the parity test.

    The real DataConnector reads gitignored, __file__-relative artifacts (e.g.
    out/edgar/issuer_features_<T>.json) that exist on a dev box but never on CI,
    which made an end-to-end golden non-portable. This stub returns the same
    'unavailable' fetch for every source on every machine, so the parity test
    isolates exactly what Phase 0 changed — the concurrent fan-out in
    ScoutAgent.gather() — without depending on local data.
    """

    def __init__(self):
        self.env = {}

    def live_available(self) -> bool:
        return False

    def sec_company_tickers(self) -> _FakeFetch:
        return _FakeFetch("sec_company_tickers")  # ok()==False → no CIK map mutation

    def __getattr__(self, name):
        # Any source method (polygon_*, x_recent, edgar_issuer_features, ...) →
        # a thunk returning a deterministic unavailable fetch.
        return lambda *a, **k: _FakeFetch(name)


class TestConcurrencyUtils(unittest.TestCase):
    def test_run_concurrent_preserves_spec_order(self):
        import concurrency
        # Thunks finish out of order; result dict must follow spec order, not completion.
        specs = [
            ("a", lambda: "A"),
            ("b", lambda: "B"),
            ("c", lambda: "C"),
        ]
        out = concurrency.run_concurrent(specs, max_workers=4)
        self.assertEqual(list(out.keys()), ["a", "b", "c"])
        self.assertEqual(out, {"a": "A", "b": "B", "c": "C"})

    def test_run_concurrent_propagates_exceptions(self):
        import concurrency

        def boom():
            raise ValueError("boom")

        with self.assertRaises(ValueError):
            concurrency.run_concurrent([("ok", lambda: 1), ("bad", boom)], max_workers=2)

    def test_retry_succeeds_after_transient_failures(self):
        import concurrency
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise TimeoutError("transient")
            return "ok"

        result = concurrency.retry(flaky, attempts=3, retry_on=(TimeoutError,),
                                   sleep=lambda _s: None)
        self.assertEqual(result, "ok")
        self.assertEqual(calls["n"], 3)

    def test_retry_raises_after_exhausting_attempts(self):
        import concurrency
        calls = {"n": 0}

        def always_fail():
            calls["n"] += 1
            raise TimeoutError("nope")

        with self.assertRaises(TimeoutError):
            concurrency.retry(always_fail, attempts=3, retry_on=(TimeoutError,),
                              sleep=lambda _s: None)
        self.assertEqual(calls["n"], 3)

    def test_retry_does_not_catch_unlisted_exceptions(self):
        import concurrency
        calls = {"n": 0}

        def wrong_error():
            calls["n"] += 1
            raise KeyError("different")

        with self.assertRaises(KeyError):
            concurrency.retry(wrong_error, attempts=3, retry_on=(TimeoutError,),
                              sleep=lambda _s: None)
        self.assertEqual(calls["n"], 1)  # not retried

    def test_ratelimiter_throttles_beyond_burst(self):
        import concurrency
        clock = {"t": 0.0}
        slept = []

        def now():
            return clock["t"]

        def sleep(s):
            slept.append(s)
            clock["t"] += s

        rl = concurrency.RateLimiter(rate_per_sec=10.0, burst=1, now=now, sleep=sleep)
        self.assertEqual(rl.acquire(), 0.0)        # first token free (burst=1)
        wait = rl.acquire()                         # bucket empty → must wait ~1/10s
        self.assertAlmostEqual(wait, 0.1, places=6)
        self.assertEqual(len(slept), 1)
        self.assertAlmostEqual(slept[0], 0.1, places=6)


class TestHttpRetry(unittest.TestCase):
    def test_http_json_retries_transient_url_errors(self):
        import urllib.error
        import connectors

        c = connectors.DataConnector.__new__(connectors.DataConnector)  # skip env/init
        c.timeout = 1
        c._live_ok = None
        c._http_attempts = 3
        c._http_backoff = 0.0  # no real sleeping in the test

        calls = {"n": 0}

        class _FakeResp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"ok": true}'

        def fake_urlopen(req, timeout=None):
            calls["n"] += 1
            if calls["n"] < 3:
                raise urllib.error.URLError("transient")
            return _FakeResp()

        orig = connectors.urllib.request.urlopen
        connectors.urllib.request.urlopen = fake_urlopen
        try:
            status, data = c._http_json("https://api.polygon.io/v1/x")
        finally:
            connectors.urllib.request.urlopen = orig

        self.assertEqual(status, 200)
        self.assertEqual(data, {"ok": True})
        self.assertEqual(calls["n"], 3)  # failed twice, succeeded on 3rd

    def test_http_json_does_not_retry_http_error_status(self):
        import urllib.error
        import connectors

        c = connectors.DataConnector.__new__(connectors.DataConnector)
        c.timeout = 1
        c._live_ok = None
        c._http_attempts = 3
        c._http_backoff = 0.0

        calls = {"n": 0}

        def fake_urlopen(req, timeout=None):
            calls["n"] += 1
            raise urllib.error.HTTPError("u", 402, "Payment Required", {}, None)

        orig = connectors.urllib.request.urlopen
        connectors.urllib.request.urlopen = fake_urlopen
        try:
            status, data = c._http_json("https://api.x.com/2/x")
        finally:
            connectors.urllib.request.urlopen = orig

        self.assertEqual(status, 402)  # definitive HTTP status returned as-is
        self.assertIsNone(data)
        self.assertEqual(calls["n"], 1)  # NOT retried


class TestRunManifest(unittest.TestCase):
    def test_run_scan_writes_manifest(self):
        from scan import run_scan
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            run_scan(["AAPL", "TSLA"], prefer_live=False, out_dir=out)
            mpath = out / "run_manifest.json"
            self.assertTrue(mpath.exists(), "run_manifest.json must be written")
            m = json.loads(mpath.read_text())
            self.assertIn("run_id", m)
            self.assertEqual(m["mode"], "replay")
            self.assertEqual(m["universe"], ["AAPL", "TSLA"])
            self.assertIn("AAPL", m["tickers"])
            self.assertIn("TSLA", m["tickers"])
            self.assertEqual(m["tickers"]["AAPL"]["status"], "done")
            self.assertIn("priority", m["tickers"]["AAPL"])
            self.assertIsNotNone(m["finished_utc"])


class TestScanParity(unittest.TestCase):
    def test_review_queue_matches_golden(self):
        from scan import run_scan
        golden = json.loads(FIXTURE.read_text())
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            # Hermetic: fake connector → identical inputs on every machine, so the
            # comparison isolates the concurrency refactor, not local artifacts.
            run_scan(["AAPL", "TSLA", "GME"], prefer_live=False, out_dir=out,
                     connector=_FakeConnector())
            produced = json.loads((out / "review_queue.json").read_text())
        # Normalize both to the same canonical form and compare.
        a = json.dumps(_normalize(golden), indent=2, sort_keys=True)
        b = json.dumps(_normalize(produced), indent=2, sort_keys=True)
        self.assertEqual(a, b, "review_queue results diverged from pre-refactor golden")


class TestTickerParallelism(unittest.TestCase):
    """Phase 0.1: tickers scan concurrently but the queue is identical to serial."""

    def _run(self, workers):
        from scan import run_scan
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            run_scan(["AAPL", "TSLA", "GME", "AMC", "NVDA"], prefer_live=False,
                     out_dir=out, connector=_FakeConnector(), workers=workers)
            return json.loads((out / "review_queue.json").read_text())

    def test_queue_identical_across_worker_counts(self):
        serial = json.dumps(_normalize(self._run(1)), sort_keys=True)
        parallel = json.dumps(_normalize(self._run(5)), sort_keys=True)
        self.assertEqual(serial, parallel)

    def test_all_tickers_present(self):
        q = self._run(5)
        self.assertEqual({r["ticker"] for r in q["review_queue"]},
                         {"AAPL", "TSLA", "GME", "AMC", "NVDA"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
