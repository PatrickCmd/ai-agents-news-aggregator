# Use the existing wildcard ACM certificate for patrickcmd.dev
# (covers scraper.patrickcmd.dev via the SAN *.patrickcmd.dev).
# Creating a new cert per service would be wasteful — this one already exists.

data "aws_acm_certificate" "wildcard" {
  domain      = var.domain_name
  statuses    = ["ISSUED"]
  most_recent = true
}
