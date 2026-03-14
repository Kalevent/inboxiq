# Can I switch off Draft Reply in my account?

Yes. Draft Reply is enabled for all accounts by default, but you can turn it off at any time from your account settings.

## Turn off Draft Reply for your whole account

1. Go to **Settings → Features**
2. Find the **Draft Reply** toggle
3. Switch it off

Once disabled, InboxIQ will continue to classify and label incoming emails as normal, but will not generate any draft replies. You can re-enable it at any time using the same toggle.

## Turn off drafts for a specific sender or domain

If you want to keep Draft Reply on generally but suppress it for certain senders:

1. Go to **Automation Studio → New rule**
2. Set the condition: **Sender email** → **ends with** → `@example.com`
3. Set the action: **Skip draft**
4. Save and enable the rule

## Turn off drafts for a specific category

To stop drafts for a whole category (e.g. all Transactions emails):

1. Go to **Settings → Triage**
2. Find the category
3. Toggle **Draft replies** off for that category

## Related articles

- [How draft replies work](/kb/triage-and-ai/ai-draft-replies)
- [How do I stop InboxIQ drafting for a specific sender?](/kb/faq/stop-drafts-for-sender)
- [Available actions in Automation Studio](/kb/automation-studio/actions)
