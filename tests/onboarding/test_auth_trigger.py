import pytest
from unittest.mock import patch, MagicMock, call


def test_first_gmail_connection_queues_onboarding_video(app):
    """queue_onboarding_video is queued when a new Gmail connection is stored."""
    with app.app_context():
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.account_id = 2

        mock_conn = MagicMock()
        mock_conn.id = "conn-1"
        mock_conn.email_address = "user@gmail.com"
        mock_conn.account_id = 2
        mock_conn.user_id = 1
        mock_conn.provider = "gmail"
        mock_conn.metadata_json = {}

        with patch("src.api.v1.auth.User") as mock_user_cls, \
             patch("src.api.v1.auth.InboxConnection") as mock_ic_cls, \
             patch("src.api.v1.auth.db") as mock_db, \
             patch("src.tasks.onboarding_video.queue_onboarding_video") as mock_task:

            # User.query.get returns our mock user
            mock_user_cls.query.get.return_value = mock_user

            # First call: filter_by(account_id=..., email_address=...) returns None
            # → is_new_connection = True
            mock_ic_cls.query.filter_by.return_value.first.return_value = None

            # InboxConnection(...) constructor returns our mock_conn
            mock_ic_cls.return_value = mock_conn

            mock_db.session.add = MagicMock()
            mock_db.session.commit = MagicMock()

            from src.api.v1.auth import _store_connection
            _store_connection(
                provider="gmail",
                email_address="user@gmail.com",
                access_token="tok",
                refresh_token=None,
                user_id=1,
            )

        mock_task.apply_async.assert_called_once()
        call_kwargs = mock_task.apply_async.call_args
        assert call_kwargs.kwargs.get("kwargs") == {"account_id": 2, "user_id": 1} or \
               call_kwargs[1].get("kwargs") == {"account_id": 2, "user_id": 1}
        # countdown must be set
        countdown = call_kwargs.kwargs.get("countdown") or call_kwargs[1].get("countdown")
        assert countdown is not None


def test_existing_gmail_connection_does_not_queue_onboarding_video(app):
    """queue_onboarding_video is NOT queued when updating an existing connection."""
    with app.app_context():
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.account_id = 2

        mock_existing_conn = MagicMock()
        mock_existing_conn.id = "conn-existing"
        mock_existing_conn.email_address = "user@gmail.com"
        mock_existing_conn.account_id = 2
        mock_existing_conn.user_id = 1
        mock_existing_conn.provider = "gmail"
        mock_existing_conn.metadata_json = {}

        with patch("src.api.v1.auth.User") as mock_user_cls, \
             patch("src.api.v1.auth.InboxConnection") as mock_ic_cls, \
             patch("src.api.v1.auth.db") as mock_db, \
             patch("src.tasks.onboarding_video.queue_onboarding_video") as mock_task:

            mock_user_cls.query.get.return_value = mock_user
            # Existing connection found → is_new_connection = False
            mock_ic_cls.query.filter_by.return_value.first.return_value = mock_existing_conn

            mock_db.session.add = MagicMock()
            mock_db.session.commit = MagicMock()

            from src.api.v1.auth import _store_connection
            _store_connection(
                provider="gmail",
                email_address="user@gmail.com",
                access_token="new-tok",
                refresh_token=None,
                user_id=1,
            )

        mock_task.apply_async.assert_not_called()


def test_first_outlook_connection_queues_onboarding_video(app):
    """queue_onboarding_video is queued for Outlook connections too."""
    with app.app_context():
        mock_user = MagicMock()
        mock_user.id = 3
        mock_user.account_id = 5

        mock_conn = MagicMock()
        mock_conn.id = "conn-outlook"
        mock_conn.email_address = "user@outlook.com"
        mock_conn.account_id = 5
        mock_conn.user_id = 3
        mock_conn.provider = "outlook"
        mock_conn.metadata_json = {}

        with patch("src.api.v1.auth.User") as mock_user_cls, \
             patch("src.api.v1.auth.InboxConnection") as mock_ic_cls, \
             patch("src.api.v1.auth.db") as mock_db, \
             patch("src.tasks.onboarding_video.queue_onboarding_video") as mock_task:

            mock_user_cls.query.get.return_value = mock_user
            mock_ic_cls.query.filter_by.return_value.first.return_value = None
            mock_ic_cls.return_value = mock_conn

            mock_db.session.add = MagicMock()
            mock_db.session.commit = MagicMock()

            from src.api.v1.auth import _store_connection
            _store_connection(
                provider="outlook",
                email_address="user@outlook.com",
                access_token="tok",
                refresh_token=None,
                user_id=3,
            )

        mock_task.apply_async.assert_called_once()
        call_kwargs = mock_task.apply_async.call_args
        kw = call_kwargs.kwargs.get("kwargs") or call_kwargs[1].get("kwargs")
        assert kw == {"account_id": 5, "user_id": 3}
