variable "region" {
  description = "AWS region for every resource."
  type        = string
  default     = "us-east-2"
}

variable "instance_type" {
  description = "EC2 instance type for the single Docker Compose host."
  type        = string
  default     = "t3a.medium"
}

variable "github_repo" {
  description = "GitHub owner/name whose production environment may assume the deploy role."
  type        = string
  default     = "hollywood-an/concert-radar"

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repo))
    error_message = "github_repo must look like owner/name."
  }
}

variable "create_github_oidc_provider" {
  description = "Create the GitHub Actions OIDC provider. Set false when the account already has one for token.actions.githubusercontent.com (an account can hold only one)."
  type        = bool
  default     = true
}
