def test_metric_registry_has_linkedin_metrics():
    from src.monitoring import metrics  # importing registers them
    from prometheus_client import REGISTRY
    names = {m.name for m in REGISTRY.collect()}
    expected = {
        "inboxiq_linkedin_prospect_status_transitions",
        "inboxiq_agent_react_max_iters_hit",
        "inboxiq_agent_status",
        "inboxiq_mcp_tool_call_duration_seconds",
        "inboxiq_linkedin_acceptance_ratio",
    }
    missing = expected - names
    # prometheus_client may suffix counters with "_total"; check both
    for n in list(missing):
        if f"{n}_total" in names or n in names:
            missing.discard(n)
    assert not missing, f"missing metrics: {missing}; available: {sorted(n for n in names if 'inboxiq' in n)}"


def test_linkedin_status_transition_increments_counter():
    from src.monitoring.metrics import linkedin_status_transitions
    before = linkedin_status_transitions.labels(
        from_status="pending", to_status="connection_sent", account_id="1"
    )._value.get()
    linkedin_status_transitions.labels(
        from_status="pending", to_status="connection_sent", account_id="1"
    ).inc()
    after = linkedin_status_transitions.labels(
        from_status="pending", to_status="connection_sent", account_id="1"
    )._value.get()
    assert after - before == 1
