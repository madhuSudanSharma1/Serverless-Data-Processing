provider "aws" {
  region = var.aws_region
}

# S3 bucket
module "data_processing_s3" {
  source                     = "./modules/s3-module"
  bucket_name                = "madhu-data-processing-bucket"
  tags                       = merge(local.tags, { Name = "madhu-data-processing-bucket" })
  versioning_enabled         = true
  allow_access_from_anywhere = false
  region                     = local.region
}

# DynamoDB for analysis results
module "analysis_dynamodb" {
  source = "./modules/dynamodb"
  
  table_name   = "madhu-analysis-results"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "analysis_id"
  
  attributes = [
    {
      name = "analysis_id"
      type = "S"
    },
    {
      name = "correlation_id"
      type = "S"
    }
  ]
  
  global_secondary_indexes = [
    {
      name            = "correlation-id-index"
      hash_key        = "correlation_id"
      projection_type = "ALL"
    }
  ]
  
  ttl_attribute = "ttl"
  tags          = local.tags
}

# EventBridge for workflow coordination
module "data_processing_eventbridge" {
  source = "./modules/eventbridge"
  
  create_custom_bus = true
  event_bus_name    = "madhu-data-processing-bus"
  
  event_rules = {
    processing_complete = {
      name          = "data-processing-complete"
      description   = "Triggered when data processing is complete"
      event_pattern = jsonencode({
        source      = ["madhu.data-processing"]
        detail-type = ["Processing Complete"]
      })
      state = "ENABLED"
    }
    
    analysis_complete = {
      name          = "data-analysis-complete"
      description   = "Triggered when data analysis is complete"
      event_pattern = jsonencode({
        source      = ["madhu.data-processing"]
        detail-type = ["Analysis Complete"]
      })
      state = "ENABLED"
    }
  }
  
  event_targets = {
    trigger_analyzer = {
      rule_name  = "processing_complete"
      target_id  = "trigger-data-analyzer"
      target_arn = module.data_analyzer_lambda.lambda_function_arn
    }
    
    trigger_notifier = {
      rule_name  = "analysis_complete"
      target_id  = "trigger-notifier"
      target_arn = module.notifier_lambda.lambda_function_arn
    }
  }
  
  lambda_permissions = {
    analyzer_permission = {
      statement_id  = "AllowEventBridgeInvokeAnalyzer"
      function_name = module.data_analyzer_lambda.lambda_function_name
      rule_name     = "processing_complete"
    }
    
    notifier_permission = {
      statement_id  = "AllowEventBridgeInvokeNotifier"
      function_name = module.notifier_lambda.lambda_function_name
      rule_name     = "analysis_complete"
    }
  }
  
  tags = local.tags
}

# Enhanced IAM role for Lambda execution 
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

  inline_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          "${module.data_processing_s3.bucket_arn}",
          "${module.data_processing_s3.bucket_arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          module.analysis_dynamodb.table_arn,
          "${module.analysis_dynamodb.table_arn}/index/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = "arn:aws:bedrock:${local.region}::foundation-model/anthropic.claude-3-sonnet-20240229-v1:0"
      },
      {
        Effect = "Allow"
        Action = [
          "events:PutEvents"
        ]
        Resource = module.data_processing_eventbridge.event_bus_arn != null ? module.data_processing_eventbridge.event_bus_arn : "arn:aws:events:${local.region}:*:event-bus/default"
      }
    ]
  })

  tags = local.tags
}

# Data processing Lambda function
module "data_processor_lambda" {
  source          = "./modules/lambda-function"
  function_name   = "madhu-data-processor"
  lambda_src_path = "${path.cwd}/functions"
  handler         = "data_processor.lambda_handler"
  runtime         = "python3.11"
  timeout         = 300
  lambda_role_arn = module.lambda_execution_role.role_arn
  
  environment_variables = {
    BUCKET_NAME     = module.data_processing_s3.bucket_name
    REGION          = local.region
    EVENT_BUS_NAME  = "madhu-data-processing-bus"
  }
  
  tags = merge(local.tags, {
    "Name" = "data-processor-lambda-madhu"
  })
}

# Data analyzer Lambda function
module "data_analyzer_lambda" {
  source          = "./modules/lambda-function"
  function_name   = "madhu-data-analyzer"
  lambda_src_path = "${path.cwd}/functions"
  handler         = "data_analyzer.lambda_handler"
  runtime         = "python3.11"
  timeout         = 900  # 15 minutes for Bedrock calls
  lambda_role_arn = module.lambda_execution_role.role_arn
  
  environment_variables = {
    BUCKET_NAME     = module.data_processing_s3.bucket_name
    DYNAMODB_TABLE  = module.analysis_dynamodb.table_name
    REGION          = local.region
    EVENT_BUS_NAME  = "madhu-data-processing-bus"
  }
  
  tags = merge(local.tags, {
    "Name" = "data-analyzer-lambda-madhu"
  })
}

# Placeholder for notifier lambda (we'll create this next)
module "notifier_lambda" {
  source          = "./modules/lambda-function"
  function_name   = "madhu-notifier"
  lambda_src_path = "${path.cwd}/functions"
  handler         = "notifier.lambda_handler"
  runtime         = "python3.11"
  timeout         = 300
  lambda_role_arn = module.lambda_execution_role.role_arn
  
  environment_variables = {
    DYNAMODB_TABLE = module.analysis_dynamodb.table_name
    REGION         = local.region
  }
  
  tags = merge(local.tags, {
    "Name" = "notifier-lambda-madhu"
  })
}

# Lambda permission for S3 to invoke the function
resource "aws_lambda_permission" "allow_s3_invoke" {
  statement_id  = "AllowExecutionFromS3Bucket"
  action        = "lambda:InvokeFunction"
  function_name = module.data_processor_lambda.lambda_function_name
  principal     = "s3.amazonaws.com"
  source_arn    = module.data_processing_s3.bucket_arn
}

# S3 bucket notification to trigger Lambda when files are uploaded to input/ folder
resource "aws_s3_bucket_notification" "data_processing_notification" {
  bucket = module.data_processing_s3.bucket_name

  lambda_function {
    lambda_function_arn = module.data_processor_lambda.lambda_function_arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "input/"
    filter_suffix       = ".csv"
  }

  depends_on = [aws_lambda_permission.allow_s3_invoke]
}


