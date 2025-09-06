variable "aws_region" {
  description = "The AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "domain_name" {
  description = "The main domain name for the static website"
  type        = string
}

variable "cloudfront_aliases" {
  description = "List of aliases for the CloudFront distribution"
  type        = list(string)
}
variable "subnets" {
  description = "Map of subnet names and IDs"
  type        = map(string)
  default = {
    "group-b-public-subnet-b"  = "subnet-0107e7ec8f1ff8dc6"
    "group-b-private-subnet-b" = "subnet-0cbd8407073cbc0e9"
    "group-b-public-subnet-c"  = "subnet-092775186223b72ed"
    "group-b-private-subnet-c" = "subnet-01543cf34ff013e81"
    "group-b-private-subnet-a" = "subnet-032768b23fa6a4424"
    "group-b-public-subnet-a"  = "subnet-08d47f32b9526825b"
  }
}

variable "backend_1_ecr_image" {
  description = "ECR image URI for Backend 1"
  type        = string
}

variable "backend_2_ecr_image" {
  description = "ECR image URI for Backend 2"
  type        = string
}
variable "db_password" {
  description = "Database password for the application"
  type        = string
  sensitive   = true
}