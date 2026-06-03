#!/usr/bin/env python3
"""Tests for authorized Discord/Telegram social import."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "features"))

import social_import as si
from features import social as soc
import scoring_v2

TELEGRAM = {"name": "ABC Pumps", "messages": [
    {"id": 1, "type": "message", "date": "2021-09-13T10:00:00", "from_id": "user1",
     "text": "$ABC guaranteed moon buy now"},
    {"id": 2, "type": "message", "date": "2021-09-13T10:01:00", "from_id": "user2",
     "text": [{"type": "plain", "text": "$ABC rocket "}, {"type": "bold", "text": "join now"}]},
]}
DISCORD = {"channel": {"name": "stocks-vip"}, "messages": [
    {"id": 99, "timestamp": "2021-09-13T10:02:00Z", "author": {"id": "u9", "name": "promo"},
     "content": "$ABC must buy now telegram", "reactions": [{"count": 5}]},
]}


class TestParsers(unittest.TestCase):
    def test_telegram(self):
        posts = si.parse_telegram_export(TELEGRAM)
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0]["platform"], "telegram")
        self.assertIn("join now", posts[1]["text"])  # list-segment text joined

    def test_discord(self):
        posts = si.parse_discord_export(DISCORD)
        self.assertEqual(posts[0]["platform"], "discord")
        self.assertEqual(posts[0]["engagement"], 5.0)

    def test_jsonl(self):
        text = "\n".join(json.dumps(x) for x in
                         [{"platform": "telegram", "id": "a", "text": "$ABC moon"},
                          {"id": "b", "text": "$ABC squeeze", "sentiment": "bullish"}])
        posts = si.parse_jsonl(text)
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[1]["sentiment"], "bullish")


class TestGate(unittest.TestCase):
    def test_off_by_default(self):
        os.environ.pop("SECFEDCLAW_AUTHORIZED_SOCIAL", None)
        self.assertFalse(si.authorized())
        self.assertEqual(si.load_authorized("ABC"), [])

    def test_opt_in_and_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "tg.json").write_text(json.dumps(TELEGRAM))
            (d / "dc.json").write_text(json.dumps(DISCORD))
            os.environ["SECFEDCLAW_AUTHORIZED_SOCIAL"] = "1"
            try:
                posts = si.load_authorized("ABC", directory=d)
                self.assertGreaterEqual(len(posts), 3)
                self.assertEqual({p["platform"] for p in posts}, {"telegram", "discord"})
                none = si.load_authorized("ZZZZ", directory=d)
                self.assertEqual(none, [])
            finally:
                os.environ.pop("SECFEDCLAW_AUTHORIZED_SOCIAL", None)


class TestScoringIntegration(unittest.TestCase):
    def _f(self, data):
        class F:
            def __init__(s): s.name = "t"; s.data = data; s.mode = "replay"; s.status = 200
            def ok(s): return data is not None
            artifact_path = None; sha256 = None; source_url_redacted = None
        return F()

    def test_imported_posts_flow_into_coordination(self):
        imported = si.parse_telegram_export(TELEGRAM) + si.parse_discord_export(DISCORD)
        fetches = {k: self._f(None) for k in
                   ("daily_range", "grouped", "snapshot", "trades", "quotes", "x", "reddit",
                    "stocktwits", "otc_threshold", "reg_sho", "halts", "submissions", "edgar")}
        fetches["reddit_unavailable"] = True
        fetches["social_import"] = imported  # pass directly (bypasses env gate)
        pkg = scoring_v2.build_package("ABC", fetches)
        self.assertIn("telegram", pkg["social_metrics"]["platforms"])
        self.assertIn("discord", pkg["social_metrics"]["platforms"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
