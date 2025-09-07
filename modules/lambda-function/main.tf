provider "aws" {
  region = var.region
}

# Zip the Lambda source code folder
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = var.lambda_src_path
  output_path = "${var.lambda_src_path}/../${var.function_name}.zip"
}

# Lambda function resource
resource "aws_lambda_function" "lambda_function" {
  function_name = var.function_name
  handler       = var.handler
  runtime       = var.runtime
  role          = var.lambda_role_arn
  filename      = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout       = var.timeout
  
  environment {
    variables = var.environment_variables
  }
  
  tags = merge(var.tags, {
    "Name" = var.function_name
  })
}
