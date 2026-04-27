from unittest.mock import patch, MagicMock

# Call .run() on Celery tasks to bypass the ContextTask wrapper (which would
# push a separate app context with a different in-memory SQLite database).


def test_discover_prospects_creates_record_for_qualifying_lead(db):
    """A Lead with source=linkedin and fit_score >= 7 becomes a LinkedInProspect."""
    from src.models.leads import Lead
    from src.models.campaigns import LinkedInProspect

    lead = Lead(
        id="lead-001",
        account_id=1,
        name="Alice Smith",
        email="alice@acmesaas.com",
        company_name="Acme SaaS",
        source="linkedin",
        linkedin_url="https://linkedin.com/in/alice",
        status="New Lead",
        fit_score=8,
        deleted=False,
    )
    db.session.add(lead)
    db.session.commit()

    from src.tasks.linkedin import discover_prospects
    discover_prospects.run()

    prospect = db.session.query(LinkedInProspect).filter_by(
        linkedin_url="https://linkedin.com/in/alice", account_id=1
    ).first()
    assert prospect is not None
    assert prospect.status == "pending"
    assert prospect.source == "auto"


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


def test_draft_messages_saves_drafts(db):
    """draft_messages_task sets msg_1_draft, msg_2_draft, msg_3_draft on pending prospects."""
    from src.models.campaigns import LinkedInProspect

    prospect = LinkedInProspect(
        account_id=1,
        name="Dave Chen",
        company_name="BuildStack",
        job_title="Founder",
        industry="B2B SaaS",
        linkedin_url="https://linkedin.com/in/davechen",
        status="pending",
    )
    db.session.add(prospect)
    db.session.commit()

    mock_draft = MagicMock()
    mock_draft.msg_1 = "Hi Dave, would love to connect."
    mock_draft.msg_2 = "Thought this post might be useful."
    mock_draft.msg_3 = "Would a 15-min call make sense?"

    mock_post_match = MagicMock()
    mock_post_match.selected_slug = "customer-support-automation-benefits"
    mock_post_match.reason = "Relevant to Founder in B2B SaaS."

    with patch("src.tasks.linkedin._configure_dspy"), \
         patch("src.tasks.linkedin.MessageDrafterModule") as MockDrafter, \
         patch("src.tasks.linkedin.BlogPostMatcherModule") as MockMatcher, \
         patch("src.tasks.linkedin._get_published_posts", return_value=[]):
        MockDrafter.return_value.return_value = mock_draft
        MockMatcher.return_value.return_value = mock_post_match

        from src.tasks.linkedin import draft_messages_task
        draft_messages_task.run()

    db.session.refresh(prospect)
    assert prospect.msg_1_draft == "Hi Dave, would love to connect."
    assert prospect.msg_2_draft == "Thought this post might be useful."
    assert prospect.msg_3_draft == "Would a 15-min call make sense?"
