from unittest.mock import patch, MagicMock

# Call .run() on Celery tasks to bypass the ContextTask wrapper (which would
# push a separate app context with a different in-memory SQLite database).


def test_discover_prospects_creates_record_for_qualifying_lead(db):
    """A Lead with linkedin_url and fit_score >= 7 becomes a LinkedInProspect via the agent tool."""
    from src.models.leads import Lead
    from src.models.campaigns import LinkedInProspect
    from unittest.mock import patch

    lead = Lead(
        id="lead-001", account_id=1, name="Alice Smith",
        email="alice@acmesaas.com", company_name="Acme SaaS",
        source="linkedin", linkedin_url="https://linkedin.com/in/alice",
        status="New Lead", fit_score=8, deleted=False,
    )
    db.session.add(lead)
    db.session.commit()

    # Test the tool directly
    from src.agents.linkedin_cadence import LinkedInCadenceAgent
    agent = LinkedInCadenceAgent(account_id=1)
    result = agent._tool_add_to_prospect_queue("lead-001")
    assert result["created"] is True

    prospect = db.session.query(LinkedInProspect).filter_by(
        linkedin_url="https://linkedin.com/in/alice", account_id=1
    ).first()
    assert prospect is not None
    assert prospect.status == "pending"


def test_discover_prospects_skips_low_fit_score(db):
    """Leads with fit_score < 7 are not added to the queue."""
    from src.models.leads import Lead
    from src.models.campaigns import LinkedInProspect

    lead = Lead(
        id="lead-002",
        account_id=1,
        name="Bob Jones",
        email="bob@example.com",
        source="linkedin",
        linkedin_url="https://linkedin.com/in/bobjones",
        status="New Lead",
        fit_score=5,
        deleted=False,
    )
    db.session.add(lead)
    db.session.commit()

    from src.tasks.linkedin import discover_prospects
    discover_prospects.run()

    prospect = db.session.query(LinkedInProspect).filter_by(
        linkedin_url="https://linkedin.com/in/bobjones"
    ).first()
    assert prospect is None


def test_discover_prospects_no_duplicate(db):
    """Running discover twice does not create a second LinkedInProspect."""
    from src.models.leads import Lead
    from src.models.campaigns import LinkedInProspect

    lead = Lead(
        id="lead-003",
        account_id=1,
        name="Carol White",
        email="carol@example.com",
        source="linkedin",
        linkedin_url="https://linkedin.com/in/carolwhite",
        status="New Lead",
        fit_score=9,
        deleted=False,
    )
    db.session.add(lead)
    db.session.commit()

    from src.tasks.linkedin import discover_prospects
    discover_prospects.run()
    discover_prospects.run()

    count = db.session.query(LinkedInProspect).filter_by(
        linkedin_url="https://linkedin.com/in/carolwhite", account_id=1
    ).count()
    assert count == 1


def test_send_digest_core_returns_empty_when_no_prospects(db):
    """_send_digest_core returns sent=False when no prospects are due.

    The test app config has no ADMIN_EMAILS set, so _send_digest_core
    short-circuits immediately with sent=False, count=0.
    """
    from src.tasks.linkedin import _send_digest_core

    result = _send_digest_core(account_id=1)

    assert result["sent"] is False
    assert result["count"] == 0


def test_draft_messages_task_calls_agent_execute(db):
    """draft_messages_task calls LinkedInCadenceAgent.execute for each account."""
    from unittest.mock import patch, MagicMock

    with patch("src.tasks.linkedin._all_account_ids", return_value=[1]), \
         patch("src.agents.linkedin_cadence.LinkedInCadenceAgent.execute") as mock_execute:
        from src.tasks.linkedin import draft_messages_task
        draft_messages_task.run()
        mock_execute.assert_called_once()
