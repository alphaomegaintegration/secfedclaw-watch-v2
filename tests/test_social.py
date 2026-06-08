#!/usr/bin/env python3
"""Tests for multi-platform social signals (X + Reddit + StockTwits + Discord)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "features"))

from features import social as soc
import scoring_v2


STOCKTWITS = {"messages": [
    {"id": 1, "body": "$ABC to the moon guaranteed buy now", "created_at": "2021-09-13T10:00:00Z",
     "user": {"id": 7}, "entities": {"sentiment": {"basic": "Bullish"}}, "likes": {"total": 3}},
    {"id": 2, "body": "$ABC rocket squeeze join telegram", "created_at": "2021-09-13T10:01:00Z",
     "user": {"id": 8}, "entities": {"sentiment": {"basic": "Bullish"}}},
    {"id": 3, "body": "$ABC easy money must buy", "created_at": "2021-09-13T10:02:00Z",
     "user": {"id": 9}, "entities": {"sentiment": {"basic": "Bullish"}}},
    {"id": 4, "body": "$ABC must buy now 100x", "created_at": "2021-09-13T10:03:00Z",
     "user": {"id": 10}, "entities": {"sentiment": {"basic": "Bullish"}}},
    {"id": 5, "body": "$ABC dont miss this rocket", "created_at": "2021-09-13T10:04:00Z",
     "user": {"id": 11}, "entities": {"sentiment": {"basic": "Bullish"}}},
]}
REDDIT = {"data": {"children": [
    {"data": {"id": "r1", "title": "$ABC squeeze incoming", "selftext": "guaranteed moon",
              "author": "u1", "created_utc": 1631520000, "score": 12, "num_comments": 4}},
]}}
X = {"data": [
    {"id": "x1", "text": "$ABC guaranteed moon rocket", "created_at": "2021-09-13T10:00:30Z",
     "author_id": "a1", "public_metrics": {"like_count": 2}},
]}


class TestNormalize(unittest.TestCase):
    def test_stocktwits_parsed_with_sentiment(self):
        posts = soc.normalize_posts(None, None, STOCKTWITS)
        self.assertEqual(len(posts), 5)
        self.assertEqual(posts[0]["platform"], "stocktwits")
        self.assertEqual(posts[0]["sentiment"], "bullish")

    def test_reddit_parsed(self):
        posts = soc.normalize_posts(None, REDDIT, None)
        self.assertEqual(posts[0]["platform"], "reddit")
        self.assertIn("$ABC", posts[0]["text"])

    def test_multiplatform_merge(self):
        posts = soc.normalize_posts(X, REDDIT, STOCKTWITS)
        plats = {p["platform"] for p in posts}
        self.assertEqual(plats, {"x", "reddit", "stocktwits"})


class TestFeatures(unittest.TestCase):
    def test_sentiment_and_cross_platform(self):
        posts = soc.normalize_posts(X, REDDIT, STOCKTWITS)
        feat = soc.social_features(posts, "ABC", reddit_unavailable=False)
        self.assertEqual(feat["n_platforms"], 3)
        self.assertGreaterEqual(feat["sentiment"]["bullish"], 3)
        self.assertEqual(feat["sentiment"]["bullish_ratio"], 1.0)
        self.assertTrue(feat["sentiment"]["unanimous_bullish"])


class TestScoringIntegration(unittest.TestCase):
    def _f(self, data):
        class F:
            def __init__(s): s.name = "t"; s.data = data; s.mode = "replay"; s.status = 200
            def ok(s): return data is not None
            artifact_path = None; sha256 = None; source_url_redacted = None
        return F()

    def test_sentiment_mania_nudges_coordination(self):
        fetches = {k: self._f(None) for k in
                   ("daily_range", "grouped", "snapshot", "trades", "quotes",
                    "otc_threshold", "reg_sho", "halts", "submissions", "edgar")}
        fetches["x"] = self._f(X)
        fetches["reddit"] = self._f(REDDIT)
        fetches["stocktwits"] = self._f(STOCKTWITS)
        fetches["reddit_unavailable"] = False
        pkg = scoring_v2.build_package("ABC", fetches)
        self.assertEqual(pkg["social_metrics"]["n_platforms"], 3)
        self.assertGreater(pkg["component_scores"]["coordination_score"], 0)
        self.assertTrue(any("sentiment" in b for b in pkg["coordination_detail"]["basis"]))


DISCORD_BOT_API = {"messages": [
    {"id": "1", "content": "$AAPL pump", "timestamp": "2026-06-08T12:00:00Z",
     "author": {"id": "u1"}, "reactions": [{"count": 3}]},
]}
DISCORD_FIRECRAWL = {"data": {"markdown": "some text"}, "success": True}


class TestDiscordNormalize(unittest.TestCase):
    def test_bot_api_message_parsed(self):
        posts = soc.normalize_posts(None, discord_fetch_data=DISCORD_BOT_API)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["platform"], "discord")
        self.assertEqual(posts[0]["text"], "$AAPL pump")
        self.assertEqual(posts[0]["engagement"], 3.0)

    def test_firecrawl_blob_produces_no_posts(self):
        posts = soc.normalize_posts(None, discord_fetch_data=DISCORD_FIRECRAWL)
        self.assertEqual(len(posts), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
