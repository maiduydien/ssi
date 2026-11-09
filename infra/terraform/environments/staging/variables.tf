variable "location" {
  type        = string
  description = "Azure region for the staging environment."
  default     = "southeastasia"
}

variable "project_name" {
  type    = string
  default = "vn30f1m"
}

variable "environment" {
  type    = string
  default = "staging"
}

variable "container_image" {
  type        = string
  description = "Immutable ACR image tag published by CI."
}

variable "container_cpu" {
  type    = number
  default = 0.5
}

variable "container_memory" {
  type    = string
  default = "1Gi"
}

variable "min_replicas" {
  type    = number
  default = 1
}

variable "max_replicas" {
  type    = number
  default = 3
}

variable "acr_name" {
  type        = string
  description = "Shared ACR."
  default     = "acrvn30f1mshared"
}

variable "acr_resource_group_name" {
  type        = string
  description = "Resource group that owns the shared ACR."
  default     = "rg-vn30f1m-shared"
}