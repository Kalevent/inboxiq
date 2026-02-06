"""
Google Calendar MCP server for Leads Funnel v2.0

Free alternative to Calendly for demo scheduling.
Integrates with Google Calendar API to manage availability and book meetings.

Tools:
- get_available_slots: Get available time slots for booking
- create_meeting: Create new calendar event
- list_upcoming_meetings: List scheduled meetings
- cancel_meeting: Cancel existing meeting
- get_meeting_details: Get details of specific meeting
- update_meeting: Update meeting details

Env:
- GOOGLE_CALENDAR_CREDENTIALS_FILE: Path to service account or OAuth credentials JSON
- GOOGLE_CALENDAR_ID: Calendar ID (default: primary)
- GOOGLE_CALENDAR_TIMEZONE: Timezone (default: America/New_York)

Setup:
1. Create Google Cloud Project: https://console.cloud.google.com
2. Enable Google Calendar API
3. Create service account or OAuth 2.0 credentials
4. Download credentials JSON file
5. Set GOOGLE_CALENDAR_CREDENTIALS_FILE environment variable
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, time
from typing import Any, Dict, List, Optional
import json

try:
    from mcp.server.fastmcp import FastMCP, Context, ToolError
except ImportError:
    from mcp.server.fastmcp import FastMCP, Context
    try:
        from mcp.types import ToolError
    except ImportError:
        class ToolError(Exception):
            pass

# Try to import Google Calendar API
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False


mcp = FastMCP("gcal-mcp")

CREDENTIALS_FILE = os.getenv("GOOGLE_CALENDAR_CREDENTIALS_FILE")
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")
TIMEZONE = os.getenv("GOOGLE_CALENDAR_TIMEZONE", "America/New_York")

# Business hours configuration
BUSINESS_HOURS_START = time(9, 0)  # 9:00 AM
BUSINESS_HOURS_END = time(17, 0)  # 5:00 PM
MEETING_DURATION_MINUTES = 30
BUFFER_MINUTES = 15  # Buffer between meetings


def get_calendar_service():
    """Initialize Google Calendar API service"""
    if not GOOGLE_AVAILABLE:
        raise ToolError(
            "Google Calendar API not available. Install: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client"
        )

    if not CREDENTIALS_FILE or not os.path.exists(CREDENTIALS_FILE):
        raise ToolError(
            "Google Calendar credentials not found. Set GOOGLE_CALENDAR_CREDENTIALS_FILE environment variable."
        )

    try:
        with open(CREDENTIALS_FILE, 'r') as f:
            cred_data = json.load(f)

        # Check if service account or OAuth credentials
        if "type" in cred_data and cred_data["type"] == "service_account":
            credentials = service_account.Credentials.from_service_account_file(
                CREDENTIALS_FILE,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
        else:
            raise ToolError(
                "OAuth credentials not yet supported. Use service account credentials."
            )

        service = build('calendar', 'v3', credentials=credentials)
        return service
    except Exception as e:
        raise ToolError(f"Failed to initialize Google Calendar service: {e}")


@mcp.tool()
def get_available_slots(
    start_date: str,
    end_date: Optional[str] = None,
    duration_minutes: int = 30,
    timezone: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get available time slots for booking within date range.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD, defaults to start_date)
        duration_minutes: Meeting duration (default: 30)
        timezone: Timezone (default: from env or America/New_York)

    Returns:
        Dict with list of available time slots
    """
    if not end_date:
        end_date = start_date

    tz = timezone or TIMEZONE

    service = get_calendar_service()

    try:
        # Parse dates
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)

        # Get busy times from calendar
        body = {
            "timeMin": start_dt.isoformat() + 'Z',
            "timeMax": end_dt.isoformat() + 'Z',
            "timeZone": tz,
            "items": [{"id": CALENDAR_ID}]
        }

        events_result = service.freebusy().query(body=body).execute()
        busy_times = events_result['calendars'][CALENDAR_ID]['busy']

        # Generate available slots
        available_slots = []
        current_date = start_dt.date()
        end_date_obj = end_dt.date()

        while current_date <= end_date_obj:
            # Skip weekends
            if current_date.weekday() >= 5:  # Saturday = 5, Sunday = 6
                current_date += timedelta(days=1)
                continue

            # Generate time slots for business hours
            slot_start = datetime.combine(current_date, BUSINESS_HOURS_START)
            day_end = datetime.combine(current_date, BUSINESS_HOURS_END)

            while slot_start + timedelta(minutes=duration_minutes) <= day_end:
                slot_end = slot_start + timedelta(minutes=duration_minutes)

                # Check if slot overlaps with busy time
                is_available = True
                for busy in busy_times:
                    busy_start = datetime.fromisoformat(busy['start'].replace('Z', '+00:00'))
                    busy_end = datetime.fromisoformat(busy['end'].replace('Z', '+00:00'))

                    if (slot_start < busy_end and slot_end > busy_start):
                        is_available = False
                        break

                if is_available:
                    available_slots.append({
                        "start": slot_start.isoformat(),
                        "end": slot_end.isoformat(),
                        "duration_minutes": duration_minutes
                    })

                # Move to next slot (with buffer)
                slot_start += timedelta(minutes=duration_minutes + BUFFER_MINUTES)

            current_date += timedelta(days=1)

        return {
            "start_date": start_date,
            "end_date": end_date,
            "timezone": tz,
            "duration_minutes": duration_minutes,
            "available_slots": available_slots,
            "total_slots": len(available_slots)
        }

    except HttpError as e:
        raise ToolError(f"Google Calendar API error: {e}")
    except Exception as e:
        raise ToolError(f"Failed to get available slots: {e}")


@mcp.tool()
def create_meeting(
    summary: str,
    start_time: str,
    end_time: str,
    attendee_emails: List[str],
    description: Optional[str] = None,
    location: Optional[str] = None,
    timezone: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a new calendar event.

    Args:
        summary: Meeting title
        start_time: Start time (ISO format: 2026-02-04T14:00:00)
        end_time: End time (ISO format: 2026-02-04T14:30:00)
        attendee_emails: List of attendee email addresses
        description: Meeting description (optional)
        location: Meeting location or video link (optional)
        timezone: Timezone (default: from env or America/New_York)

    Returns:
        Dict with meeting details and calendar link
    """
    tz = timezone or TIMEZONE
    service = get_calendar_service()

    event = {
        'summary': summary,
        'description': description or '',
        'location': location or 'Google Meet',
        'start': {
            'dateTime': start_time,
            'timeZone': tz,
        },
        'end': {
            'dateTime': end_time,
            'timeZone': tz,
        },
        'attendees': [{'email': email} for email in attendee_emails],
        'conferenceData': {
            'createRequest': {
                'requestId': f"meet-{datetime.now().timestamp()}",
                'conferenceSolutionKey': {'type': 'hangoutsMeet'}
            }
        },
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'email', 'minutes': 24 * 60},  # 1 day before
                {'method': 'popup', 'minutes': 30},  # 30 minutes before
            ],
        },
    }

    try:
        event = service.events().insert(
            calendarId=CALENDAR_ID,
            body=event,
            conferenceDataVersion=1,
            sendUpdates='all'
        ).execute()

        return {
            "event_id": event['id'],
            "summary": event['summary'],
            "start_time": event['start'].get('dateTime', event['start'].get('date')),
            "end_time": event['end'].get('dateTime', event['end'].get('date')),
            "attendees": [a['email'] for a in event.get('attendees', [])],
            "html_link": event['htmlLink'],
            "meet_link": event.get('conferenceData', {}).get('entryPoints', [{}])[0].get('uri'),
            "message": "Meeting created successfully"
        }

    except HttpError as e:
        raise ToolError(f"Google Calendar API error: {e}")
    except Exception as e:
        raise ToolError(f"Failed to create meeting: {e}")


@mcp.tool()
def list_upcoming_meetings(
    days_ahead: int = 7,
    max_results: int = 50
) -> Dict[str, Any]:
    """
    List upcoming meetings from calendar.

    Args:
        days_ahead: Number of days to look ahead (default: 7)
        max_results: Maximum number of events to return (default: 50)

    Returns:
        Dict with list of upcoming meetings
    """
    service = get_calendar_service()

    try:
        now = datetime.utcnow()
        time_max = now + timedelta(days=days_ahead)

        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=now.isoformat() + 'Z',
            timeMax=time_max.isoformat() + 'Z',
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        meetings = []
        for event in events:
            meetings.append({
                "event_id": event['id'],
                "summary": event.get('summary', 'No title'),
                "start_time": event['start'].get('dateTime', event['start'].get('date')),
                "end_time": event['end'].get('dateTime', event['end'].get('date')),
                "attendees": [a['email'] for a in event.get('attendees', [])],
                "location": event.get('location'),
                "html_link": event.get('htmlLink')
            })

        return {
            "days_ahead": days_ahead,
            "total_meetings": len(meetings),
            "meetings": meetings
        }

    except HttpError as e:
        raise ToolError(f"Google Calendar API error: {e}")
    except Exception as e:
        raise ToolError(f"Failed to list meetings: {e}")


@mcp.tool()
def cancel_meeting(
    event_id: str,
    send_updates: bool = True
) -> Dict[str, Any]:
    """
    Cancel an existing calendar event.

    Args:
        event_id: Google Calendar event ID
        send_updates: Send cancellation emails to attendees (default: True)

    Returns:
        Dict with cancellation confirmation
    """
    service = get_calendar_service()

    try:
        service.events().delete(
            calendarId=CALENDAR_ID,
            eventId=event_id,
            sendUpdates='all' if send_updates else 'none'
        ).execute()

        return {
            "event_id": event_id,
            "cancelled": True,
            "send_updates": send_updates,
            "message": "Meeting cancelled successfully"
        }

    except HttpError as e:
        raise ToolError(f"Google Calendar API error: {e}")
    except Exception as e:
        raise ToolError(f"Failed to cancel meeting: {e}")


@mcp.tool()
def get_meeting_details(event_id: str) -> Dict[str, Any]:
    """
    Get details of a specific calendar event.

    Args:
        event_id: Google Calendar event ID

    Returns:
        Dict with full meeting details
    """
    service = get_calendar_service()

    try:
        event = service.events().get(
            calendarId=CALENDAR_ID,
            eventId=event_id
        ).execute()

        return {
            "event_id": event['id'],
            "summary": event.get('summary', 'No title'),
            "description": event.get('description'),
            "location": event.get('location'),
            "start_time": event['start'].get('dateTime', event['start'].get('date')),
            "end_time": event['end'].get('dateTime', event['end'].get('date')),
            "attendees": [
                {
                    "email": a['email'],
                    "response_status": a.get('responseStatus', 'needsAction'),
                    "organizer": a.get('organizer', False)
                }
                for a in event.get('attendees', [])
            ],
            "html_link": event['htmlLink'],
            "meet_link": event.get('conferenceData', {}).get('entryPoints', [{}])[0].get('uri'),
            "status": event.get('status'),
            "created": event.get('created'),
            "updated": event.get('updated')
        }

    except HttpError as e:
        raise ToolError(f"Google Calendar API error: {e}")
    except Exception as e:
        raise ToolError(f"Failed to get meeting details: {e}")


@mcp.tool()
def update_meeting(
    event_id: str,
    summary: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    send_updates: bool = True
) -> Dict[str, Any]:
    """
    Update an existing calendar event.

    Args:
        event_id: Google Calendar event ID
        summary: New meeting title (optional)
        start_time: New start time in ISO format (optional)
        end_time: New end time in ISO format (optional)
        description: New description (optional)
        location: New location (optional)
        send_updates: Send update emails to attendees (default: True)

    Returns:
        Dict with updated meeting details
    """
    service = get_calendar_service()

    try:
        # Get existing event
        event = service.events().get(
            calendarId=CALENDAR_ID,
            eventId=event_id
        ).execute()

        # Update fields
        if summary:
            event['summary'] = summary
        if description:
            event['description'] = description
        if location:
            event['location'] = location
        if start_time:
            event['start']['dateTime'] = start_time
        if end_time:
            event['end']['dateTime'] = end_time

        # Update event
        updated_event = service.events().update(
            calendarId=CALENDAR_ID,
            eventId=event_id,
            body=event,
            sendUpdates='all' if send_updates else 'none'
        ).execute()

        return {
            "event_id": updated_event['id'],
            "summary": updated_event.get('summary'),
            "start_time": updated_event['start'].get('dateTime', updated_event['start'].get('date')),
            "end_time": updated_event['end'].get('dateTime', updated_event['end'].get('date')),
            "html_link": updated_event['htmlLink'],
            "message": "Meeting updated successfully"
        }

    except HttpError as e:
        raise ToolError(f"Google Calendar API error: {e}")
    except Exception as e:
        raise ToolError(f"Failed to update meeting: {e}")


if __name__ == "__main__":
    mcp.run()
