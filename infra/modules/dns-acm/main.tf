# ── Route53 hosted zone — kalevent.com ──────────────────────
# NOTE: policynumbers.com zone (Z01782894SRNBO6YL2GW) is a SEPARATE app
# using AWS App Runner in a different region. It is NOT managed here.
data "aws_route53_zone" "kalevent" {
  zone_id = "Z0879834J7JV7WW500TQ"
}

# ── ACM certificates ─────────────────────────────────────────
data "aws_acm_certificate" "kalevent_root" {
  domain   = "kalevent.com"
  statuses = ["ISSUED"]
}

data "aws_acm_certificate" "kalevent_api" {
  domain   = "api.kalevent.com"
  statuses = ["ISSUED"]
}
