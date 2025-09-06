variable "tags" {
  description = "A map of tags to assign to the resource."
  type        = map(string)

}
variable "security_group_name" {
  description = "Name of the security group"
  type        = string
  default     = "madhu-security-group"

}
variable "security_group_description" {
  description = "Description of the security group"
  type        = string
  default     = "Security group for RDS instances"

}
variable "vpc_id" {
  description = "VPC ID where the security group will be created"
  type        = string
}
variable "ingress_rules" {
  description = "List of ingress rules for the security group"
  type = list(object({
    description     = optional(string)
    protocol        = string
    from_port       = number
    to_port         = number
    cidr_blocks     = optional(list(string))
    security_groups = optional(list(string))
  }))
}

variable "egress_rules" {
  description = "List of egress rules for the security group"
  type = list(object({
    description     = optional(string)
    protocol        = string
    from_port       = number
    to_port         = number
    cidr_blocks     = optional(list(string))
    security_groups = optional(list(string))
  }))
}