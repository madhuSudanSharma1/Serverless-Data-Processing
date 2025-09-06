# KMS Key
resource "aws_kms_key" "madhu_kms_key_terraform" {
  description             = var.description
  enable_key_rotation     = var.enable_key_rotation
  deletion_window_in_days = var.deletion_window_in_days
  policy                  = file(var.policy_file_path)
  tags                    = var.tags
}