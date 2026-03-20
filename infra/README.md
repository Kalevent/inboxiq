# InboxIQ Infrastructure — Terraform

Manages all AWS resources for **InboxIQ / kalevent.com** (us-west-2).

> ⚠️ This directory is scoped exclusively to InboxIQ.
> policynumbers.com (App Runner, Europe) is a separate AWS account/region — do NOT manage here.

---

## Directory Structure

```
infra/
├── environments/
│   └── production/          ← The live environment. Only one env for now.
│       ├── main.tf           ← Calls all modules
│       ├── variables.tf
│       ├── outputs.tf
│       └── terraform.tfvars
│
├── modules/
│   ├── networking/           ← VPC, subnets, security groups, RDS subnet group
│   ├── eks/                  ← EKS cluster, node group, IRSA roles
│   ├── rds/                  ← PostgreSQL db.t4g.micro (inboxiq-db)
│   ├── s3-cdn/               ← S3 kalevent-uploads + CloudFront (files.kalevent.com)
│   ├── ecr/                  ← ECR repository (094985084741.dkr.ecr.us-west-2...)
│   ├── iam/                  ← Node instance role, cluster role, inline policies
│   └── dns-acm/              ← Route53 kalevent.com zone, ACM certificates
│
└── scripts/
    ├── bootstrap.sh          ← One-time: creates S3 state bucket + DynamoDB lock
    └── import.sh             ← terraform import commands for all existing resources
```

---

## First-Time Setup (new machine / disaster recovery)

```bash
# 1. Bootstrap state backend (only needed once ever, or after account loss)
bash infra/scripts/bootstrap.sh

# 2. Init
cd infra/environments/production
terraform init

# 3. Import existing resources (only needed once per resource)
bash ../../scripts/import.sh

# 4. Plan — should show zero changes if import was clean
terraform plan

# 5. Apply
terraform apply
```

## Day-to-day

```bash
cd infra/environments/production
terraform plan    # review
terraform apply   # apply
```

## Scaling nodes

Edit `infra/modules/eks/main.tf` → `scaling_config.desired_size`, then `terraform apply`.

## Adding a new resource

1. Add to the relevant module under `modules/`
2. Wire it in `environments/production/main.tf`
3. Run `terraform plan` before applying

---

## State

Stored in `s3://kalevent-terraform-state/inboxiq/production/terraform.tfstate` (us-west-2).
Lock table: `terraform-state-lock` (DynamoDB).
Both are created by `scripts/bootstrap.sh`.
