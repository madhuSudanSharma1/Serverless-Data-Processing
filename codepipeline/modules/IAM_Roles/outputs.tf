output "role_arn" {
  description = "ARN of the IAM role"
  value       = aws_iam_role.iam_role.arn
}

output "role_name" {
  description = "Name of the IAM role"
  value       = aws_iam_role.iam_role.name
}