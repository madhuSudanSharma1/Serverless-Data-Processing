# Custom Event Bus (optional - can use default)
resource "aws_cloudwatch_event_bus" "custom_bus" {
  count = var.create_custom_bus ? 1 : 0
  name  = var.event_bus_name
  tags  = var.tags
}

# EventBridge Rules
resource "aws_cloudwatch_event_rule" "rules" {
  for_each = var.event_rules

  name           = each.value.name
  description    = each.value.description
  event_bus_name = var.create_custom_bus ? aws_cloudwatch_event_bus.custom_bus[0].name : "default"
  event_pattern  = each.value.event_pattern
  state          = each.value.state

  tags = var.tags
}

# EventBridge Targets
resource "aws_cloudwatch_event_target" "targets" {
  for_each = var.event_targets

  rule           = aws_cloudwatch_event_rule.rules[each.value.rule_name].name
  event_bus_name = var.create_custom_bus ? aws_cloudwatch_event_bus.custom_bus[0].name : "default"
  target_id      = each.value.target_id
  arn            = each.value.target_arn

  dynamic "input_transformer" {
    for_each = each.value.input_transformer != null ? [each.value.input_transformer] : []
    content {
      input_paths    = input_transformer.value.input_paths
      input_template = input_transformer.value.input_template
    }
  }

  depends_on = [aws_cloudwatch_event_rule.rules]
}

# Lambda permissions for EventBridge
resource "aws_lambda_permission" "eventbridge_invoke" {
  for_each = var.lambda_permissions

  statement_id  = each.value.statement_id
  action        = "lambda:InvokeFunction"
  function_name = each.value.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.rules[each.value.rule_name].arn
}