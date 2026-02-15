# Adding name Field to User Model

## Step 1: Update the Model

Edit `src/models.py`:

```python
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255), nullable=True)  # ADD THIS LINE
    password_hash = db.Column(db.String(255), nullable=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
```

## Step 2: Generate Migration

```bash
cd /Users/kofi/inboxiq
flask db migrate -m "Add name field to User model"
```

This will create a migration file in `src/migrations/versions/`

## Step 3: Review and Run Migration

```bash
# Review the generated migration
cat src/migrations/versions/*_add_name_field_to_user_model.py

# Run migration locally
flask db upgrade

# Deploy to production (via CI/CD with "Force run migrations" option)
```

## Step 4: Update Trial Onboarding Code

Once the field exists, update `src/api/v1/admin_trial.py`:

```python
# Change from:
display_name = user.email.split('@')[0] if user.email else "Unknown"

# To:
display_name = user.name if user.name else user.email.split('@')[0]
```

## Step 5: Collect Names on Signup

Update signup/activation flow in `src/auth/` to collect user's full name:
- Add `name` field to registration form
- Store it when creating User record
- For existing users, optionally backfill from trial_onboarding.py's `extract_personalization_variables()`

## Benefits:

1. **Better UX** - Show real names instead of email prefixes
2. **Email Personalization** - Already used in trial emails via `extract_personalization_variables()`
3. **Professional** - `"Jane Doe"` vs `"jane.doe"`
4. **Analytics** - Better user identification in metrics

## Optional: Backfill Existing Users

```python
# Script to backfill names from emails
from src.models import User
from src.extensions import db

users = User.query.filter(User.name.is_(None)).all()
for user in users:
    # Convert email to name: jane.doe@company.com → Jane Doe
    name_part = user.email.split('@')[0]
    formatted_name = ' '.join(word.capitalize() for word in name_part.replace('.', ' ').split())
    user.name = formatted_name

db.session.commit()
print(f"Backfilled {len(users)} user names")
```

---

**Would you like me to:**
1. Add the `name` field to the User model now?
2. Generate the migration?
3. Update the trial onboarding code to use it?
