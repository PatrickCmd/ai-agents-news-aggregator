variable "zip_s3_key" {
  type        = string
  description = "S3 key under the lambda artefacts bucket — set by deploy.py."
}

variable "zip_sha256" {
  type        = string
  description = "Base64-encoded SHA-256 of the zip — set by deploy.py."
}

variable "git_sha" {
  type        = string
  description = "Surfaced via /v1/healthz."
  default     = "unknown"
}

variable "clerk_issuer" {
  type        = string
  description = "Clerk frontend API URL (e.g. https://clerk.example.com)."

  validation {
    condition     = startswith(var.clerk_issuer, "https://")
    error_message = "clerk_issuer must be HTTPS."
  }
}

variable "allowed_origins" {
  type        = list(string)
  description = "CORS allowed origins for both API Gateway and FastAPI middleware."
  default     = ["http://localhost:3000"]
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "memory_size" {
  type    = number
  default = 512
}

variable "timeout" {
  type    = number
  default = 15
}
