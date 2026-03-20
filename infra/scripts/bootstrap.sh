#!/usr/bin/env bash
# bootstrap.sh — run once to create Terraform remote state backend.
# Safe to re-run (all commands are idempotent).
set -euo pipefail

REGION="us-west-2"
BUCKET="kalevent-terraform-state"
LOCK_TABLE="terraform-state-lock"

echo "==> Creating S3 state bucket: ${BUCKET}"
aws s3api create-bucket \
  --bucket "${BUCKET}" \
  --region "${REGION}" \
  --create-bucket-configuration LocationConstraint="${REGION}" 2>/dev/null || echo "  (already exists)"

aws s3api put-bucket-versioning \
  --bucket "${BUCKET}" \
  --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption \
  --bucket "${BUCKET}" \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

aws s3api put-public-access-block \
  --bucket "${BUCKET}" \
  --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

echo "==> Creating DynamoDB lock table: ${LOCK_TABLE}"
aws dynamodb create-table \
  --table-name "${LOCK_TABLE}" \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region "${REGION}" 2>/dev/null || echo "  (already exists)"

echo ""
echo "✅ Bootstrap complete. Now run:"
echo "   cd infra/environments/production && terraform init"
