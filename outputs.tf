output "s3_bucket_name" {
  value = module.my_s3_module.bucket_name
}

output "s3_bucket_arn" {
  value = module.my_s3_module.bucket_arn
}

output "cloudfront_distribution_url" {
  value = module.cloudfront.cloudfront_distribution_domain_name
}
