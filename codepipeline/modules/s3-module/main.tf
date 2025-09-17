locals {
  bucket_name = var.bucket_name
  tags = merge(var.tags, {
    Name = local.bucket_name
  })
}

resource "aws_s3_bucket" "s3_bucket" {
  bucket = local.bucket_name
  tags   = local.tags
}

resource "aws_s3_bucket_versioning" "s3_bucket_versioning" {
  bucket = aws_s3_bucket.s3_bucket.id
  versioning_configuration {
    status = var.versioning_enabled ? "Enabled" : "Suspended"
  }
}

resource "aws_s3_bucket_public_access_block" "s3_bucket_public_access_block" {
  bucket                  = aws_s3_bucket.s3_bucket.id
  block_public_acls       = var.allow_access_from_anywhere ? false : true
  block_public_policy     = var.allow_access_from_anywhere ? false : true
  ignore_public_acls      = var.allow_access_from_anywhere ? false : true
  restrict_public_buckets = var.allow_access_from_anywhere ? false : true
}

# Make bucket policy conditional - only create if json_policy is provided and not empty
resource "aws_s3_bucket_policy" "bucket_policy" {
  count  = var.json_policy != null && var.json_policy != "" ? 1 : 0
  bucket = aws_s3_bucket.s3_bucket.id
  policy = var.json_policy
}