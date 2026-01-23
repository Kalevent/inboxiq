# InboxIQ Dashboard User Guide

This guide shows where everything lives in the updated InboxIQ dashboard so you can get oriented quickly. The dashboard is available at `https://kalevent.com/dashboard`, and the in-app help link points to `https://kalevent.com/docs` for deeper articles.

## Access and roles
- Sign in with your Kalevent workspace credentials, then open `/dashboard`.
- If you are an admin, you will see admin-only cards and links (plan, billing, usage); standard users see work queues and metrics only.
- Keep your browser session active; the dashboard auto-refreshes lightweight stats but will prompt you if your session expires.

## Navigation at a glance
- **Header bar:** account avatar, quick links for Dashboard and Help (`/docs`), and an Admin link (when applicable).
- **Plan banner:** shows your current plan and upgrade actions; only visible if plan data is available.
- **Projects area:** create, edit, and refresh projects from the cards; upgrade prompts surface when you hit limits.
- **Usage cards:** API calls and data usage snapshots update live; use them to spot spikes.
- **Live activity feed:** real-time events streamed over WebSocket; use for quick health and adoption checks.
- **Action buttons:** shortcuts to Settings, Recommendations, Admin Dashboard (admins), and Threat Center (security roles).

## Core tasks
- **Create or manage projects:** use “+ Add Project” to add a goal and description; use the edit icon on each card to rename or update details.
- **Monitor health:** glance at the API/Data usage cards and the activity feed; if the feed stalls, refresh the page to re-open the socket.
- **Review limits:** when project limits are close, the banner suggests upgrading; click through to plan management.
- **Switch contexts:** use the header dropdown to jump to admin, dashboard, or help without leaving the page.

## Troubleshooting and tips
- If counts look stale, refresh the page to renew the session token and WebSocket.
- If you cannot see admin links, confirm your role with an admin.
- For issues with project actions, check that your browser allows cookies and that your session has not timed out.

## More help
Use the Help link in the header or visit `https://kalevent.com/docs` for feature-specific guides, FAQs, and release notes. Include the timestamp, your account email, and a short description when reporting issues.
