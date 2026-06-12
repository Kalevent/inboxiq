module "networking" {
  source = "../../modules/networking"
}

module "iam" {
  source = "../../modules/iam"
}

module "observability_storage" {
  source = "../../modules/observability-storage"

  vpc_id             = module.networking.vpc_id
  vpc_cidr           = module.networking.vpc_cidr
  private_subnet_ids = module.networking.private_subnet_ids
}

module "eks" {
  source = "../../modules/eks"

  cluster_role_arn   = module.iam.cluster_service_role_arn
  node_role_arn      = module.iam.node_instance_role_arn
  public_subnet_ids  = module.networking.public_subnet_ids
  private_subnet_ids = module.networking.private_subnet_ids

  node_desired = 2
  node_min     = 2
  node_max     = 4
}

data "aws_security_group" "rds" {
  name   = "inboxiq-rds-sg"
  vpc_id = module.networking.vpc_id
}

module "rds" {
  source = "../../modules/rds"

  db_password          = var.db_password
  db_subnet_group_name = module.networking.db_subnet_group_name
  security_group_ids   = [data.aws_security_group.rds.id]
}

module "ecr" {
  source = "../../modules/ecr"
}

module "dns_acm" {
  source = "../../modules/dns-acm"
}

module "s3_cdn" {
  source = "../../modules/s3-cdn"

  # CloudFront requires us-east-1 cert — this is the files.kalevent.com cert
  acm_cert_arn_us_east_1 = "arn:aws:acm:us-east-1:094985084741:certificate/c61e0862-384e-46e4-a2f2-b20c87813e4c"

  # WAF ACL protecting the CloudFront distribution (created by CloudFront automatically)
  cloudfront_waf_acl_arn = "arn:aws:wafv2:us-east-1:094985084741:global/webacl/CreatedByCloudFront-6f79819b/dd86375b-b0e2-46ce-a66a-74afb321cfcc"

  # Existing OAC — do not recreate
  existing_oac_id = "E2DI4G332V6D45"
}
