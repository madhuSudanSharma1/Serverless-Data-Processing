variable "bucket_name" {
  description = "Name of the S3 bucket"
  type        = string
}

variable "tags" {
  description = "Tags to apply to the S3 bucket"
  type        = map(string)
  default     = {}
}

variable "versioning_enabled" {
  description = "Enable versioning for the S3 bucket"
  type        = bool
  default     = false
}

variable "allow_access_from_anywhere" {
  description = "Allow public access to the S3 bucket"
  type        = bool
  default     = false
}

variable "json_policy" {
  description = "JSON policy for the S3 bucket (optional)"
  type        = string
  default     = null
}

variable "region" {
  description = "AWS region for the S3 bucket"
  type        = string
  default     = null
}
variable "enable_sse" {
  description = "Enable server-side encryption for the S3 bucket"
  type        = bool
  default     = false
}
variable "enable_lifecycle" {
  description = "Enable lifecycle rules for the S3 bucket"
  type        = bool
  default     = false
}