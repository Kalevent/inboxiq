variable "acm_cert_arn_us_east_1" {
  description = "ACM cert ARN in us-east-1 — CloudFront only accepts us-east-1 certs"
  type        = string
}

variable "cloudfront_waf_acl_arn" {
  description = "WAF Web ACL ARN (us-east-1) protecting the CloudFront distribution"
  type        = string
}

variable "existing_oac_id" {
  description = "Existing CloudFront Origin Access Control ID — do not recreate"
  type        = string
}
