"""SRE observability: LLM-cost local-free split + status aggregation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import usage
import agent_status


# ---- usage.py: local models price as free ---------------------------------

def test_ollama_prices_known_free():
    pin, pout, known = usage.price_for("ollama/gemma4:latest")
    assert (pin, pout, known) == (0.0, 0.0, True)
    assert usage.is_free("ollama/gemma4:latest") is True
    assert usage.is_free("ollama/llama3:70b") is True


def test_paid_model_not_free():
    assert usage.is_free("openai/gpt-4o-mini") is False
    assert usage.is_free("claude-opus-4") is False
    pin, pout, known = usage.price_for("openai/gpt-4o-mini")
    assert known and pin > 0


def test_summary_paid_free_split(tmp_path):
    led = tmp_path / "usage.jsonl"
    usage.record("ollama/gemma4:latest", 1000, 500, component="search", path=led)
    usage.record("openai/gpt-4o-mini", 1000, 500, component="explain", path=led)
    usage.record("ollama/llama3:70b", 200, 100, component="search", path=led)
    s = usage.summary(path=led)
    assert s["n_calls"] == 3
    assert s["local_free_calls"] == 2
    assert s["paid_calls"] == 1
    # only the paid call contributes cost
    assert s["paid_cost_usd"] > 0
    assert not s["any_unknown_pricing"]  # ollama is now known-priced


# ---- agent_status.py: integration health + agent perf ---------------------

def _queue():
    sh = {
        "polygon_prev": {"mode": "live", "ok": True},
        "openinsider": {"mode": "live", "ok": True, "provider": "scrapegraphai"},
        "discord": {"mode": "live", "ok": True, "provider": "firecrawl"},
        "glint": {"mode": "replay", "ok": True},
    }
    # two tickers, openinsider mostly scrapegraphai
    return {"review_queue": [
        {"ticker": "AMC", "source_health": sh},
        {"ticker": "GME", "source_health": {**sh, "openinsider": {"mode": "replay", "ok": False, "provider": "scrapegraphai"}}},
    ]}


def test_integration_health_success_and_provider():
    rows = {r["integration"]: r for r in agent_status.integration_health(_queue())}
    oi = rows["openinsider"]
    assert oi["provider"] == "scrapegraphai"
    assert oi["ok"] == 1 and oi["total"] == 2 and oi["success_pct"] == 50
    assert oi["state"] == "live"  # at least one live
    assert rows["discord"]["provider"] == "firecrawl"
    assert "provider" not in rows["polygon_prev"]  # no provider tagged
    assert rows["glint"]["state"] == "replay"


def test_agent_perf_p50_max_and_errors():
    manifest = {"tickers": {
        "AMC": {"status": "done", "stage_ms": {"Scout": 1200.0, "Analyst": 300.0}},
        "GME": {"status": "done", "stage_ms": {"Scout": 800.0, "Analyst": 100.0}},
        "TSLA": {"status": "error", "error": "boom"},
    }}
    perf, runs, errors = agent_status.agent_perf(manifest)
    assert runs == 3 and errors == 1
    assert perf["Scout"]["max_ms"] == 1200 and perf["Scout"]["runs"] == 2
    assert perf["Analyst"]["p50_ms"] == 200  # median(300,100)


def test_agent_perf_empty_manifest():
    perf, runs, errors = agent_status.agent_perf({})
    assert perf == {} and runs == 0 and errors == 0
