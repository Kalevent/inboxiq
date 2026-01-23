# Security (Passkeys & 2FA)

Use the Security tab in Settings to enable passwordless sign-in and two-factor authentication.

## Passkeys (WebAuthn)
- Requirements: modern browser with WebAuthn and a platform/hardware authenticator.
- Production: set `PASSKEY_RP_ID` to your HTTPS domain. Locally, the host (e.g., localhost) is used.
- Enroll:
  1) Go to **Settings → Security → Passkeys**.
  2) Click **Register passkey** and complete the browser prompt.
  3) Your passkey appears in the list; you can register multiple keys per user.

## TOTP 2FA (Authenticator App)
- Requirements: any TOTP app (Google Authenticator, Authy, etc.).
- Enroll:
  1) Go to **Settings → Security → Two-factor auth**.
  2) Click **Start setup** to generate a secret, scan it in your app, then enter the 6-digit code and click **Verify**.
  3) Existing devices show in the list; **Disable 2FA** removes all TOTP devices for your account.

## Notes
- CSRF is handled automatically by the settings UI for these flows.
- Database: `passkeys` stores WebAuthn credentials; `totp_devices` stores TOTP secrets (added via migration).
- Troubleshooting: if you see RP ID/origin errors locally, use the same host as `PASSKEY_RP_ID` (e.g., localhost) and prefer HTTPS in production.
