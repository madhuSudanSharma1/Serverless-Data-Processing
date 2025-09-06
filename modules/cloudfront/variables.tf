variable "cloudfront_aliases" {
  description = "List of aliases for the CloudFront distribution."
  type        = list(string)
}

variable "acm_certificate_arn" {
  description = "The ARN of the ACM certificate for SSL."
  type        = string
}

variable "default_root_object" {
  description = "The default root object for the CloudFront distribution."
  type        = string
  default     = "index.html"
}

variable "viewer_protocol_policy" {
  description = "The viewer protocol policy for the CloudFront distribution."
  type        = string
  default     = "redirect-to-https"
}
variable "tags" {
  description = "A map of tags to assign to the CloudFront distribution."
  type        = map(string)
  default     = {}

}
variable "geo_restriction_type" {
  description = "The type of geo restriction for the CloudFront distribution."
  type        = string
  default     = "none"
}
variable "cloudfront_enabled" {
  description = "Whether the CloudFront distribution is enabled."
  type        = bool
  default     = true
}
variable "is_ipv6_enabled" {
  description = "Whether IPv6 is enabled for the CloudFront distribution."
  type        = bool
  default     = true
}
variable "origin_access_identity_arn" {
  description = "The ARN of the CloudFront origin access identity."
  type        = string
}
variable "bucket_regional_domain_name" {
  description = "The regional domain name of the S3 bucket."
  type        = string
}
variable "origin_id" {
  description = "The ID of the S3 bucket to be used as the origin for the CloudFront distribution."
  type        = string
}
