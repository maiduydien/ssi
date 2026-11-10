
variable "name_prefix" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "log_analytics_workspace_id" {
  type = string
}

variable "acr_login_server" {
  type = string
}

variable "identity_id" {
  type        = string
  description = "Resource ID of the User Assigned Managed Identity."
}

variable "container_image" {
  type = string
}

variable "container_cpu" {
  type = number
}

variable "container_memory" {
  type = string
}

variable "min_replicas" {
  type = number
}

variable "max_replicas" {
  type = number
}

variable "app_insights_connection_string" {
  type      = string
  sensitive = true
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "container_app_environment_id" {
  type        = string
  default     = null
  description = "Existing Container Apps Environment ID."
}

variable "azure_files_storage_name" {
  type        = string
  default     = null
  description = "Registered Azure Files storage name in the Container Apps Environment."
}
