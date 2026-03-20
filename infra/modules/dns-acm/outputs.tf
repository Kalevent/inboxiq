output "zone_id"              { value = data.aws_route53_zone.kalevent.zone_id }
output "zone_name"            { value = data.aws_route53_zone.kalevent.name }
output "cert_arn_root"        { value = data.aws_acm_certificate.kalevent_root.arn }
output "cert_arn_api"         { value = data.aws_acm_certificate.kalevent_api.arn }
