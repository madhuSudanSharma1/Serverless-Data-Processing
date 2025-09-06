variable "tags" {
  description = "A map of tags to assign to the resource."
  type        = map(string)

}
variable "policy_file_path" {
  description = "Path to the KMS key policy file."
  type        = string
}
variable "deletion_window_in_days" {
  description = "The number of days after which the KMS key can be deleted."
  type        = number
  default     = 20

}
variable "enable_key_rotation" {
  description = "Whether to enable key rotation for the KMS key."
  type        = bool
  default     = true
}
variable "description" {
  description = "Description for the KMS key."
  type        = string
  default     = "KMS key for encryption"
}

