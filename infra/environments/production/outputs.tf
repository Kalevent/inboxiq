output "eks_cluster_name" { value = module.eks.cluster_name }
output "eks_cluster_endpoint" { value = module.eks.cluster_endpoint }
output "rds_endpoint" { value = module.rds.endpoint }
output "ecr_repository_url" { value = module.ecr.repository_url }
output "cloudfront_domain" { value = module.s3_cdn.cloudfront_domain }
output "route53_zone_id" { value = module.dns_acm.zone_id }
output "observability_efs_file_system_id" {
  value = module.observability_storage.file_system_id
}
