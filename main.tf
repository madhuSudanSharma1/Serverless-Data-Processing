provider "aws" {
  region = var.aws_region
}

# S3
module "my_s3_module" {
  source                     = "./modules/s3-module"
  bucket_name                = "madhu-data-ingestion-bucket"
  tags                       = merge(local.tags, { Name = "madhu-data-ingestion-bucket" })
  versioning_enabled         = true
  allow_access_from_anywhere = false
  region                     = local.region
  # json_policy = jsonencode({
  #   Version = "2012-10-17"
  #   Statement = [
  #     {
  #       Effect = "Allow"
  #       Principal = {
  #         AWS = aws_cloudfront_origin_access_identity.oai.iam_arn
  #       }
  #       Action   = "s3:GetObject"
  #       Resource = "${module.my_s3_module.bucket_arn}/*"
  #     }
  #   ]
  # })
}

# Create IAM role for Lambda execution
module "lambda_execution_role" {
  source = "./modules/IAM_Roles"

  role_name = "lambda-execution-role-madhu"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action = "sts:AssumeRole",
      Effect = "Allow",
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })

  policy_arns = [
    "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
  ]

  tags = local.tags
}

# Lambda function for processing the uploaded data
module "notification_lambda" {
  source          = "./modules/lambda-function"
  function_name   = "madhu-lambda-process-uploaded-data"
  lambda_src_path = "${path.cwd}/functions/process_uploaded_data.py"
  handler         = "lambda_function.lambda_handler"
  runtime         = "python3.13"
  timeout         = 30
  lambda_role_arn = module.lambda_execution_role.role_arn
  
  
  
  tags = merge(local.tags, {
    "Name" = "error-notification-lambda-madhu"
  })
}

