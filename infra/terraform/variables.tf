variable "region" {
  description = "AWS region for every resource."
  type        = string
  default     = "us-east-2"
}

variable "instance_type" {
  description = "EC2 instance type for the single Docker Compose host. The default is one of the few types an AWS Free plan account can launch; on a Paid plan, t3a.medium (same 2 vCPU / 4 GB) costs less than half as much."
  type        = string
  default     = "c7i-flex.large"
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

variable "budget_email" {
  description = "Email for the 40 USD/month budget alert. Empty creates no budget."
  type        = string
  default     = ""

  validation {
    condition     = var.budget_email == "" || can(regex("^[^@[:space:]]+@[^@[:space:]]+$", var.budget_email))
    error_message = "budget_email must be empty or an email address."
  }
}
