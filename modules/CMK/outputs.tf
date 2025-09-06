output "kms_key_id" {
  description = "The ID of the KMS key"
  value       = aws_kms_key.madhu_kms_key_terraform.id

}
output "kms_key_arn" {
  description = "The ARN of the KMS key"
  value       = aws_kms_key.madhu_kms_key_terraform.arn
}