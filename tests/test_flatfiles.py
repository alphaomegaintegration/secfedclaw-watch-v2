#!/usr/bin/env python3
"""Tests for Polygon/Massive Flat Files client + historical replay."""
import datetime as dt
import gzip
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import flatfiles
import historical


DAY_CSV = (
    "ticker,volume,open,close,high,low,window_start,transactions\n"
    "AABB,{v},{o},{c},{h},{l},1631520000000000000,{n}\n"
    "MSFT,5000000,300,301,302,299,1631520000000000000,40000\n"
    "NVDA,4000000,200,201,202,199,1631520000000000000,30000\n"
)


def _make_day(path: Path, day: str, aabb=(1_000_000, 1.0, 1.0, 1.0, 1.0, 5000), spike=False):
    v, o, c, h, l, n = aabb
    if spike:
        v, c, h, n = 30_000_000, 1.8, 1.9, 90000
    csv = DAY_CSV.format(v=v, o=o, c=c, h=h, l=l, n=n)
    (path / f"{day}.csv.gz").write_bytes(gzip.compress(csv.encode()))


class TestParse(unittest.TestCase):
    def test_parse_gz_and_plain(self):
        csv = DAY_CSV.format(v=1000, o=1, c=2, h=2, l=1, n=10)
        gzd = gzip.compress(csv.encode())
        a = flatfiles.parse_day_aggs_csv(gzd)
        b = flatfiles.parse_day_aggs_csv(csv.encode())
        self.assertEqual(a["AABB"]["c"], 2.0)
        self.assertEqual(b["MSFT"]["o"], 300.0)
        self.assertEqual(a["AABB"]["t"], 1631520000000)  # ns -> ms

    def test_day_aggs_key(self):
        self.assertEqual(flatfiles.day_aggs_key("2021-09-13"),
                         "us_stocks_sip/day_aggs_v1/2021/09/2021-09-13.csv.gz")


class TestSigning(unittest.TestCase):
    def test_signed_get_has_auth(self):
        req = flatfiles.signed_get_request("AKIDEXAMPLE", "secret", "us_stocks_sip/x.csv.gz")
        self.assertTrue(req.headers["Authorization"].startswith("AWS4-HMAC-SHA256"))
        self.assertIn("x-amz-date", {k.lower() for k in req.headers})

    def test_signed_get_deterministic_structure(self):
        """Fixed inputs produce a deterministic, structurally valid Authorization header."""
        access_key = "AKIAIOSFODNN7EXAMPLE"
        secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        key = "us_stocks_sip/day_aggs_v1/2021/09/2021-09-13.csv.gz"
        # Fix the signing time so the output is 100% deterministic.
        fixed_now = dt.datetime(2021, 9, 13, 0, 0, 0, tzinfo=dt.timezone.utc)
        req = flatfiles.signed_get_request(access_key, secret, key, now=fixed_now)

        auth = req.headers["Authorization"]
        # 1. Algorithm prefix
        self.assertTrue(auth.startswith("AWS4-HMAC-SHA256 "), auth[:40])

        # 2. Credential scope contains the access key
        self.assertIn(f"Credential={access_key}/", auth)

        # 3. Credential scope encodes the correct date + region + service
        #    format: <access_key>/YYYYMMDD/us-east-1/s3/aws4_request
        self.assertIn("20210913/us-east-1/s3/aws4_request", auth)

        # 4. SignedHeaders field lists exactly the expected headers
        self.assertIn("SignedHeaders=host;x-amz-content-sha256;x-amz-date", auth)

        # 5. Signature field is present and looks like a 64-char hex string
        import re
        m = re.search(r"Signature=([0-9a-f]+)", auth)
        self.assertIsNotNone(m, "Signature field missing from Authorization header")
        self.assertEqual(len(m.group(1)), 64, "SigV4 signature must be 64 hex chars (SHA-256)")

        # 6. x-amz-date header matches the fixed timestamp (urllib stores as "X-amz-date")
        amz_date = req.headers.get("X-amz-date") or req.headers.get("x-amz-date") or req.headers.get("X-Amz-Date")
        self.assertEqual(amz_date, "20210913T000000Z")


class TestMarketFetchesAndScore(unittest.TestCase):
    def test_real_data_path_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "day_aggs"
            cache.mkdir(parents=True)
            # 30 flat days + a spike on the event day
            days = [f"2021-08-{d:02d}" for d in range(1, 28)] + ["2021-09-13"]
            for d in days[:-1]:
                _make_day(cache, d)
            _make_day(cache, "2021-09-13", spike=True)

            client = flatfiles.FlatFilesClient(prefer_live=False)
            client.cache_dir = cache
            mf = client.market_fetches("AABB", "2021-09-13", lookback_days=40)
            self.assertGreater(mf["n_days_with_bars"], 10)
            self.assertTrue(mf["daily_range"].ok())
            self.assertTrue(mf["grouped"].ok())

            res = historical.score_window(client, "AABB", "2021-09-13", lookback=40)
            # spike day should light up the market-anomaly component on real-shaped data
            self.assertGreater(res["market_anomaly_score"], 20)
            self.assertEqual(res["data_mode"], "replay")

    def test_offline_no_cache_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = flatfiles.FlatFilesClient(prefer_live=False)
            client.cache_dir = Path(tmp) / "empty"
            res = historical.score_window(client, "AABB", "2021-09-13", lookback=10)
            self.assertEqual(res["n_days_with_bars"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
