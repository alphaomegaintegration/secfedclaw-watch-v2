#!/usr/bin/env python3
"""Tests for _parse_openinsider positional column parsing in scoring_v2."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scoring_v2 import _parse_openinsider

# Realistic OpenInsider Firecrawl markdown snippet (pipe-delimited table)
# Columns: Filing Date | Trade Date | Ticker | Insider Name | Title | Trade Type | Price | Qty | Owned | ΔOwn% | Value
SAMPLE_MD = """
## Insider Trades

| Filing Date | Trade Date | Ticker | Insider Name | Title | Trade Type | Price | Qty | Owned | ΔOwn% | Value |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-06-05 | 2026-06-04 | AMC | Jane Smith | CEO | S | 4.12 | 100000 | 500000 | -16.7% | $412,000 |
| 2026-06-04 | 2026-06-03 | AMC | Bob Jones | CFO | S+ | 4.05 | 50000 | 200000 | -20.0% | $202,500 |
| 2026-06-03 | 2026-06-02 | AMC | Alice Wu | Director | P | 3.98 | 25000 | 75000 | +50.0% | $99,500 |
| 2026-06-01 | 2026-05-31 | GME | Dave Kim | VP | S | 22.00 | 10000 | 50000 | -16.7% | $220,000 |
"""

HEADER_ONLY_MD = """
| Filing Date | Trade Date | Ticker | Insider Name | Title | Trade Type | Price | Qty | Owned | ΔOwn% | Value |
|---|---|---|---|---|---|---|---|---|---|---|
"""

EMPTY_MD = ""
SHORT_MD = "| x |"


class TestParseOpenInsider(unittest.TestCase):

    def test_counts_sales_correctly(self):
        sells, buys = _parse_openinsider(SAMPLE_MD, "AMC")
        self.assertEqual(sells, 2)  # Jane Smith (S) + Bob Jones (S+)

    def test_counts_purchases_correctly(self):
        sells, buys = _parse_openinsider(SAMPLE_MD, "AMC")
        self.assertEqual(buys, 1)  # Alice Wu (P)

    def test_does_not_count_other_ticker(self):
        sells, buys = _parse_openinsider(SAMPLE_MD, "GME")
        self.assertEqual(sells, 1)  # Only Dave Kim
        self.assertEqual(buys, 0)

    def test_header_row_produces_no_counts(self):
        """Header row has 'Trade Type' in col[5] — must not be counted."""
        sells, buys = _parse_openinsider(HEADER_ONLY_MD, "AMC")
        self.assertEqual(sells, 0)
        self.assertEqual(buys, 0)

    def test_empty_markdown_returns_zeros(self):
        self.assertEqual(_parse_openinsider(EMPTY_MD, "AMC"), (0, 0))

    def test_short_markdown_returns_zeros(self):
        self.assertEqual(_parse_openinsider(SHORT_MD, "AMC"), (0, 0))

    def test_ticker_case_insensitive(self):
        sells, _ = _parse_openinsider(SAMPLE_MD, "amc")
        self.assertEqual(sells, 2)

    def test_unknown_ticker_returns_zeros(self):
        sells, buys = _parse_openinsider(SAMPLE_MD, "AAPL")
        self.assertEqual(sells, 0)
        self.assertEqual(buys, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
