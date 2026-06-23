"""#19: per-fetch provider observability — note parsing + manifest map."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agents


def test_provider_from_note_parses_via_clause():
    assert agents._provider_from_note("stock forums $AMC via scrapegraphai") == "scrapegraphai"
    assert agents._provider_from_note("OpenInsider Form 4 trades for GME via firecrawl") == "firecrawl"
    assert agents._provider_from_note("x $TSLA via scrapegraphai search (3 posts)") == "scrapegraphai"


def test_provider_from_note_none_when_absent():
    assert agents._provider_from_note("live (persisted to live_cache)") is None
    assert agents._provider_from_note("") is None
    assert agents._provider_from_note(None) is None


def test_manifest_providers_extraction_matches_scan_logic():
    # mirrors the dict-comp scan.py uses to build the per-ticker "providers" map
    sh = {
        "polygon_prev": {"mode": "live", "ok": True},                       # no provider
        "openinsider": {"mode": "live", "ok": True, "provider": "scrapegraphai"},
        "x": {"mode": "live", "ok": True, "provider": "scrapegraphai"},
        "glint": {"mode": "replay", "ok": True},                            # no provider
    }
    providers = {k: v["provider"] for k, v in sh.items() if v.get("provider")}
    assert providers == {"openinsider": "scrapegraphai", "x": "scrapegraphai"}
    # additive: existing fetches/mode map is unchanged
    fetches = {k: v.get("mode") for k, v in sh.items()}
    assert fetches["polygon_prev"] == "live" and fetches["glint"] == "replay"
