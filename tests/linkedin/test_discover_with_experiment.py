"""Tests for the experiment branch in linkedin.discover_prospects."""
from unittest.mock import patch, MagicMock


def _fake_lead(lead_id, account_id=2, **lead_attrs):
    lead = MagicMock(id=lead_id, account_id=account_id)
    for k, v in lead_attrs.items():
        setattr(lead, k, v)
    return lead


def _fake_variant(label, titles, industries=None, geographies=None):
    v = MagicMock()
    v.id = f"variant-{label}"
    v.label = label
    v.titles = titles
    v.industries = industries or ["B2B SaaS"]
    v.geographies = geographies or ["UK"]
    v.company_size_min = None
    v.company_size_max = None
    return v


def test_discover_no_experiment_falls_back_to_legacy_path():
    """No running experiment for the account -> legacy LinkedInCadenceAgent path
    runs unchanged. No ICPLeadAssignment rows are created."""
    from src.tasks.linkedin import discover_prospects

    lead = _fake_lead("lead-1")
    with patch("src.tasks.linkedin._qualified_leads", return_value=[lead]), \
         patch("src.tasks.linkedin._running_experiment", return_value=None), \
         patch("src.tasks.linkedin.LinkedInCadenceAgent") as mock_agent_cls:
        mock_agent = MagicMock()
        mock_agent._tool_add_to_prospect_queue.return_value = {"created": True}
        mock_agent_cls.return_value = mock_agent

        result = discover_prospects.run()

        mock_agent._tool_add_to_prospect_queue.assert_called_once_with("lead-1")
        assert result["created"] == 1


def test_discover_with_experiment_routes_to_variant_a_first():
    """When variant A's filters match the lead, A claims it and writes one
    ICPLeadAssignment."""
    from src.tasks.linkedin import discover_prospects

    lead = _fake_lead("lead-1", job_title="Founder", industry="B2B SaaS",
                       num_employees=30, country="UK")
    exp = MagicMock(id="exp-1", traffic_split={"A": 50, "B": 50})
    va = _fake_variant("A", titles=["Founder"])
    vb = _fake_variant("B", titles=["Co-founder"])

    created_assignments = []

    def _fake_assign(experiment_id, variant_id, lead_id):
        created_assignments.append({"experiment_id": experiment_id, "variant_id": variant_id, "lead_id": lead_id})

    with patch("src.tasks.linkedin._qualified_leads", return_value=[lead]), \
         patch("src.tasks.linkedin._running_experiment", return_value=exp), \
         patch("src.tasks.linkedin._variants_for", return_value=(va, vb)), \
         patch("src.tasks.linkedin._has_assignment", return_value=False), \
         patch("src.tasks.linkedin._create_assignment", side_effect=_fake_assign), \
         patch("src.tasks.linkedin.db.session.commit"), \
         patch("src.tasks.linkedin.LinkedInCadenceAgent") as mock_agent_cls:
        mock_agent_cls.return_value._tool_add_to_prospect_queue.return_value = {"created": True}
        discover_prospects.run()

    assert len(created_assignments) == 1
    assert created_assignments[0]["variant_id"] == "variant-A"


def test_discover_skips_lead_already_assigned_to_an_experiment():
    """A lead already in an experiment via lead_id UNIQUE must not be re-tagged."""
    from src.tasks.linkedin import discover_prospects

    lead = _fake_lead("lead-1", job_title="Founder", industry="B2B SaaS",
                       country="UK", num_employees=30)
    exp = MagicMock(id="exp-1", traffic_split={"A": 50, "B": 50})
    va = _fake_variant("A", titles=["Founder"])
    vb = _fake_variant("B", titles=["Co-founder"])

    created_assignments = []
    with patch("src.tasks.linkedin._qualified_leads", return_value=[lead]), \
         patch("src.tasks.linkedin._running_experiment", return_value=exp), \
         patch("src.tasks.linkedin._variants_for", return_value=(va, vb)), \
         patch("src.tasks.linkedin._has_assignment", return_value=True), \
         patch("src.tasks.linkedin._create_assignment", side_effect=lambda **k: created_assignments.append(k)), \
         patch("src.tasks.linkedin.db.session.commit"), \
         patch("src.tasks.linkedin.LinkedInCadenceAgent"):
        discover_prospects.run()
    assert created_assignments == [], "already-assigned lead must not be re-tagged"


def test_discover_falls_through_to_b_when_a_quota_exhausted():
    """With traffic_split={'A':50,'B':50} and budget 4, A claims 2; subsequent
    matches go to B."""
    from src.tasks.linkedin import discover_prospects
    import os

    leads = [
        _fake_lead(f"lead-{i}", job_title="Founder", industry="B2B SaaS",
                    country="UK", num_employees=30)
        for i in range(4)
    ]
    exp = MagicMock(id="exp-1", traffic_split={"A": 50, "B": 50})
    va = _fake_variant("A", titles=["Founder"])
    vb = _fake_variant("B", titles=["Founder"])  # matches too — overlap case

    created = []
    with patch.dict(os.environ, {"LEAD_DISCOVERY_MAX_LEADS": "4"}), \
         patch("src.tasks.linkedin._qualified_leads", return_value=leads), \
         patch("src.tasks.linkedin._running_experiment", return_value=exp), \
         patch("src.tasks.linkedin._variants_for", return_value=(va, vb)), \
         patch("src.tasks.linkedin._has_assignment", return_value=False), \
         patch("src.tasks.linkedin._create_assignment",
               side_effect=lambda **k: created.append(k["variant_id"])), \
         patch("src.tasks.linkedin.db.session.commit"), \
         patch("src.tasks.linkedin.LinkedInCadenceAgent"):
        discover_prospects.run()

    assert created.count("variant-A") == 2
    assert created.count("variant-B") == 2
