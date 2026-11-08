
locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  }
}

resource "azurerm_resource_group" "this" {
  name     = "rg-${local.name_prefix}"
  location = var.location
  tags     = local.common_tags
}

resource "azurerm_log_analytics_workspace" "this" {
  name                = "law-${local.name_prefix}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.common_tags
}

resource "azurerm_application_insights" "this" {
  name                = "appi-${local.name_prefix}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  application_type    = "web"
  workspace_id        = azurerm_log_analytics_workspace.this.id
  tags                = local.common_tags
}

data "azurerm_container_registry" "shared" {
  name                = var.acr_name
  resource_group_name = var.acr_resource_group_name
}

data "azurerm_client_config" "current" {}

resource "random_string" "kv_suffix" {
  length  = 5
  special = false
  upper   = false
}

resource "azurerm_key_vault" "this" {
  name = substr(
    replace("kv-${local.name_prefix}-${random_string.kv_suffix.result}", "-", ""),
    0,
    24
  )

  location                   = azurerm_resource_group.this.location
  resource_group_name        = azurerm_resource_group.this.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  purge_protection_enabled   = true
  soft_delete_retention_days = 7
  tags                       = local.common_tags
}

# Managed Identity riêng cho môi trường staging
resource "azurerm_user_assigned_identity" "container_app" {
  name                = "uami-${local.name_prefix}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.common_tags
}

# Cho phép Container App pull image từ ACR dùng chung
resource "azurerm_role_assignment" "container_app_acr_pull" {
  scope                = data.azurerm_container_registry.shared.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.container_app.principal_id
}

# Cho phép Container App đọc secrets trong Key Vault staging
resource "azurerm_role_assignment" "container_app_key_vault_secrets_user" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.container_app.principal_id
}

module "container_app" {
  source = "../../modules/container_app"

  name_prefix                    = local.name_prefix
  location                       = azurerm_resource_group.this.location
  resource_group_name            = azurerm_resource_group.this.name
  log_analytics_workspace_id     = azurerm_log_analytics_workspace.this.id
  acr_login_server               = data.azurerm_container_registry.shared.login_server
  container_image                = var.container_image
  container_cpu                  = var.container_cpu
  container_memory               = var.container_memory
  min_replicas                   = var.min_replicas
  max_replicas                   = var.max_replicas
  app_insights_connection_string = azurerm_application_insights.this.connection_string

  identity_id = azurerm_user_assigned_identity.container_app.id

  tags = local.common_tags

  depends_on = [
    azurerm_role_assignment.container_app_acr_pull,
    azurerm_role_assignment.container_app_key_vault_secrets_user,
  ]
}
