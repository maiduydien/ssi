locals {
  common_tags = {
    project     = var.project_name
    environment = "shared"
    managed_by  = "terraform"
  }
}

resource "azurerm_resource_group" "this" {
  name     = "rg-${var.project_name}-shared"
  location = var.location
  tags     = local.common_tags
}

resource "azurerm_container_registry" "this" {
  name                = replace("acr${var.project_name}shared", "-", "")
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  sku                 = "Basic"
  admin_enabled       = false
  tags                = local.common_tags
}
