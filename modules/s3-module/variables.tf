variable "bucket_name" {
  type        = string
  description = "The name of the S3 bucket"
}
variable "tags" {
  description = "Tags"
  type        = map(string)
  default     = {}
}
variable "versioning_enabled" {
  description = "Enable versioning for the S3 bucket"
  type        = bool
  default     = false
}
variable "allow_access_from_anywhere" {
  description = "Allow access from anywhere"
  type        = bool
  default     = false
}
variable "region" {
  description = "AWS region for the S3 bucket"
  type        = string
  default     = "us-east-1"
}

variable "json_policy" {
  description = "JSON policy for the S3 bucket"
  type        = string
  default     = ""

}