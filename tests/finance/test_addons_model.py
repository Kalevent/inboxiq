import pytest
from sqlalchemy.exc import IntegrityError
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


def test_addon_id_is_uuid_string(app, db):
    with app.app_context():
        account = Account(name="UUID Test Account")
        db.session.add(account)
        db.session.commit()

        addon = AccountAddOn(account_id=account.id, addon_type="finance")
        db.session.add(addon)
        db.session.commit()
        db.session.refresh(addon)

        assert isinstance(addon.id, str)
        assert len(addon.id) == 36  # standard UUID string length
        # Verify it has the UUID format (8-4-4-4-12)
        parts = addon.id.split("-")
        assert len(parts) == 5


def test_is_active(app, db):
    with app.app_context():
        account = Account(name="IsActive Test Account")
        db.session.add(account)
        db.session.commit()

        addon = AccountAddOn(account_id=account.id, addon_type="finance")
        db.session.add(addon)
        db.session.commit()
        db.session.refresh(addon)

        # Default status is "inactive" — is_active() should be False
        assert addon.is_active() is False

        # Set to active and verify
        addon.status = "active"
        db.session.commit()
        db.session.refresh(addon)

        assert addon.is_active() is True


def test_to_dict_keys(app, db):
    with app.app_context():
        account = Account(name="ToDict Test Account")
        db.session.add(account)
        db.session.commit()

        addon = AccountAddOn(account_id=account.id, addon_type="finance")
        db.session.add(addon)
        db.session.commit()
        db.session.refresh(addon)

        result = addon.to_dict()
        expected_keys = {
            "id",
            "account_id",
            "addon_type",
            "status",
            "stripe_subscription_id",
            "transactions_this_month",
            "billing_month",
            "config_json",
            "created_at",
            "updated_at",
        }
        assert set(result.keys()) == expected_keys
        assert result["created_at"] is not None


def test_unique_constraint(app, db):
    with app.app_context():
        account = Account(name="Unique Constraint Test Account")
        db.session.add(account)
        db.session.commit()

        addon1 = AccountAddOn(account_id=account.id, addon_type="finance")
        db.session.add(addon1)
        db.session.commit()

        addon2 = AccountAddOn(account_id=account.id, addon_type="finance")
        db.session.add(addon2)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
