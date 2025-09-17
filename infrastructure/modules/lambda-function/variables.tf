variable "function_name" {
  description = "Name of the Lambda function"
  type        = string
}

variable "lambda_src_path" {
  description = "Path to the folder containing Lambda function code"
  type        = string
}

variable "handler" {
  description = "Handler for the Lambda function (e.g., lambda_function.lambda_handler)"
  type        = string
}

variable "runtime" {
  description = "Lambda runtime (e.g., python3.11)"
  type        = string
  default     = "python3.11"
}

variable "timeout" {
  description = "Timeout in seconds"
  type        = number
  default     = 10
}

variable "region" {
  description = "AWS Region"
  type        = string
  default     = "us-east-1"
}

variable "lambda_role_arn" {
  description = "ARN of the IAM role for Lambda execution"
  type        = string
}

variable "tags" {
  description = "Tags to apply to the Lambda function"
  type        = map(string)
  default     = {}
}

variable "environment_variables" {
  description = "Environment variables for the Lambda function"
  type        = map(string)
  default     = {}
}