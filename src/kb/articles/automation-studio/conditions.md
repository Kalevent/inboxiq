# Available conditions

Conditions determine when an automation rule fires. You can combine multiple conditions — all must be true for the rule to trigger.

## Condition types

| Condition | Values |
|---|---|
| `category` | Support, Billing, Transactions, Updates, Promotions, Social, Forums |
| `priority` | P1 (urgent), Normal |
| `sentiment` | Frustrated, Neutral, Positive |
| `is_automated` | True / False — whether the sender is an automated system |
| `action_required` | True / False — whether the email requires a human response |
| `sender_domain` | Any domain string, e.g. `stripe.com` |

## Examples

**All frustrated support emails:**
- `category = Support` AND `sentiment = Frustrated`

**Automated billing receipts only:**
- `category = Billing` AND `is_automated = True`

**All urgent emails:**
- `priority = P1`

**Emails from a specific domain:**
- `sender_domain = stripe.com`

## Combining conditions

All conditions in a rule use AND logic. For OR logic, create two separate rules that share the same action.

## Related articles

- [Available actions](/kb/automation-studio/actions)
- [Rule recipes and examples](/kb/automation-studio/rule-recipes)
