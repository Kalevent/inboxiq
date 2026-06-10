"""
Data migration: InboxConnection webhook providers → WebhookProvider

Run this script to migrate existing webhook providers from the InboxConnection
table to the new WebhookProvider table for Automation Studio.

Usage:
    python -m src.migrations.scripts.migrate_webhook_providers
"""

import json
from uuid import uuid4

from src.extensions import db
from src.models.automation import WebhookProvider
from src.models.core import InboxConnection
from src.crypto import encrypt_value


WEBHOOK_PROVIDERS = ['sage', 'quickbooks', 'slack', 'custom', 'stripe', 'square', 'paypal']


def migrate_webhook_providers(dry_run=True):
    """
    Migrate webhook providers from InboxConnection to WebhookProvider.

    Args:
        dry_run: If True, print changes without committing. If False, commit to database.
    """
    print(f"Starting webhook provider migration (dry_run={dry_run})...")

    # Find all InboxConnection records that are webhook providers
    webhook_connections = InboxConnection.query.filter(
        InboxConnection.provider.in_(WEBHOOK_PROVIDERS)
    ).all()

    print(f"Found {len(webhook_connections)} webhook providers to migrate")

    migrated_count = 0
    skipped_count = 0

    for conn in webhook_connections:
        print(f"\n--- Migrating: {conn.provider} (ID: {conn.id}) ---")
        print(f"    Account ID: {conn.account_id}")
        print(f"    Status: {conn.status}")

        # Check if already migrated
        existing = WebhookProvider.query.filter_by(
            account_id=conn.account_id,
            provider_type=conn.provider
        ).first()

        if existing:
            print(f"    ⚠️  SKIPPED: WebhookProvider already exists for {conn.provider}")
            skipped_count += 1
            continue

        # Extract metadata
        metadata = conn.metadata_json or {}
        configuration_name = metadata.get('label', f"{conn.provider.title()} Integration")

        # Build credentials JSON from metadata
        credentials = {}

        # Extract encrypted fields (they have _enc suffix in metadata)
        encrypted_fields = {
            'api_key_enc': 'api_key',
            'client_secret_enc': 'client_secret',
            'auth_token_enc': 'auth_token',
            'webhook_url_enc': 'webhook_url',
            'auth_header_enc': 'authorization_header',
            'webhook_secret_enc': 'webhook_signing_secret',
            'webhook_signature_key_enc': 'webhook_signature_key',
            'access_token_enc': 'access_token',
        }

        # Copy encrypted fields (they're already encrypted, keep them encrypted in credentials)
        for old_key, new_key in encrypted_fields.items():
            if old_key in metadata:
                # These are already encrypted values, we'll decrypt and re-encrypt them
                # into a single credentials blob
                credentials[new_key] = metadata[old_key]  # Store encrypted value temporarily

        # Copy non-encrypted fields
        non_encrypted_fields = [
            'company_id', 'endpoint_url', 'client_id', 'realm_id',
            'channel', 'environment', 'webhook_id', 'destination_provider'
        ]

        for field in non_encrypted_fields:
            if field in metadata:
                credentials[field] = metadata[field]

        # For encrypted fields that are stored with _enc suffix, we need to extract them
        # Since they're already encrypted individually, we need to decrypt them first,
        # then re-encrypt as a JSON blob

        # Actually, let's keep it simple: store the metadata as-is in credentials_encrypted
        # The webhook_actions.py can decrypt the whole blob and access individual fields

        # Encrypt the entire credentials object
        credentials_json = json.dumps(metadata)  # Keep original structure for compatibility
        credentials_encrypted = encrypt_value(credentials_json)

        print(f"    Configuration Name: {configuration_name}")
        print(f"    Credentials keys: {list(metadata.keys())}")

        # Create WebhookProvider record
        webhook_provider = WebhookProvider(
            id=str(uuid4()),
            account_id=conn.account_id,
            provider_type=conn.provider,
            configuration_name=configuration_name,
            environment=metadata.get('environment', 'production'),
            credentials_encrypted=credentials_encrypted,
            enabled=(conn.status == 'connected'),
            created_at=conn.created_at,
            updated_at=conn.updated_at,
        )

        # Handle webhook signing secrets for source providers
        if 'webhook_secret_enc' in metadata:
            webhook_provider.webhook_signing_secret_encrypted = metadata['webhook_secret_enc']

        if 'webhook_signature_key_enc' in metadata:
            webhook_provider.webhook_signing_secret_encrypted = metadata['webhook_signature_key_enc']

        # Handle API keys
        if 'api_key_enc' in metadata:
            webhook_provider.api_key_encrypted = metadata['api_key_enc']

        if 'access_token_enc' in metadata:
            webhook_provider.api_key_encrypted = metadata['access_token_enc']

        if not dry_run:
            db.session.add(webhook_provider)
            print("    ✅ MIGRATED: Created WebhookProvider record")
        else:
            print("    [DRY RUN] Would create WebhookProvider record")

        migrated_count += 1

    if not dry_run:
        db.session.commit()
        print("\n✅ Migration complete!")
    else:
        print("\n[DRY RUN] No changes committed")

    print("\nSummary:")
    print(f"  - Migrated: {migrated_count}")
    print(f"  - Skipped: {skipped_count}")
    print(f"  - Total: {len(webhook_connections)}")

    if dry_run:
        print("\nRun with dry_run=False to apply changes")


def rollback_migration():
    """
    Rollback: Delete all WebhookProvider records (InboxConnection remains unchanged).

    WARNING: This will delete all WebhookProvider records!
    """
    print("⚠️  WARNING: This will delete ALL WebhookProvider records!")
    confirmation = input("Type 'DELETE ALL' to confirm: ")

    if confirmation != "DELETE ALL":
        print("Cancelled.")
        return

    count = WebhookProvider.query.delete()
    db.session.commit()

    print(f"✅ Deleted {count} WebhookProvider records")


if __name__ == "__main__":
    import sys

    # Parse command line args
    dry_run = True
    if len(sys.argv) > 1:
        if sys.argv[1] == "--apply":
            dry_run = False
        elif sys.argv[1] == "--rollback":
            rollback_migration()
            sys.exit(0)

    # Initialize Flask app context
    from src.app import create_app
    app = create_app()

    with app.app_context():
        migrate_webhook_providers(dry_run=dry_run)
