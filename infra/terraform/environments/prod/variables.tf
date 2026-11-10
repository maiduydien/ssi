
variable "subscription_id" {
  description = "Azure Subscription ID"
  type        = string
}

variable "tenant_id" {
  description = "Microsoft Entra Tenant ID"
  type        = string
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "vn30f1m"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "production"

  validation {
    condition     = var.environment == "production"
    error_message = "This Terraform root is dedicated to production."
  }
}

variable "location" {
  description = "Azure region"
  type        = string
  default     = "southeastasia"
}

variable "container_image" {
  description = "Immutable container image tag"
  type        = string
}

variable "container_cpu" {
  type    = number
  default = 2
}

variable "container_memory" {
  type    = string
  default = "4Gi"
}

variable "min_replicas" {
  type    = number
  default = 1
}

variable "max_replicas" {
  type    = number
  default = 1
}

variable "acr_name" {
  type    = string
  default = "acrvn30f1mshared"
}

variable "acr_resource_group_name" {
  type    = string
  default = "rg-vn30f1m-shared"
}

variable "shared_container_app_environment_name" {
  description = "Name of the existing shared Container Apps Environment"
  type        = string
  default     = "cae-vn30f1m-dev"
}

variable "shared_container_app_environment_resource_group_name" {
  description = "Resource group containing the shared Container Apps Environment"
  type        = string
  default     = "rg-vn30f1m-dev"
}
