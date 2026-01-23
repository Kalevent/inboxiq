# Invite teammates

Add new users to your workspace through the team invite flow. This is the same flow used in the app at `/team/invite`.

## Send an invite
1) Go to **Team → Invite** or visit `/team/invite`.
2) Enter the teammate’s work email.
3) Click **Send invite**. An activation link is emailed so they can set a password and sign in.
4) Seat limits are enforced automatically; you’ll see an error if your workspace is full.

## Resending or sharing the link
- If the teammate does not receive the email, verify the address and ask them to check spam.
- You can resend after a short wait. In development, the activation link may also be shown inline for quick copying.

## Common issues
- **Autocomplete hides typed text:** Use the dark input style (`input-dark`) on the invite field to ensure Chrome autofill does not overlay a white background.
- **Seat limit reached:** Remove or downgrade existing seats before sending a new invite.
- **Invalid email:** Only valid email addresses are accepted.
