import pytest
from src.extensions import db
from src.models.addons import AccountAddOn
from src.models.core import Account


def test_addon_defaults(app, db):
    with app.app_context():
        # Create a test account first
        account = Account(name="Test Account")
        db.session.add(account)
        db.session.commit()

        # Create addon and commit to see defaults applied
        addon = AccountAddOn(account_id=account.id, addon_type="finance")
        db.session.add(addon)
        db.session.commit()

        # Refresh to get the defaults from DB
        db.session.refresh(addon)

        assert addon.status == "inactive"
        assert addon.transactions_this_month == 0
        assert addon.config_json == {}
