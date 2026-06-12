#!/usr/bin/env bash
# import.sh — Import existing AWS resources into Terraform state.
# Run from: infra/environments/production/
# Run ONCE after bootstrap.sh + terraform init.
# Safe to re-run — already-imported resources are skipped.
#
# SCOPE: InboxIQ / kalevent.com only (eu-west-2, account 094985084741)
# NOT IN SCOPE: policynumbers.com (App Runner, separate region/account)

set -euo pipefail

tf_import() {
  local addr="$1" id="$2"
  echo -n "  importing ${addr} ... "
  if terraform state show "${addr}" &>/dev/null; then
    echo "already imported, skipping"
  else
    terraform import "${addr}" "${id}" && echo "✅" || echo "❌ (check manually)"
  fi
}

echo "=== Networking ==="
tf_import "module.networking.aws_vpc.main"              "vpc-034a0ee98632a0fdd"
tf_import "module.networking.aws_subnet.public_2a"      "subnet-05518e85e881241aa"
tf_import "module.networking.aws_subnet.public_2c"      "subnet-07662bff45ab526ab"
tf_import "module.networking.aws_subnet.public_2d"      "subnet-07981a625d844dfec"
tf_import "module.networking.aws_subnet.private_2a"     "subnet-0a9af226171376664"
tf_import "module.networking.aws_subnet.private_2c"     "subnet-0f3181b946a27dd5b"
tf_import "module.networking.aws_subnet.private_2d"     "subnet-028136a9c1c9cf1ef"
tf_import "module.networking.aws_db_subnet_group.inboxiq" "inboxiq-subnets"

echo ""
echo "=== IAM (inline policies only — roles are data sources) ==="
tf_import "module.iam.aws_iam_role_policy.node_s3_uploads" \
  "eksctl-inboxiq-eks-nodegroup-inbox-NodeInstanceRole-qJMYbgghTryP:S3-kalevent-uploads"
tf_import "module.iam.aws_iam_role_policy.node_ses" \
  "eksctl-inboxiq-eks-nodegroup-inbox-NodeInstanceRole-qJMYbgghTryP:SES-SendEmail-kalevent"

echo ""
echo "=== EKS ==="
tf_import "module.eks.aws_eks_cluster.inboxiq"    "inboxiq-eks"
tf_import "module.eks.aws_eks_node_group.medium"  "inboxiq-eks:inboxiq-ng-medium"

echo ""
echo "=== RDS ==="
tf_import "module.rds.aws_db_instance.inboxiq"    "inboxiq-db"

echo ""
echo "=== ECR ==="
tf_import "module.ecr.aws_ecr_repository.inboxiq"   "inboxiq"

echo ""
echo "=== S3 + CloudFront ==="
tf_import "module.s3_cdn.aws_s3_bucket.uploads"                       "kalevent-uploads"
tf_import "module.s3_cdn.aws_s3_bucket_public_access_block.uploads"   "kalevent-uploads"
tf_import "module.s3_cdn.aws_s3_bucket_versioning.uploads"            "kalevent-uploads"
tf_import "module.s3_cdn.aws_s3_bucket_server_side_encryption_configuration.uploads" "kalevent-uploads"
tf_import "module.s3_cdn.aws_cloudfront_distribution.uploads"         "E3UNMEO49KB06C"

echo ""
echo "=== DNS / ACM (data sources — no import needed) ==="
echo "  Route53 zone Z0879834J7JV7WW500TQ and ACM certs are data sources — no import required"

echo ""
echo "=== All imports complete. Run: terraform plan ==="
echo "    Expected: 0 changes if everything matched correctly."
echo "    Any 'will be updated' lines need the Terraform resource to match AWS reality."
