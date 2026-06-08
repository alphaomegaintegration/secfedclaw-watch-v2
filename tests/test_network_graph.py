#!/usr/bin/env python3
"""Regression tests for dashboard_v2.network_graph_panel().

Guards against the index-based edge lookup regression fixed in commit 8a68c9b,
where node keys were looked up by string ID rather than by stable dict key,
causing edges to silently reference wrong node indices.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import dashboard_v2


def _pkg(ticker, priority="MEDIUM", watch_score=55,
         clusters=None, shared_domains=None, families=None, platforms=None):
    """Build a minimal package dict for network_graph_panel testing."""
    return {
        "ticker": ticker,
        "review_priority": priority,
        "watch_score": watch_score,
        "component_scores": {"coordination_score": 40},
        "social_metrics": {"platforms": platforms or []},
        "coordination_detail": {
            "near_duplicate_clusters": clusters or [],
            "shared_domain_groups": shared_domains or [],
        },
        "corroboration": {
            "n_families_active": len(families or []),
            "families_active": families or [],
        },
    }


class TestNetworkGraphNodes(unittest.TestCase):
    """Ticker nodes must appear in the embedded graph data."""

    def _graph_data(self, packages):
        html = dashboard_v2.network_graph_panel(packages)
        # The JSON data is embedded as: var GD={...};
        start = html.index("var GD=") + len("var GD=")
        end = html.index(";", start)
        return json.loads(html[start:end])

    def test_ticker_node_present(self):
        pkgs = [_pkg("AAPL", priority="HIGH", watch_score=70)]
        gd = self._graph_data(pkgs)
        ids = {n["id"] for n in gd["nodes"]}
        self.assertIn("AAPL", ids, "Ticker node must appear in graph data")

    def test_multiple_ticker_nodes(self):
        pkgs = [_pkg("XYZ", watch_score=60), _pkg("ABC", watch_score=30)]
        gd = self._graph_data(pkgs)
        ids = {n["id"] for n in gd["nodes"]}
        self.assertIn("XYZ", ids)
        self.assertIn("ABC", ids)

    def test_ticker_node_type(self):
        pkgs = [_pkg("ZZZT")]
        gd = self._graph_data(pkgs)
        ticker_nodes = [n for n in gd["nodes"] if n.get("type") == "ticker"]
        self.assertEqual(len(ticker_nodes), 1)
        self.assertEqual(ticker_nodes[0]["id"], "ZZZT")

    def test_ticker_node_carries_watch_score(self):
        pkgs = [_pkg("SCORED", watch_score=77)]
        gd = self._graph_data(pkgs)
        node = next(n for n in gd["nodes"] if n["id"] == "SCORED")
        self.assertEqual(node["score"], 77)

    def test_platform_node_present(self):
        pkgs = [_pkg("PTST", platforms=["x", "reddit"])]
        gd = self._graph_data(pkgs)
        ids = {n["id"] for n in gd["nodes"]}
        self.assertIn("x", ids)
        self.assertIn("reddit", ids)

    def test_cluster_node_present(self):
        clusters = [{"size": 5, "members": []}]
        pkgs = [_pkg("CLST", clusters=clusters)]
        gd = self._graph_data(pkgs)
        cluster_nodes = [n for n in gd["nodes"] if n.get("type") == "cluster"]
        self.assertEqual(len(cluster_nodes), 1)
        self.assertEqual(cluster_nodes[0]["size"], 5)

    def test_family_node_present(self):
        pkgs = [_pkg("FAMTEST", families=["market", "coordination"])]
        gd = self._graph_data(pkgs)
        ids = {n["id"] for n in gd["nodes"]}
        self.assertIn("market", ids)
        self.assertIn("coordination", ids)


class TestNetworkGraphEdges(unittest.TestCase):
    """Regression: edges must use stable index-based lookup (commit 8a68c9b fix)."""

    def _graph_data(self, packages):
        html = dashboard_v2.network_graph_panel(packages)
        start = html.index("var GD=") + len("var GD=")
        end = html.index(";", start)
        return json.loads(html[start:end])

    def _node_index(self, gd, node_id):
        """Return the index of a node by its 'id' field."""
        for i, n in enumerate(gd["nodes"]):
            if n["id"] == node_id:
                return i
        return None

    def test_ticker_to_platform_edge_exists(self):
        pkgs = [_pkg("EDGET", platforms=["x"])]
        gd = self._graph_data(pkgs)
        ticker_idx = self._node_index(gd, "EDGET")
        platform_idx = self._node_index(gd, "x")
        self.assertIsNotNone(ticker_idx)
        self.assertIsNotNone(platform_idx)
        edge_pairs = {(e["s"], e["t"]) for e in gd["edges"]}
        self.assertIn((ticker_idx, platform_idx), edge_pairs,
                      "Edge from ticker to platform node is missing — "
                      "index-based lookup regression may have recurred")

    def test_ticker_to_cluster_edge_uses_correct_indices(self):
        """The original regression: cluster edge pointed to wrong node.

        With two ticker nodes that both have clusters, the edge source index
        must match the correct ticker, not the first ticker's index for every
        edge.
        """
        pkgs = [
            _pkg("FIRST", watch_score=50, clusters=[{"size": 3, "members": []}]),
            _pkg("SECOND", watch_score=60, clusters=[{"size": 4, "members": []}]),
        ]
        gd = self._graph_data(pkgs)
        first_idx = self._node_index(gd, "FIRST")
        second_idx = self._node_index(gd, "SECOND")

        # Find cluster nodes for each ticker
        cluster_nodes = {n["_key"]: i for i, n in enumerate(gd["nodes"])
                         if n.get("type") == "cluster"}

        # Each cluster edge's source must be the correct ticker, not a
        # constant fallback index (the pre-fix bug used string ID lookup
        # which could silently return wrong results when IDs were reused).
        has_cluster_edges = [(e["s"], e["t"], e.get("type")) for e in gd["edges"]
                             if e.get("type") == "has_cluster"]
        self.assertGreaterEqual(len(has_cluster_edges), 2,
                                "Expected 2 has_cluster edges (one per ticker)")
        sources = {e[0] for e in has_cluster_edges}
        # Both tickers must appear as distinct edge sources
        self.assertIn(first_idx, sources,
                      "FIRST ticker is not the source of any cluster edge")
        self.assertIn(second_idx, sources,
                      "SECOND ticker is not the source of any cluster edge")

    def test_edges_reference_valid_node_indices(self):
        """All edge source/target indices must be within bounds — no ghost indices."""
        pkgs = [
            _pkg("A1", platforms=["x"], clusters=[{"size": 2}],
                 families=["market", "coordination"]),
            _pkg("B2", platforms=["reddit"], families=["social"]),
        ]
        gd = self._graph_data(pkgs)
        n_nodes = len(gd["nodes"])
        for edge in gd["edges"]:
            self.assertGreaterEqual(edge["s"], 0)
            self.assertLess(edge["s"], n_nodes,
                            f"Edge source index {edge['s']} out of bounds (n={n_nodes})")
            self.assertGreaterEqual(edge["t"], 0)
            self.assertLess(edge["t"], n_nodes,
                            f"Edge target index {edge['t']} out of bounds (n={n_nodes})")

    def test_empty_packages_produces_empty_graph(self):
        gd = self._graph_data([])
        self.assertEqual(gd["nodes"], [])
        self.assertEqual(gd["edges"], [])

    def test_none_package_is_skipped(self):
        """None entries in the packages list must be silently skipped."""
        pkgs = [None, _pkg("SAFETICK"), None]
        gd = self._graph_data(pkgs)
        ids = {n["id"] for n in gd["nodes"]}
        self.assertIn("SAFETICK", ids)


class TestNetworkGraphStats(unittest.TestCase):
    """The stats block embedded in the HTML must match the graph data."""

    def test_stats_node_count_matches_data(self):
        pkgs = [_pkg("A"), _pkg("B"), _pkg("C")]
        html = dashboard_v2.network_graph_panel(pkgs)
        start = html.index("var GD=") + len("var GD=")
        end = html.index(";", start)
        gd = json.loads(html[start:end])
        # The stats text embeds the node count
        n_nodes = len(gd["nodes"])
        self.assertIn(f"{n_nodes} nodes", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
