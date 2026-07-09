#!/usr/bin/env python3
"""Wave-5 structural fixes: unified output_root() and the decoupled, thread-safe
CIK registry."""
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config
import cik_registry


class TestOutputRoot(unittest.TestCase):
    def test_default_is_repo_out(self):
        self.assertEqual(config.output_root(), config.fed_claw_root() / "out")

    def test_env_override(self, ):
        import os
        prev = os.environ.get("SECFEDCLAW_OUT_DIR")
        os.environ["SECFEDCLAW_OUT_DIR"] = "/tmp/sec_out_xyz"
        try:
            self.assertEqual(config.output_root(), Path("/tmp/sec_out_xyz"))
        finally:
            if prev is None:
                os.environ.pop("SECFEDCLAW_OUT_DIR", None)
            else:
                os.environ["SECFEDCLAW_OUT_DIR"] = prev


class TestCikRegistry(unittest.TestCase):
    def test_seed_and_lookup(self):
        self.assertEqual(cik_registry.cik_for("aapl"), "0000320193")
        self.assertIsNone(cik_registry.cik_for("NOPE_TICKER"))

    def test_edgar_pipeline_decoupled_from_agents(self):
        # edgar_pipeline must resolve CIKs via cik_registry, not by importing the
        # agent/scoring stack (the old cross-layer cycle).
        src = (ROOT / "edgar_pipeline.py").read_text()
        self.assertIn("from cik_registry import CIK_MAP", src)
        self.assertNotIn("from agents import", src)

    def test_load_cik_map_thread_safe_single_fetch(self):
        # Reset load state, then hit it from many threads: exactly one fetch.
        cik_registry._loaded = False
        calls = {"n": 0}

        class _FakeFetch:
            data = {"0": {"ticker": "ZZZZ", "cik_str": 42}}
            def ok(self): return True

        class _FakeConn:
            def sec_company_tickers(self):
                calls["n"] += 1
                return _FakeFetch()

        conn = _FakeConn()
        threads = [threading.Thread(target=cik_registry.load_cik_map, args=(conn,)) for _ in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(calls["n"], 1)                       # loaded once, not 20x
        self.assertEqual(cik_registry.cik_for("ZZZZ"), "0000000042")


if __name__ == "__main__":
    unittest.main(verbosity=2)
