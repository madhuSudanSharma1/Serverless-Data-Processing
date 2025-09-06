output "event_bus_arn" {
  description = "ARN of the custom event bus"
  value       = var.create_custom_bus ? aws_cloudwatch_event_bus.custom_bus[0].arn : null
}

output "rule_arns" {
  description = "Map of EventBridge rule ARNs"
  value       = { for k, v in aws_cloudwatch_event_rule.rules : k => v.arn }
}