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
