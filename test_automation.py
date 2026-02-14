"""Test automation workflow execution directly."""
import sys
sys.path.insert(0, '/usr/src')

from src.app import create_app
from src.models import AutomationRule, Ticket
from src.automation.workflow_engine import execute_automation_workflow
from src.automation.template_engine import build_context
import json

app = create_app()

with app.app_context():
    # Get the rule
    rule_id = '26ca728b-c4cd-454f-9586-f9f4060cffd6'
    rule = AutomationRule.query.filter_by(id=rule_id).first()

    if not rule:
        print("ERROR: Rule not found!")
        sys.exit(1)

    print(f"✓ Rule found: {rule.name}")
    print(f"  Enabled: {rule.enabled}")
    print(f"  Trigger: {json.dumps(rule.trigger, indent=2)}")
    print(f"  Conditions ({len(rule.conditions)} total):")
    for i, cond in enumerate(rule.conditions, 1):
        print(f"    {i}. {json.dumps(cond, indent=6)}")
    print(f"  Actions ({len(rule.actions)} total):")
    for i, action in enumerate(rule.actions, 1):
        print(f"    {i}. {action.get('type', 'unknown')}")

    # Get a recent ticket
    ticket = Ticket.query.filter_by(account_id=rule.account_id).order_by(Ticket.created_at.desc()).first()

    if not ticket:
        print("\nERROR: No tickets found for testing!")
        sys.exit(1)

    print(f"\n✓ Using ticket: {ticket.id}")
    print(f"  Subject: {ticket.subject[:80]}")
    print(f"  Category: {ticket.category}")
    print(f"  Email type: {ticket.email_type}")

    # Build trigger context
    trigger_context = build_context(
        email={"subject": ticket.subject, "body": ticket.body},
        ticket=ticket,
        account_id=rule.account_id,
        extracted={},
        rule_name=rule.name
    )

    print(f"\n✓ Built trigger context with keys: {list(trigger_context.keys())}")

    # Execute workflow
    print(f"\n🚀 Executing automation workflow...")
    try:
        result = execute_automation_workflow(
            workflow_id=str(rule.id),
            trigger_context=trigger_context,
            trigger_event="email.received"
        )
        print(f"\n✅ Workflow execution completed!")
        print(f"   Result: {json.dumps(result, indent=2, default=str)}")
    except Exception as e:
        print(f"\n❌ Workflow execution FAILED!")
        print(f"   Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
