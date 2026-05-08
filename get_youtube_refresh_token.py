"""
One-time script: exchange OAuth 2.0 Desktop credentials for a refresh token.

Usage:
  1. Download OAuth 2.0 Desktop credentials from Google Cloud Console
     and save as client_secrets.json in this directory.
  2. python get_youtube_refresh_token.py
  3. Browser opens. Sign in as the Google account that has access to the
     InboxIQ YouTube channel. If the channel is a Brand Account (most
     channels named after a business are), the channel chooser appears
     AFTER sign-in. Pick the InboxIQ brand channel, NOT your personal
     Google account's default channel. The youtubeSignupRequired 401 on
     upload means the chosen identity has no channel attached.
  4. Copy the printed values into prod.env (or kubectl patch secret
     inboxiq-env in the kaley namespace).
"""
from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_secrets_file(
    "client_secrets.json",
    scopes=["https://www.googleapis.com/auth/youtube.force-ssl"],
)
# select_account forces the Google account chooser even if you're already
# signed in (so you don't accidentally re-mint a token against the same
# account-without-a-channel). consent forces a fresh refresh_token to be
# returned (Google omits it on subsequent grants otherwise).
# access_type=offline is required for refresh_token issuance.
creds = flow.run_local_server(
    port=8080,
    access_type="offline",
    prompt="consent select_account",
    include_granted_scopes="true",
)

print()
print("Add these to prod.env:")
print(f"YOUTUBE_CLIENT_ID={creds.client_id}")
print(f"YOUTUBE_CLIENT_SECRET={creds.client_secret}")
print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")
