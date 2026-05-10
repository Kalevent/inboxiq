"""Verify PersistentMCPClient.invoke observes mcp_tool_call_duration_seconds."""
from unittest.mock import patch


def _histogram_sample_count(server_label: str, tool: str) -> float:
    """Sum of '_count' samples for the given (server_label, tool) labels."""
    from src.monitoring.metrics import mcp_tool_call_duration
    total = 0.0
    for metric in mcp_tool_call_duration.collect():
        for sample in metric.samples:
            if sample.name.endswith("_count"):
                if sample.labels.get("server_label") == server_label and sample.labels.get("tool") == tool:
                    total += sample.value
    return total


def test_invoke_observes_mcp_tool_call_duration():
    """A successful invoke() call must record one histogram sample."""
    from src.mcp.client import PersistentMCPClient

    client = PersistentMCPClient(command=["/usr/bin/python", "lead_discovery_mcp.py"])
    # Stub the inner method so we don't actually spawn a subprocess.
    with patch.object(client, "_invoke_inner", return_value={"ok": True}):
        before = _histogram_sample_count(client.server_label, "find_decision_makers")
        result = client.invoke("find_decision_makers", {"domain": "example.com"})
        after = _histogram_sample_count(client.server_label, "find_decision_makers")

    assert result == {"ok": True}
    assert after - before >= 1.0, f"expected histogram increment, before={before}, after={after}"


def test_invoke_records_metric_even_when_inner_raises():
    """Failed invocations should still be timed (the histogram should observe)."""
    from src.mcp.client import PersistentMCPClient

    client = PersistentMCPClient(command=["/usr/bin/python", "search_mcp.py"])
    before = _histogram_sample_count(client.server_label, "search")
    with patch.object(client, "_invoke_inner", side_effect=RuntimeError("boom")):
        try:
            client.invoke("search", {"q": "x"})
        except RuntimeError:
            pass
    after = _histogram_sample_count(client.server_label, "search")
    assert after - before >= 1.0


def test_server_label_defaults_from_command_basename():
    """server_label should be derived from the last command segment basename."""
    from src.mcp.client import PersistentMCPClient

    c1 = PersistentMCPClient(command=["/usr/bin/python", "/path/to/lead_discovery_mcp.py"])
    assert c1.server_label == "lead_discovery_mcp"

    c2 = PersistentMCPClient(command=["python", "search_mcp.py"], server_label="custom_label")
    assert c2.server_label == "custom_label"
