"""Configure account-specific triage labels for account_id=2."""
import sys
sys.path.insert(0, '/usr/src')

from src.app import create_app
from src.triage_labels import save_triage_labels

app = create_app()

with app.app_context():
    # Configure account 2 to only use "billing" email type
    labels = {
        "priorities": ["P1", "P2", "P3"],
        "categories": ["billing", "support", "sales"],
        "sentiments": ["positive", "neutral", "negative", "urgent"],
        "intents": ["question", "request", "complaint", "feedback"],
        "email_types": ["billing"],  # ONLY billing!
        "teams": ["billing", "support"],
        "action_required_options": ["true", "false", "optional"]
    }

    result = save_triage_labels(account_id=2, labels=labels, name="default")
    print(f"✅ Configured account 2 with custom labels")
    print(f"   Email types: {labels['email_types']}")
    print(f"   Result: {result}")
