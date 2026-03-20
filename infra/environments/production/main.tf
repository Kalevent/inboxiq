module "networking" {
  source = "../../modules/networking"
}

module "iam" {
  source = "../../modules/iam"
}

module "eks" {
  source = "../../modules/eks"

  cluster_role_arn          = module.iam.cluster_service_role_arn
  node_role_arn             = module.iam.node_instance_role_arn
  public_subnet_ids         = module.networking.public_subnet_ids
  private_subnet_ids        = module.networking.private_subnet_ids
  cluster_security_group_id = "sg-08279dbe2c9bca819"

  node_desired = 3
  node_min     = 2
  node_max     = 4
}

module "rds" {
  source = "../../modules/rds"

  db_password          = var.db_password
  db_subnet_group_name = module.networking.db_subnet_group_name
  security_group_ids   = ["sg-08279dbe2c9bca819"]
}

module "ecr" {
  source = "../../modules/ecr"
}

module "dns_acm" {
  source = "../../modules/dns-acm"
}

module "s3_cdn" {
  source      = "../../modules/s3-cdn"
  acm_cert_arn = module.dns_acm.cert_arn_root
}
