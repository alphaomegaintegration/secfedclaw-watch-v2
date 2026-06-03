# Multi-Platform Social Signals

**Commit:** `91b0d1e` (2026-06-03) — *Multi-platform social: Reddit OAuth + StockTwits (sentiment) signals*
**Files:** `connectors.py`, `features/social.py`, `scoring_v2.py`, `agents.py`, `tests/test_social.py`

## Overview

Restores Reddit via authenticated OAuth (app-only `client_credentials`), replacing the 403-blocked public-JSON path, and adds StockTwits symbol streams with native Bullish/Bearish sentiment. All platforms (X + Reddit + StockTwits) normalize into one post schema so the coordination graph, social split, and dedup work cross-platform automatically.

Validated: a 3-platform coordinated pump (8-post duplicate cluster, unanimous bullish) scored coordination 72 and reached MEDIUM. Discord/Telegram are left as an explicit evidence gap (require lawful authorization). WATCH-only throughout.

## Platform Coverage

| Platform | Auth | Endpoint | Data |
|---|---|---|---|
| **X (Twitter)** | Bearer token | `/2/tweets/search/recent` | Cashtag search, engagement metrics |
| **Reddit** | OAuth `client_credentials` | `/r/{subs}/search` | Finance subreddit search (pennystocks, stocks, wallstreetbets, Shortsqueeze, smallstreetbets, RobinHoodPennyStocks) |
| **StockTwits** | None (public) | `/api/2/streams/symbol/{ticker}` | Symbol stream with native Bullish/Bearish sentiment |

### Evidence Gaps (documented)
- **Discord** — requires lawful authorization
- **Telegram** — requires lawful authorization

## Post Normalization

All platforms normalize into a unified schema via `normalize_posts()`:

```python
{
    "platform": "x" | "reddit" | "stocktwits",
    "id": "<platform-specific id>",
    "text": "<post content>",
    "created_at": "<timestamp>",
    "author_id": "<author identifier>",
    "sentiment": "bullish" | "bearish" | None,  # StockTwits only
    "engagement": <float>  # platform-specific engagement metric
}
```

### Engagement Metrics
- **X:** `retweet_count + reply_count + like_count + quote_count`
- **Reddit:** `score + num_comments`
- **StockTwits:** `likes.total`

### Deduplication
Posts are deduped by `(platform, id)` before scoring. The count of removed duplicates is tracked in the output.

## Reddit OAuth Flow

The connector uses Reddit's app-only OAuth (`client_credentials` grant):

1. Base64-encode `CLIENT_ID:CLIENT_SECRET`
2. POST to `https://www.reddit.com/api/v1/access_token` with `grant_type=client_credentials`
3. Use the returned bearer token for search requests to `oauth.reddit.com`

The token is cached on the `DataConnector` instance for the session. If credentials are missing or the grant fails, Reddit falls back to replay mode.

### Subreddits Searched
Default: `pennystocks+stocks+wallstreetbets+Shortsqueeze+smallstreetbets+RobinHoodPennyStocks`

Custom subreddits can be passed via the `subreddits` parameter on `reddit_oauth()`.

## StockTwits Integration

Uses the public symbol stream endpoint (no auth required, rate-limited). Parses:
- **Messages:** body text, creation time, user info
- **Sentiment:** native `Bullish`/`Bearish` tags from StockTwits' entity sentiment

## Social Features (`features/social.py`)

`social_features()` computes:

| Feature | Description |
|---|---|
| `n_posts` | Total normalized posts across all platforms |
| `n_issuer_specific` | Posts mentioning this ticker without promo signatures |
| `n_promotional_noise` | Posts with promo terms or cashtag-stuffing (>3 tickers) |
| `promo_term_hits` | Count of promotional keyword matches |
| `engagement_total` | Sum of all engagement metrics |
| `platforms` | List of platforms with data |
| `n_platforms` | Number of distinct platforms |
| `platform_counts` | Per-platform post counts |
| `cross_platform_issuer_specific` | `true` if issuer-specific posts appear on ≥2 platforms |
| `sentiment.bullish` | Count of bullish-tagged posts |
| `sentiment.bearish` | Count of bearish-tagged posts |
| `sentiment.bullish_ratio` | Proportion bullish (0–1) |
| `sentiment.unanimous_bullish` | `true` if ≥5 sentiment posts and ≥90% bullish |
| `reddit_state` | `platform_unavailable` / `platform_present` / `platform_silent` |

### Promotional Term Detection

Posts are flagged as promotional if they contain any of ~30 promo terms (e.g. "guaranteed", "moon", "squeeze", "buy now", "telegram", "100x") or mention >3 cashtags (basket/promo, not issuer-specific).

Promotional noise **deflates** the issuer-specific burst score — it does not inflate it. This is a key design principle: spam makes social evidence *less* credible, not more.

### Issuer-Specific Detection

A post is issuer-specific if it mentions the ticker (via cashtag or name) AND has ≤3 total cashtags. Posts with >3 cashtags are classified as basket/promo regardless of content.

## Scoring Integration

### Social Scores
`social_scores()` produces two sub-scores:
- **`social_issuer_specific_burst`** (0–100): Scaled by post count × platform diversity, with engagement boost and promo deflation
- **`social_promotional_noise`** (0–100): Raw promo signal (informational, not a concern-bearing score)

### Sentiment → Coordination Nudge
When `unanimous_bullish` is true (≥5 sentiment posts, ≥90% bullish) AND promotional posts are present, `scoring_v2.py` applies a capped coordination nudge. This recognizes that unanimous bullish sentiment combined with promotional language is a coordination tell.

The nudge:
- Is capped (does not dominate the coordination score)
- Adds an explained basis entry: `"sentiment_mania_nudge: unanimous_bullish + promo"`
- Feeds into the coordination component, which participates in corroboration

## Credentials

| Variable | Required For | Notes |
|---|---|---|
| `REDDIT_CLIENT_ID` | Reddit live | Create at reddit.com/prefs/apps (script type) |
| `REDDIT_CLIENT_SECRET` | Reddit live | Paired with client ID |
| `REDDIT_USER_AGENT` | Reddit live | Optional; defaults to `secfedclaw-watch/2.0 by u/secfedclaw` |
| `X_BEARER_TOKEN` | X live | Twitter API v2 bearer token |

StockTwits requires no credentials (public endpoint).

## Testing

5 tests in `tests/test_social.py`:

- **`TestNormalize.test_stocktwits_parsed_with_sentiment`** — StockTwits messages parse correctly with bullish/bearish sentiment tags.
- **`TestNormalize.test_reddit_parsed`** — Reddit listing data normalizes into the post schema.
- **`TestNormalize.test_multiplatform_merge`** — X + Reddit + StockTwits merge into a single post list with all 3 platforms represented.
- **`TestFeatures.test_sentiment_and_cross_platform`** — 3-platform input produces correct platform count, bullish ratio of 1.0, and `unanimous_bullish` flag.
- **`TestScoringIntegration.test_sentiment_mania_nudges_coordination`** — End-to-end: unanimous bullish + promo across 3 platforms produces coordination_score > 0 with a "sentiment" basis entry.

```bash
python3 -m pytest tests/test_social.py -v   # all 5 pass
```
