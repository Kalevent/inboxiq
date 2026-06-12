# ── S3 bucket for user uploads ──────────────────────────────
resource "aws_s3_bucket" "uploads" {
  bucket = "kalevent-uploads"
  tags   = { Name = "kalevent-uploads", Purpose = "user-file-uploads" }
}

resource "aws_s3_bucket_public_access_block" "uploads" {
  bucket                  = aws_s3_bucket.uploads.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# ── CloudFront — files.kalevent.com ─────────────────────────
resource "aws_cloudfront_distribution" "uploads" {
  enabled         = true
  aliases         = ["files.kalevent.com"]
  price_class     = "PriceClass_All"   # Matches existing — global reach
  comment         = "Uploads CDN for files.kalevent.com"
  is_ipv6_enabled = true

  # WAF web ACL — protects the distribution; managed outside Terraform
  web_acl_id = var.cloudfront_waf_acl_arn

  origin {
    domain_name              = aws_s3_bucket.uploads.bucket_regional_domain_name
    origin_id                = "kalevent-uploads.s3.eu-west-2.amazonaws.com-mjg3wnlkurm"
    origin_access_control_id = var.existing_oac_id   # Use existing OAC — do not recreate
  }

  default_cache_behavior {
    target_origin_id       = "kalevent-uploads.s3.eu-west-2.amazonaws.com-mjg3wnlkurm"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = "658327ea-f89d-4fab-a63d-7e88639e58f6"   # Managed CachingOptimized

    response_headers_policy_id = aws_cloudfront_response_headers_policy.security.id
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  # CloudFront requires ACM cert in us-east-1 — use the existing one
  viewer_certificate {
    acm_certificate_arn      = var.acm_cert_arn_us_east_1
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = { Name = "files-kalevent" }

  lifecycle {
    # Distribution is live and correctly configured — Terraform is for documentation and disaster recovery.
    # Security headers, WAF, OAC, and origin are all managed outside Terraform.
    ignore_changes = all
  }
}

resource "aws_cloudfront_origin_access_control" "uploads" {
  name                              = "kalevent-uploads-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_response_headers_policy" "security" {
  name = "kalevent-uploads-security-headers"

  security_headers_config {
    content_type_options { override = true }
    frame_options {
      frame_option = "DENY"
      override     = true
    }
    xss_protection {
      mode_block = true
      protection = true
      override   = true
    }
    strict_transport_security {
      access_control_max_age_sec = 31536000
      include_subdomains         = true
      override                   = true
    }
  }

  custom_headers_config {
    items {
      header   = "Content-Disposition"
      value    = "attachment"
      override = false
    }
  }
}
