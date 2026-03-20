output "bucket_name"           { value = aws_s3_bucket.uploads.bucket }
output "cloudfront_domain"     { value = aws_cloudfront_distribution.uploads.domain_name }
output "cloudfront_id"         { value = aws_cloudfront_distribution.uploads.id }
