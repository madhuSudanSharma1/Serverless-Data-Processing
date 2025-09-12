variable "aws_region" {
  description = "The AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "from_email" {
  description = "Email address for SES"
  type        = string

}
variable "to_email" {
  description = "Recipient email address for notifications"
  type        = string
}

variable "bedrock_model_id" {
  description = "Amazon Bedrock model ID to use for data analysis"
  type        = string

}
variable "bedrock_max_tokens" {
  description = "Maximum tokens for Amazon Bedrock model response"
  type        = number
  default     = 2000
}
variable "alert_email" {
  description = "Email address for sending alerts"
  type        = string
}