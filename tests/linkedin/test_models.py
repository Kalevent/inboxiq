from src.models.campaigns import LinkedInProspect


def test_linkedin_prospect_defaults(db):
    p = LinkedInProspect(
        account_id=1,
        name="Alice Smith",
        linkedin_url="https://linkedin.com/in/alice",
    )
    db.session.add(p)
    db.session.commit()
    assert p.status == "pending"
    assert p.source == "auto"
    assert p.id is not None


def test_linkedin_prospect_unique_url_per_account(db):
    p1 = LinkedInProspect(account_id=1, name="Alice", linkedin_url="https://linkedin.com/in/alice")
    p2 = LinkedInProspect(account_id=1, name="Alice Dup", linkedin_url="https://linkedin.com/in/alice")
    db.session.add(p1)
    db.session.commit()
    db.session.add(p2)
    import pytest
    with pytest.raises(Exception):
        db.session.commit()


def test_linkedin_prospect_same_url_different_account(db):
    p1 = LinkedInProspect(account_id=1, name="Alice", linkedin_url="https://linkedin.com/in/alice")
    p2 = LinkedInProspect(account_id=2, name="Alice", linkedin_url="https://linkedin.com/in/alice")
    db.session.add_all([p1, p2])
    db.session.commit()
    assert p1.id != p2.id
