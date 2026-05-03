"""
One-time script: exchange OAuth 2.0 Desktop credentials for a refresh token.

Usage:
  1. Download OAuth 2.0 Desktop credentials from Google Cloud Console
     and save as client_secrets.json in this directory.
  2. python get_youtube_refresh_token.py
  3. Browser opens — sign in and grant access.
  4. Copy the printed values into prod.env.
"""
from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_secrets_file(
    "client_secrets.json",
    scopes=["https://www.googleapis.com/auth/youtube.force-ssl"],
)
creds = flow.run_local_server(port=8080)

print()
print("Add these to prod.env:")
print(f"YOUTUBE_CLIENT_ID={creds.client_id}")
print(f"YOUTUBE_CLIENT_SECRET={creds.client_secret}")
print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")
