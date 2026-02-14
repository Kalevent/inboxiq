"""Check automation rule configuration and webhook providers."""
import sys
sys.path.insert(0, '/usr/src')

from src.app import create_app
from src.models import AutomationRule, WebhookProvider, AutomationRuleExecution
import json

app = create_app()

with app.app_context():
    # Get the rule
    rule_id = '26ca728b-c4cd-454f-9586-f9f4060cffd6'
    rule = AutomationRule.query.filter_by(id=rule_id).first()

    if not rule:
        print("ERROR: Rule not found!")
        sys.exit(1)

    print(f"✓ Rule: {rule.name}")
    print(f"  Account ID: {rule.account_id}")
    print(f"  Enabled: {rule.enabled}")
    print(f"\nActions ({len(rule.actions)} total):")
    for i, action in enumerate(rule.actions, 1):
        print(f"\n  Action {i}:")
        print(f"    Type: {action.get('type')}")
        print(f"    Config: {json.dumps(action.get('config', {}), indent=6)}")

    # Check webhook providers
    print(f"\n\nWebhook Providers for account {rule.account_id}:")
    providers = WebhookProvider.query.filter_by(account_id=rule.account_id).all()

    if not providers:
        print("  ❌ NO WEBHOOK PROVIDERS FOUND!")
    else:
        for p in providers:
            print(f"\n  Provider:")
            print(f"    ID: {p.id}")
            print(f"    Name: {p.configuration_name}")
            print(f"    Type: {p.provider_type}")
            print(f"    Enabled: {p.enabled}")

    # Check recent executions
    print(f"\n\nRecent Executions:")
    executions = AutomationRuleExecution.query.filter_by(
        rule_id=rule_id
    ).order_by(AutomationRuleExecution.created_at.desc()).limit(5).all()

    for ex in executions:
        print(f"\n  Execution {ex.id[:8]}...")
        print(f"    Created: {ex.created_at}")
        print(f"    Matched: {ex.matched}")
        print(f"    Executed: {ex.executed}")
        print(f"    Success: {ex.success}")
        print(f"    Error: {ex.error_message}")
        if ex.actions_executed:
            print(f"    Actions: {json.dumps(ex.actions_executed, indent=6)}")
