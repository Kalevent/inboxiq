"""Tests for the Tickets settings tab — query helper and route logic."""
from __future__ import annotations
from unittest.mock import MagicMock, patch, call
import pytest


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
