#!/usr/bin/env python3
"""Live-path integration test.

This sandbox blocks real network egress, so we inject a mock live HTTP transport
into DataConnector and prove that data flows LIVE through the full agent pipeline
(Scout → Analyst → Adversary → Packager): the connector reports live mode,
persists raw responses with SHA256 (custody), and the live data reaches the
scores. On the operator's machine the same path runs against real endpoints via
`scan.py --live`.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import connectors
from agents import Orchestrator


def _mock_http_json(url, headers=None):
    """Return canned 200 payloads keyed by URL, mimicking live endpoints."""
    if "marketstatus" in url:
        return 200, {"market": "open"}
    if "/range/1/day/" in url:  # daily range -> a flat series + a final spike
        res = []
        price = 2.0
        for i in range(40):
            c = price * (1.5 if i == 39 else (1.001 if i % 2 else 0.999))
            v = 40_000_000 if i == 39 else 1_000_000
            res.append({"o": price, "c": c, "h": max(price, c) * 1.01, "l": min(price, c) * 0.99,
                        "v": v, "vw": (price + c) / 2, "n": int(v / 90), "t": 1700000000000 + i * 86400000})
            price = c
        return 200, {"results": res}
    if "/aggs/grouped/" in url:
        return 200, {"results": [{"T": "LIVE", "o": 2.0, "c": 3.0, "v": 9_000_000, "vw": 2.4}]
                     + [{"T": f"N{i}", "o": 10, "c": 10.01, "v": 1_000_000, "vw": 10} for i in range(150)]}
    if "/aggs/ticker/" in url and "/prev" in url:
        return 200, {"results": [{"o": 2.0, "c": 3.0, "h": 3.1, "l": 1.9, "v": 9_000_000, "vw": 2.4}]}
    if "snapshot" in url:
        return 200, {"ticker": {"day": {}, "prevDay": {}}}
    if "twitter.com" in url:
        return 200, {"data": [{"id": f"x{i}", "text": "$LIVE guaranteed moon buy now",
                               "author_id": "a1", "public_metrics": {"like_count": 3}} for i in range(5)]}
    if "stocktwits" in url:
        return 200, {"messages": []}
    if "data.sec.gov" in url:
        return 200, {"name": "Live Co", "filings": {"recent": {"form": [], "filingDate": []}}}
    return 200, {}


def _mock_http_text(url, headers=None):
    if "company_tickers" in url:
        return 200, '{"0":{"cik_str":1,"ticker":"LIVE","title":"Live Co"}}'
    return 200, ""


class TestLiveFlow(unittest.TestCase):
    def test_live_data_flows_through_agents(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = connectors.DataConnector(root=Path(tmp), prefer_live=True)
            c.env["POLYGON_API_KEY"] = "test-key"   # gate live market branches
            c.env["X_BEARER_TOKEN"] = "test-bearer"
            c._http_json = _mock_http_json
            c._http_text = _mock_http_text
            orch = Orchestrator(connector=c, out_dir=Path(tmp) / "out")
            summary = orch.run("LIVE")

            # 1. live mode end-to-end
            self.assertIn(summary["data_mode"], ("live", "mixed_live_replay"))
            # 2. scout reports live feeds
            health = summary["source_health"]
            live_feeds = [k for k, v in health.items() if v.get("mode") == "live"]
            self.assertTrue(live_feeds, "expected at least one live feed")
            # 3. custody: live responses persisted to live_cache with sha256
            pkg = json.loads(Path(summary["package_path"]).read_text())
            live_rows = [e for e in pkg["evidence"] if e.get("mode") == "live" and e.get("artifact_sha256")]
            self.assertTrue(live_rows, "expected persisted live artifacts with sha256")
            # 4. live market data produced a real anomaly score
            self.assertGreater(pkg["component_scores"]["market_anomaly_score"], 20)

    def test_no_live_when_unreachable(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = connectors.DataConnector(root=Path(tmp), prefer_live=True)
            c._http_json = lambda url, headers=None: (None, None)   # all calls fail
            c._http_text = lambda url, headers=None: (None, None)
            self.assertFalse(c.live_available())
            f = c.polygon_prev("LIVE")
            self.assertEqual(f.mode, "unavailable")  # no cache in tmp, no live


if __name__ == "__main__":
    unittest.main(verbosity=2)
