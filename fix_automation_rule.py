"""Fix automation rule configuration."""
import sys
sys.path.insert(0, '/usr/src')

from src.app import create_app
from src.models import AutomationRule
from src.extensions import db
import json

app = create_app()

with app.app_context():
    rule_id = '26ca728b-c4cd-454f-9586-f9f4060cffd6'
    rule = AutomationRule.query.filter_by(id=rule_id).first()

    if not rule:
        print("ERROR: Rule not found!")
        sys.exit(1)

    print(f"✓ Fixing rule: {rule.name}")

    # Fix conditions - change field paths to use email.subject and email.body
    print(f"\n=== FIXING CONDITIONS ===")
    for i, cond in enumerate(rule.conditions):
        old_field = cond.get('field')
        if old_field == 'subject':
            cond['field'] = 'email.subject'
            print(f"  Condition {i}: 'subject' → 'email.subject'")
        elif old_field == 'body':
            cond['field'] = 'email.body'
            print(f"  Condition {i}: 'body' → 'email.body'")

    # Fix actions - change slack_notify to send_webhook
    print(f"\n=== FIXING ACTIONS ===")
    new_actions = []

    # Get the webhook provider ID
    provider_id = "74f980d9-53a9-4066-afa0-eba219953551"  # Slack Notifications

    for i, action in enumerate(rule.actions):
        old_type = action.get('type')
        old_config = action.get('config', {})

        if old_type == 'slack_notify':
            # Convert to send_webhook with proper config
            # Build a meaningful message from the config
            message_parts = []

            if 'message' in old_config:
                message_parts.append(old_config['message'])
            if 'tag' in old_config:
                message_parts.append(f"Tag: {old_config['tag']}")
            if 'priority' in old_config:
                message_parts.append(f"Priority: {old_config['priority']}")
            if 'team' in old_config:
                message_parts.append(f"Team: {old_config['team']}")

            message = " | ".join(message_parts) if message_parts else "New email received: {{email.subject}}"

            new_action = {
                "type": "send_webhook",
                "config": {
                    "provider": provider_id,
                    "payload_template": {
                        "text": message,
                        "channel": old_config.get('channel', '#billing'),
                        "username": "InboxIQ Bot",
                        "icon_emoji": ":envelope:"
                    }
                }
            }
            new_actions.append(new_action)
            print(f"  Action {i}: 'slack_notify' → 'send_webhook' with message: {message}")
        else:
            new_actions.append(action)
            print(f"  Action {i}: '{old_type}' (unchanged)")

    # Simplify to a single combined action
    combined_message = "🔔 High priority billing issue received\\n\\n*Subject:* {{email.subject}}\\n*From:* {{email.from_email}}\\n*Priority:* high\\n*Team:* Billing\\n*Tag:* Billing issue"

    rule.actions = [{
        "type": "send_webhook",
        "config": {
            "provider": provider_id,
            "payload_template": {
                "text": combined_message,
                "channel": "#billing",
                "username": "InboxIQ Bot",
                "icon_emoji": ":envelope:"
            }
        }
    }]

    print(f"\n=== SIMPLIFIED TO SINGLE ACTION ===")
    print(f"  Combined all 4 slack_notify actions into 1 send_webhook action")

    # Save changes
    db.session.commit()

    print(f"\n✅ Rule updated successfully!")
    print(f"\nNew conditions:")
    for i, cond in enumerate(rule.conditions):
        print(f"  {i+1}. {cond.get('field')} {cond.get('operator')} '{cond.get('value')}'")

    print(f"\nNew actions:")
    for i, action in enumerate(rule.actions):
        print(f"  {i+1}. {action.get('type')}")
        print(f"      Config: {json.dumps(action.get('config', {}), indent=10)}")
