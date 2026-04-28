resource "aws_route53_record" "subdomain" {
  zone_id = data.aws_route53_zone.parent.zone_id
  name    = var.subdomain
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.web.domain_name
    zone_id                = aws_cloudfront_distribution.web.hosted_zone_id
    evaluate_target_health = false
  }
}

# Also IPv6 (AAAA) so dual-stack clients use the shorter resolution path.
resource "aws_route53_record" "subdomain_aaaa" {
  zone_id = data.aws_route53_zone.parent.zone_id
  name    = var.subdomain
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.web.domain_name
    zone_id                = aws_cloudfront_distribution.web.hosted_zone_id
    evaluate_target_health = false
  }
}
