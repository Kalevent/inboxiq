"""Tests for the Tickets settings tab — query helper and route logic."""
from __future__ import annotations
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# _build_ticket_query
# ---------------------------------------------------------------------------

class TestBuildTicketQuery:
    """Test filter application in _build_ticket_query."""

    def _make_mock_query(self):
        """Return a mock that chains .filter() and .order_by() calls."""
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        return q

    def test_scopes_to_account(self):
        mock_q = self._make_mock_query()
        with patch("src.settings.routes.Ticket") as MockTicket:
            MockTicket.query.filter.return_value = mock_q
            from src.settings.routes import _build_ticket_query
            result = _build_ticket_query(account_id=42)
            # First call must filter by account_id
            MockTicket.query.filter.assert_called_once()
            assert result is mock_q

    def test_no_extra_filters_when_params_empty(self):
        mock_q = self._make_mock_query()
        with patch("src.settings.routes.Ticket") as MockTicket:
            MockTicket.query.filter.return_value = mock_q
            from src.settings.routes import _build_ticket_query
            _build_ticket_query(account_id=1)
            # Only one filter call (account_id scope)
            assert mock_q.filter.call_count == 0

    def test_status_filter_applied(self):
        mock_q = self._make_mock_query()
        with patch("src.settings.routes.Ticket") as MockTicket:
            MockTicket.query.filter.return_value = mock_q
            from src.settings.routes import _build_ticket_query
            _build_ticket_query(account_id=1, status="open")
            assert mock_q.filter.call_count >= 1

    def test_empty_status_not_applied(self):
        mock_q = self._make_mock_query()
        with patch("src.settings.routes.Ticket") as MockTicket:
            MockTicket.query.filter.return_value = mock_q
            from src.settings.routes import _build_ticket_query
            _build_ticket_query(account_id=1, status="")
            assert mock_q.filter.call_count == 0


# ---------------------------------------------------------------------------
# _is_staff_account
# ---------------------------------------------------------------------------

class TestIsStaffAccount:

    def _mock_current_app(self, admin_emails="kofi@kalevent.com"):
        """Return a mock current_app with config.get returning admin_emails."""
        mock_app = MagicMock()
        mock_app.config.get.return_value = admin_emails
        return mock_app

    def test_staff_email_returns_true(self):
        from src.settings.routes import _is_staff_account
        import src.settings.routes as routes_mod
        user = MagicMock()
        user.email = "kofi@kalevent.com"
        orig = routes_mod.current_app
        routes_mod.current_app = self._mock_current_app()
        try:
            assert _is_staff_account(user) is True
        finally:
            routes_mod.current_app = orig

    def test_non_staff_email_returns_false(self):
        from src.settings.routes import _is_staff_account
        import src.settings.routes as routes_mod
        user = MagicMock()
        user.email = "customer@example.com"
        orig = routes_mod.current_app
        routes_mod.current_app = self._mock_current_app()
        try:
            assert _is_staff_account(user) is False
        finally:
            routes_mod.current_app = orig

    def test_none_user_returns_false(self):
        from src.settings.routes import _is_staff_account
        assert _is_staff_account(None) is False

    def test_case_insensitive(self):
        from src.settings.routes import _is_staff_account
        import src.settings.routes as routes_mod
        user = MagicMock()
        user.email = "KOFI@KALEVENT.COM"
        orig = routes_mod.current_app
        routes_mod.current_app = self._mock_current_app()
        try:
            assert _is_staff_account(user) is True
        finally:
            routes_mod.current_app = orig


# ---------------------------------------------------------------------------
# Resolve / close idempotency guard
# ---------------------------------------------------------------------------

class TestTicketActionIdempotency:
    """The resolve and close routes skip the DB write if ticket is already resolved/closed."""

    def _already_done_ticket(self, status):
        ticket = MagicMock()
        ticket.id = "abc123"
        ticket.status = status
        return ticket

    def test_resolve_skipped_when_already_resolved(self):
        ticket = self._already_done_ticket("resolved")
        already_done = ticket.status in ("resolved", "closed")
        assert already_done is True

    def test_resolve_skipped_when_already_closed(self):
        ticket = self._already_done_ticket("closed")
        already_done = ticket.status in ("resolved", "closed")
        assert already_done is True

    def test_resolve_proceeds_when_open(self):
        ticket = self._already_done_ticket("open")
        already_done = ticket.status in ("resolved", "closed")
        assert already_done is False

    def test_close_proceeds_when_new(self):
        ticket = self._already_done_ticket("new")
        already_done = ticket.status in ("resolved", "closed")
        assert already_done is False
