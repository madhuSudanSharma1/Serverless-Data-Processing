variable "create_custom_bus" {
  description = "Whether to create a custom event bus"
  type        = bool
  default     = false
}

variable "event_bus_name" {
  description = "Name of the custom event bus"
  type        = string
  default     = "data-processing-bus"
}

variable "event_rules" {
  description = "Map of EventBridge rules"
  type = map(object({
    name          = string
    description   = string
    event_pattern = string
    state         = string
  }))
  default = {}
}

variable "event_targets" {
  description = "Map of EventBridge targets"
  type = map(object({
    rule_name    = string
    target_id    = string
    target_arn   = string
    input_transformer = optional(object({
      input_paths    = map(string)
      input_template = string
    }))
  }))
  default = {}
}

variable "lambda_permissions" {
  description = "Map of Lambda permissions for EventBridge"
  type = map(object({
    statement_id  = string
    function_name = string
    rule_name     = string
  }))
  default = {}
}

variable "tags" {
  description = "Tags to apply to EventBridge resources"
  type        = map(string)
  default     = {}
}