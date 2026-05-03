import pytest
from datetime import datetime, timezone
from src.models.leads import ICPPainPoint


def test_icp_pain_point_creation(db):
    pp = ICPPainPoint(
        account_id=1,
        icp_config_id="test-config-id",
        pain_point="Support emails pile up unread over the weekend",
        consequence="Customers churn before Monday",
        persona="Head of Support",
        priority=10,
    )
    db.session.add(pp)
    db.session.commit()
    fetched = db.session.get(ICPPainPoint, pp.id)
    assert fetched.pain_point == "Support emails pile up unread over the weekend"
    assert fetched.active is True
    assert fetched.priority == 10


def test_icp_pain_point_requires_pain_point_and_consequence(db):
    with pytest.raises(Exception):
        pp = ICPPainPoint(account_id=1, icp_config_id="x")
        db.session.add(pp)
        db.session.commit()
    db.session.rollback()
