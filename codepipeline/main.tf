provider "aws" {
  region = "us-east-1"
}

# Artifact s3 bucket
module "artifacts_bucket" {
  source                     = "./modules/s3-module"
  bucket_name                = "madhu-pipeline-artifacts"
  versioning_enabled         = true
  allow_access_from_anywhere = false
  tags = {
    Project = "terraform-cicd"
    Owner   = "madhu"
  }
}
data "aws_codestarconnections_connection" "madhu_github" {
  name = var.code_connection_name
}

# Codepipeline role
module "codepipeline_role" {
  source = "./modules/IAM_Roles"

  role_name = "madhu-codepipeline-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "codepipeline.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  policy_arns = [
    "arn:aws:iam::aws:policy/AWSCodePipeline_FullAccess",
    "arn:aws:iam::aws:policy/AmazonS3FullAccess"
  ]

  inline_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect   = "Allow",
        Action   = "codestar-connections:UseConnection",
        Resource = data.aws_codestarconnections_connection.madhu_github.arn
      },
      {
        Effect = "Allow",
        Action = [
          "codebuild:StartBuild",
          "codebuild:BatchGetBuilds"
        ],
        Resource = [
          aws_codebuild_project.validate_and_test.arn,
          aws_codebuild_project.deploy.arn
        ]
      }
    ]
  })


  tags = {
    Project = "terraform-cicd"
  }
}

# Codebuild role
module "codebuild_role" {
  source = "./modules/IAM_Roles"

  role_name = "madhu-codebuild-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "codebuild.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  policy_arns = [
    "arn:aws:iam::aws:policy/AmazonS3FullAccess",
    "arn:aws:iam::aws:policy/AmazonSESFullAccess",
    "arn:aws:iam::aws:policy/AWSLambda_FullAccess",
    "arn:aws:iam::aws:policy/CloudWatchFullAccess",
    "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess",
    "arn:aws:iam::aws:policy/AmazonEventBridgeFullAccess",
    "arn:aws:iam::aws:policy/AmazonSNSFullAccess",
    "arn:aws:iam::aws:policy/IAMFullAccess"
  ]
  inline_policy = ""
  tags = {
    Project = "terraform-cicd"
  }
}

# Codebuild Project
resource "aws_codebuild_project" "validate_and_test" {
  name         = "madhu-validate-and-test"
  service_role = module.codebuild_role.role_arn

  artifacts { type = "CODEPIPELINE" }
  environment {
    compute_type    = "BUILD_GENERAL1_SMALL"
    image           = "aws/codebuild/standard:7.0"
    type            = "LINUX_CONTAINER"
    privileged_mode = true
  }
  source {
    type      = "CODEPIPELINE"
    buildspec = "infrastructure/build.yaml"
  }
}

resource "aws_codebuild_project" "deploy" {
  name         = "madhu-terraform-deploy"
  service_role = module.codebuild_role.role_arn

  artifacts { type = "CODEPIPELINE" }
  environment {
    compute_type    = "BUILD_GENERAL1_SMALL"
    image           = "aws/codebuild/standard:7.0"
    type            = "LINUX_CONTAINER"
    privileged_mode = true
  }
  source {
    type      = "CODEPIPELINE"
    buildspec = "infrastructure/deploy.yaml"
  }
}

# Codepipeline
resource "aws_codepipeline" "pipeline" {
  name     = "madhu-terraform-pipeline"
  role_arn = module.codepipeline_role.role_arn

  artifact_store {
    location = module.artifacts_bucket.bucket_id
    type     = "S3"
  }

  stage {
    name = "Source"
    action {
      name             = "SourceAction"
      category         = "Source"
      owner            = "AWS"
      provider         = "CodeStarSourceConnection"
      version          = "1"
      output_artifacts = ["source_output"]
      configuration = {
        ConnectionArn    = data.aws_codestarconnections_connection.madhu_github.arn
        FullRepositoryId = var.repository
        BranchName       = var.branch
      }
    }
  }

  stage {
    name = "ValidateAndTest"
    action {
      name             = "BuildValidateAndTest"
      category         = "Build"
      owner            = "AWS"
      provider         = "CodeBuild"
      input_artifacts  = ["source_output"]
      output_artifacts = ["build_output"]
      version          = "1"
      configuration = {
        ProjectName = aws_codebuild_project.validate_and_test.name
      }
    }
  }

  stage {
    name = "Deploy"
    action {
      name            = "TerraformApply"
      category        = "Build"
      owner           = "AWS"
      provider        = "CodeBuild"
      input_artifacts = ["source_output"]
      version         = "1"
      configuration = {
        ProjectName = aws_codebuild_project.deploy.name
      }
    }
  }
}
