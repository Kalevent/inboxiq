# How rules work

Automation Studio lets you create rules that fire automatically after InboxIQ has triaged an email. Rules use the AI classification output as conditions — something no native Gmail filter or Outlook rule can do.

## Rule structure

Each rule has three parts:

1. **Name** — a label for your own reference.
2. **Conditions** — criteria that must be met for the rule to fire. You can combine multiple conditions with AND logic.
3. **Actions** — what happens when conditions are met.

## When rules fire

Rules fire **after triage** — after the email has been classified with category, priority, and sentiment. This means you can write conditions like `category = Billing AND sentiment = Frustrated` that would be impossible in a native email filter.

## Creating a rule

1. Go to **Settings → Integrations → Automation Studio** → **Manage Automation Rules**.
2. Click **New rule**.
3. Enter a name, add your conditions, and choose an action.
4. Click **Save**. The rule is active immediately.

## Rules apply across all connected inboxes

One set of rules covers every inbox connected to your account — yours and any teammate inboxes you've invited.

## Related articles

- [Available conditions](/kb/automation-studio/conditions)
- [Available actions](/kb/automation-studio/actions)
- [Rule recipes and examples](/kb/automation-studio/rule-recipes)
