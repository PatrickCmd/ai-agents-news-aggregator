variable "subdomain" {
  type        = string
  description = "Full subdomain to host (e.g. digest.patrickcmd.dev for prod, dev-digest.patrickcmd.dev for dev)."

  validation {
    condition     = can(regex("\\.patrickcmd\\.dev$", var.subdomain))
    error_message = "subdomain must end in .patrickcmd.dev"
  }
}

variable "github_repo" {
  type        = string
  description = "GitHub repo in 'owner/name' form — gates the OIDC AssumeRole condition."
  default     = "PatrickCmd/ai-agents-news-aggregator"
}

variable "price_class" {
  type    = string
  default = "PriceClass_100"
}
