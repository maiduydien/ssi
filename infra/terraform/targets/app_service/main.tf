# Alternative hosting target. Use this instead of ACA if the team prefers App Service.
# This target expects an existing resource group and ACR image.
terraform {
  required_version = ">= 1.7.0, < 2.0.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 4.0, < 5.0"
    }
  }
}
provider "azurerm" { features {} }

variable "resource_group_name" { type = string }
variable "location" { type = string }
variable "app_name" { type = string }
variable "acr_login_server" { type = string }
variable "acr_resource_group_name" { type = string }
variable "image_repository" { type = string }
variable "image_tag" { type = string }

resource "azurerm_service_plan" "this" {
  name                = "asp-${var.app_name}"
  resource_group_name = var.resource_group_name
  location            = var.location
  os_type             = "Linux"
  sku_name            = "S1"
}

resource "azurerm_linux_web_app" "this" {
  name                = var.app_name
  resource_group_name = var.resource_group_name
  location            = var.location
  service_plan_id     = azurerm_service_plan.this.id
  https_only          = true

  identity { type = "SystemAssigned" }

  site_config {
    always_on = true
    health_check_path = "/health"
    container_registry_use_managed_identity = true
    application_stack {
      docker_image_name   = "${var.image_repository}:${var.image_tag}"
      docker_registry_url = "https://${var.acr_login_server}"
    }
  }

  app_settings = {
    WEBSITES_PORT                     = "8050"
    DASH_HOST                         = "0.0.0.0"
    DASH_PORT                         = "8050"
    DATA_MODE                         = "auto"
    WEBSITE_SWAP_WARMUP_PING_PATH     = "/health"
    WEBSITE_SWAP_WARMUP_PING_STATUSES = "200"
  }
}

resource "azurerm_role_assignment" "acr_pull" {
  scope                = data.azurerm_container_registry.acr.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_linux_web_app.this.identity[0].principal_id
}

data "azurerm_container_registry" "acr" {
  name                = replace(var.acr_login_server, ".azurecr.io", "")
  resource_group_name = var.acr_resource_group_name
}


resource "azurerm_linux_web_app_slot" "staging" {
  name           = "staging"
  app_service_id = azurerm_linux_web_app.this.id
  https_only     = true

  identity { type = "SystemAssigned" }

  site_config {
    always_on = true
    health_check_path = "/health"
    container_registry_use_managed_identity = true
    application_stack {
      docker_image_name   = "${var.image_repository}:${var.image_tag}"
      docker_registry_url = "https://${var.acr_login_server}"
    }
  }

  app_settings = {
    WEBSITES_PORT                     = "8050"
    DASH_HOST                         = "0.0.0.0"
    DASH_PORT                         = "8050"
    DATA_MODE                         = "auto"
    WEBSITE_SWAP_WARMUP_PING_PATH     = "/health"
    WEBSITE_SWAP_WARMUP_PING_STATUSES = "200"
  }
}

resource "azurerm_role_assignment" "staging_slot_acr_pull" {
  scope                = data.azurerm_container_registry.acr.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_linux_web_app_slot.staging.identity[0].principal_id
}

output "default_hostname" { value = azurerm_linux_web_app.this.default_hostname }
output "staging_slot_hostname" { value = azurerm_linux_web_app_slot.staging.default_hostname }
