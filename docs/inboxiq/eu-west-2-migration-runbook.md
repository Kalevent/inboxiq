# InboxIQ EKS Migration Runbook — us-west-2 → eu-west-2

**Date:** 2026-06-12
**Status:** Ready to execute — all code changes merged, awaiting night window
**Branch:** `infra/eu-west-2-migration`
**Estimated execution time:** 3–4 hours (excluding RDS restore wait ~30 min)

---

## Terraform role in this migration

**Important:** This is NOT a `terraform destroy + terraform apply` migration.
The Terraform files document **target state**. The actual infrastructure is
provisioned manually with `eksctl` + AWS CLI, then imported into Terraform state.
Do not run `terraform apply` until Step 9.

---

## Placeholders to fill in during execution

Two values are unknown until AWS provisioning runs. Search for these strings
in the codebase and replace before the final deploy:

| Placeholder | Where | Filled in at |
|---|---|---|
| `REPLACE_AFTER_KMS_PROVISION` | `infra/modules/rds/main.tf` | Step 1 |
| `REPLACE_AFTER_ACM_PROVISION` | `src/k8s/inboxiq-ingress.yaml`, `src/k8s/grafana-ingress.yaml` | Step 2 |

---

## Pre-flight checks (run before starting)

```bash
# Confirm you're on the right branch
git status

# Confirm live us-west-2 cluster is healthy before touching anything
kubectl get nodes -n kaley
kubectl get pods -n kaley

# Set your terminal to us-west-2 for pre-migration steps
export AWS_REGION=us-west-2
aws eks update-kubeconfig --name inboxiq-eks --region us-west-2
```

---

## Step 1 — Provision KMS key in eu-west-2

```bash
KMS_KEY=$(aws kms create-key \
  --description "InboxIQ RDS encryption key (eu-west-2)" \
  --region eu-west-2 \
  --query 'KeyMetadata.KeyId' \
  --output text)

aws kms create-alias \
  --alias-name alias/inboxiq-rds \
  --target-key-id "$KMS_KEY" \
  --region eu-west-2

echo "KMS Key ARN: arn:aws:kms:eu-west-2:094985084741:key/$KMS_KEY"
```

**After this step** — fill in the placeholder:
```bash
# In infra/modules/rds/main.tf, replace:
#   arn:aws:kms:eu-west-2:094985084741:key/REPLACE_AFTER_KMS_PROVISION
# with:
#   arn:aws:kms:eu-west-2:094985084741:key/<KMS_KEY value above>
```

---

## Step 2 — Request ACM certificate in eu-west-2

```bash
CERT_ARN=$(aws acm request-certificate \
  --domain-name "kalevent.com" \
  --subject-alternative-names "*.kalevent.com" \
  --validation-method DNS \
  --region eu-west-2 \
  --query 'CertificateArn' \
  --output text)

echo "Certificate ARN: $CERT_ARN"

# Get DNS validation record
aws acm describe-certificate \
  --certificate-arn "$CERT_ARN" \
  --region eu-west-2 \
  --query 'Certificate.DomainValidationOptions'
```

Add the DNS CNAME record shown above to Route 53 / GoDaddy.
Wait for validation (usually 2–5 minutes):

```bash
aws acm wait certificate-validated \
  --certificate-arn "$CERT_ARN" \
  --region eu-west-2
echo "Certificate validated"
```

**After this step** — fill in both ingress placeholders:
```bash
# In src/k8s/inboxiq-ingress.yaml and src/k8s/grafana-ingress.yaml, replace:
#   arn:aws:acm:eu-west-2:094985084741:certificate/REPLACE_AFTER_ACM_PROVISION
# with:
#   $CERT_ARN
```

---

## Step 3 — Create ECR repository in eu-west-2

```bash
aws ecr create-repository \
  --repository-name inboxiq \
  --region eu-west-2 \
  --image-scanning-configuration scanOnPush=true

# Push the current production image to eu-west-2 ECR
CURRENT_TAG=$(kubectl get deployment inboxiq -n kaley \
  -o jsonpath='{.spec.template.spec.containers[0].image}' | cut -d: -f2)

# Pull from us-west-2, push to eu-west-2
aws ecr get-login-password --region us-west-2 | \
  docker pull 094985084741.dkr.ecr.us-west-2.amazonaws.com/inboxiq:$CURRENT_TAG

aws ecr get-login-password --region eu-west-2 | \
  docker tag 094985084741.dkr.ecr.us-west-2.amazonaws.com/inboxiq:$CURRENT_TAG \
             094985084741.dkr.ecr.eu-west-2.amazonaws.com/inboxiq:$CURRENT_TAG

docker push 094985084741.dkr.ecr.eu-west-2.amazonaws.com/inboxiq:$CURRENT_TAG
```

---

## Step 4 — RDS: snapshot → cross-region copy → restore in eu-west-2

```bash
# Take a final snapshot of the live RDS (while us-west-2 is still live)
aws rds create-db-snapshot \
  --db-instance-identifier inboxiq-db-encrypted \
  --db-snapshot-identifier inboxiq-eu-migration-$(date +%Y%m%d) \
  --region us-west-2

# Wait for snapshot to complete (~5 min)
aws rds wait db-snapshot-completed \
  --db-snapshot-identifier inboxiq-eu-migration-$(date +%Y%m%d) \
  --region us-west-2
echo "Snapshot ready"

# Copy snapshot cross-region with eu-west-2 KMS key
SNAPSHOT_ID="inboxiq-eu-migration-$(date +%Y%m%d)"
SOURCE_ARN="arn:aws:rds:us-west-2:094985084741:snapshot:$SNAPSHOT_ID"

aws rds copy-db-snapshot \
  --source-db-snapshot-identifier "$SOURCE_ARN" \
  --target-db-snapshot-identifier "inboxiq-eu-migration-copy" \
  --kms-key-id "arn:aws:kms:eu-west-2:094985084741:key/REPLACE_AFTER_KMS_PROVISION" \
  --region eu-west-2

# Wait for copy (~10-15 min)
aws rds wait db-snapshot-completed \
  --db-snapshot-identifier inboxiq-eu-migration-copy \
  --region eu-west-2
echo "Cross-region copy ready"

# Get eu-west-2 subnet group and security group first (created by eksctl in Step 5)
# Then restore:
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier inboxiq-db-encrypted \
  --db-snapshot-identifier inboxiq-eu-migration-copy \
  --db-instance-class db.t4g.micro \
  --db-subnet-group-name inboxiq-subnets \
  --vpc-security-group-ids <eu-west-2-rds-sg-id> \
  --no-publicly-accessible \
  --deletion-protection \
  --region eu-west-2

aws rds wait db-instance-available \
  --db-instance-identifier inboxiq-db-encrypted \
  --region eu-west-2
echo "RDS ready in eu-west-2"

# Get the new endpoint
aws rds describe-db-instances \
  --db-instance-identifier inboxiq-db-encrypted \
  --region eu-west-2 \
  --query 'DBInstances[0].Endpoint.Address'
```

**Note:** The restored RDS instance has the full production database — no data loss.
Update the `DATABASE_URL` K8s secret with the new endpoint before deploying.

---

## Step 5 — Create eu-west-2 EKS cluster

```bash
# Use eksctl — same pattern as the existing us-west-2 cluster
eksctl create cluster \
  --name inboxiq-eks \
  --region eu-west-2 \
  --version 1.32 \
  --nodegroup-name standard-workers \
  --node-type t3.medium \
  --nodes 2 \
  --nodes-min 2 \
  --nodes-max 4 \
  --managed \
  --with-oidc \
  --asg-access \
  --full-ecr-access \
  --alb-ingress-access

# ~15 minutes. After completion:
aws eks update-kubeconfig --name inboxiq-eks --region eu-west-2
kubectl get nodes
```

Install ALB Ingress Controller and EBS CSI driver (same as existing cluster):

```bash
# ALB Ingress Controller
eksctl create iamserviceaccount \
  --cluster inboxiq-eks \
  --namespace kube-system \
  --name aws-load-balancer-controller \
  --attach-policy-arn arn:aws:iam::094985084741:policy/AWSLoadBalancerControllerIAMPolicy \
  --override-existing-serviceaccounts \
  --region eu-west-2 \
  --approve

helm upgrade --install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=inboxiq-eks \
  --set serviceAccount.create=false \
  --set serviceAccount.name=aws-load-balancer-controller

# EBS CSI driver (K8s 1.32 — in-tree provisioner removed)
eksctl create iamserviceaccount \
  --cluster inboxiq-eks \
  --namespace kube-system \
  --name ebs-csi-controller-sa \
  --attach-policy-arn arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy \
  --override-existing-serviceaccounts \
  --region eu-west-2 \
  --approve

aws eks create-addon \
  --cluster-name inboxiq-eks \
  --addon-name aws-ebs-csi-driver \
  --region eu-west-2
```

---

## Step 6 — Deploy and smoke test on staging hostname

```bash
# Create kaley namespace and copy all secrets from us-west-2
kubectl create namespace kaley

# Copy secrets (adjust DATABASE_URL to new eu-west-2 RDS endpoint)
kubectl get secret inboxiq-secrets -n kaley --context=us-west-2 -o yaml | \
  sed 's/namespace: kaley/namespace: kaley/' | \
  kubectl apply -f - --context=eu-west-2

# Update DATABASE_URL with new eu-west-2 RDS endpoint
kubectl edit secret inboxiq-secrets -n kaley

# Deploy app (uses the updated k8s manifests with eu-west-2 ECR)
kubectl apply -f src/k8s/ -n kaley

# Smoke test via port-forward (before DNS cutover)
kubectl port-forward svc/inboxiq 8080:80 -n kaley
curl http://localhost:8080/health
```

---

## Step 7 — DNS cutover (point-of-no-return)

```bash
# Get new eu-west-2 ALB DNS name
NEW_ALB=$(kubectl get ingress inboxiq -n kaley \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
echo "New ALB: $NEW_ALB"
```

Update DNS records (Route 53 or GoDaddy) to point `kalevent.com` → new ALB.
Set TTL to 60 seconds before cutover for fast rollback.

```bash
# After DNS change propagates, verify:
curl -I https://kalevent.com/health
```

---

## Step 8 — Monitor and verify (24h window)

```bash
# Watch pod health
kubectl get pods -n kaley -w

# Check logs for errors
kubectl logs -n kaley deploy/inboxiq --since=1h | grep -i error

# Verify Celery workers are processing
kubectl exec -n kaley deploy/inboxiq -- python -c \
  "from src.celery_inboxiq import celery; print(list(celery.tasks.keys())[:5])"
```

---

## Step 9 — Update GitHub Secrets

In GitHub → Settings → Secrets and variables → Actions:

| Secret | Old value | New value |
|---|---|---|
| `AWS_REGION` | `us-west-2` | `eu-west-2` |
| `ECR_REGISTRY` | `094985084741.dkr.ecr.us-west-2.amazonaws.com` | `094985084741.dkr.ecr.eu-west-2.amazonaws.com` |
| `EKS_CLUSTER` | `inboxiq-eks` | `inboxiq-eks` (unchanged) |

Trigger a test build to confirm CI/CD deploys to eu-west-2 correctly.

---

## Step 10 — Terraform import (sync state with new infra)

```bash
cd infra/environments/production

# Re-init backend (now pointing to eu-west-2 backend)
terraform init -reconfigure

# Import new resources
terraform import module.networking.aws_vpc.main <vpc-id>
terraform import module.rds.aws_db_instance.inboxiq inboxiq-db-encrypted
# ... (run infra/scripts/import.sh for full list)

terraform plan  # Should show no changes if import was clean
```

---

## Step 11 — Decommission us-west-2 (after 24h monitoring)

```bash
# Scale down us-west-2 cluster first (don't delete yet)
eksctl scale nodegroup --cluster inboxiq-eks --name standard-workers \
  --nodes 0 --region us-west-2

# After 48h with no issues:
eksctl delete cluster --name inboxiq-eks --region us-west-2

# Delete us-west-2 RDS (already have eu-west-2 copy)
aws rds delete-db-instance \
  --db-instance-identifier inboxiq-db-encrypted \
  --skip-final-snapshot \
  --region us-west-2
```

---

## Rollback plan

If anything goes wrong before DNS cutover (Steps 1–6): us-west-2 is untouched.
Just abandon the eu-west-2 provisioning.

If issues arise after DNS cutover (Step 7):

```bash
# Point DNS back to us-west-2 ALB (you noted this before cutting over)
# TTL=60s so propagation is fast

# us-west-2 cluster and RDS are still running — just repoint DNS
```

The us-west-2 cluster stays live and unmodified until Step 11.

---

## S3 uploads bucket migration

The `kalevent-uploads` bucket is in us-west-2. After the cluster migration:

```bash
# Create new bucket in eu-west-2 with same config
aws s3api create-bucket \
  --bucket kalevent-uploads-eu \
  --region eu-west-2 \
  --create-bucket-configuration LocationConstraint=eu-west-2

# Sync existing uploads
aws s3 sync s3://kalevent-uploads s3://kalevent-uploads-eu --region eu-west-2

# Update CloudFront origin to new bucket, then rename bucket
# (or update UPLOADS_BUCKET env var in K8s secrets)
```

**Note:** S3 buckets can't be renamed or moved between regions. Options:
1. Sync to new bucket + update `UPLOADS_BUCKET` secret + update CloudFront origin
2. Use S3 Cross-Region Replication during transition

For zero-downtime: enable replication first, then cut CloudFront origin over.

---

## SES setup in eu-west-2

```bash
# Verify your sending domain in eu-west-2 SES
aws sesv2 create-email-identity \
  --email-identity kalevent.com \
  --region eu-west-2

# Request production access (if sandbox)
aws sesv2 put-account-details \
  --production-access-enabled \
  --mail-type TRANSACTIONAL \
  --website-url https://kalevent.com \
  --region eu-west-2
```

The Prometheus alertmanager SMTP endpoint is already updated in
`src/k8s/prometheus-values.yaml` to `email-smtp.eu-west-2.amazonaws.com`.
SES SMTP credentials (username/password) are region-specific — generate new
SMTP credentials in eu-west-2 IAM and update the K8s secret.

---

*Last updated: 2026-06-12*
