variable "aws_region" {
  description = "The AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "repository" {
  description = "GitHub repo in the form owner/repo"
  type        = string
}

variable "branch" {
  description = "Branch to watch"
  type        = string
  default     = "main"
}

variable "code_connection_name" {
  description = "The name of the CodeStar Connections connection"
  type        = string
}
