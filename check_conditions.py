"""Check automation rule conditions."""
import sys
sys.path.insert(0, '/usr/src')

from src.app import create_app
from src.models import AutomationRule, AutomationRuleExecution
import json

app = create_app()

with app.app_context():
    rule_id = '26ca728b-c4cd-454f-9586-f9f4060cffd6'
    rule = AutomationRule.query.filter_by(id=rule_id).first()

    print(f"✓ Rule: {rule.name}")
    print(f"\nTrigger:")
    print(f"  {json.dumps(rule.trigger, indent=2)}")

    print(f"\nConditions ({len(rule.conditions)} total):")
    for i, cond in enumerate(rule.conditions, 1):
        print(f"\n  Condition {i}:")
        print(f"    Field: {cond.get('field')}")
        print(f"    Operator: {cond.get('operator')}")
        print(f"    Value: {cond.get('value')}")

    print(f"\nCondition Logic: {rule.condition_logic}")

    # Check last execution details
    last_exec = AutomationRuleExecution.query.filter_by(
        rule_id=rule_id
    ).order_by(AutomationRuleExecution.created_at.desc()).first()

    if last_exec and last_exec.conditions_evaluated:
        print(f"\n\nLast Execution Condition Details:")
        for cond_detail in last_exec.conditions_evaluated:
            print(f"\n  Condition {cond_detail.get('index', '?')}:")
            print(f"    Field: {cond_detail.get('field')}")
            print(f"    Operator: {cond_detail.get('operator')}")
            print(f"    Expected: {cond_detail.get('expected')}")
            print(f"    Actual: {cond_detail.get('actual')}")
            print(f"    Matched: {cond_detail.get('matched')}")
