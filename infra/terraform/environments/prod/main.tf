
locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  }
}

# ------------------------------------------------------------
# Production Resource Group
# ------------------------------------------------------------

resource "azurerm_resource_group" "this" {
  name     = "rg-${local.name_prefix}"
  location = var.location
  tags     = local.common_tags
}

# ------------------------------------------------------------
# Production Monitoring
# ------------------------------------------------------------

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

# ------------------------------------------------------------
# Shared infrastructure: lookup only
# ------------------------------------------------------------

data "azurerm_container_registry" "shared" {
  name                = var.acr_name
  resource_group_name = var.acr_resource_group_name
}

data "azurerm_container_app_environment" "shared" {
  name                = var.shared_container_app_environment_name
  resource_group_name = var.shared_container_app_environment_resource_group_name
}

data "azurerm_client_config" "current" {}

# ------------------------------------------------------------
# Production Key Vault
# ------------------------------------------------------------

resource "random_string" "kv_suffix" {
  length  = 5
  special = false
  upper   = false
}

resource "azurerm_key_vault" "this" {
  name = substr(
    replace(
      "kv-${local.name_prefix}-${random_string.kv_suffix.result}",
      "-",
      ""
    ),
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

  tags = local.common_tags
}

# ------------------------------------------------------------
# Production Azure Files Storage
# ------------------------------------------------------------

resource "random_string" "storage_suffix" {
  length  = 5
  special = false
  upper   = false
}

resource "azurerm_storage_account" "production_data" {
  name = "stvn30f1mprod${random_string.storage_suffix.result}"

  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location

  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"

  https_traffic_only_enabled      = true
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = true

  tags = local.common_tags
}

resource "azurerm_storage_share" "production_data" {
  name               = "vn30f1m-data"
  storage_account_name = azurerm_storage_account.production_data.name
  quota              = 100
}

# Register the Production Azure Files share with the existing CAE.
# This adds a named storage entry; it does not replace the CAE.

resource "azurerm_container_app_environment_storage" "production_data" {
  name                         = "production-duckdb-files"
  container_app_environment_id = data.azurerm_container_app_environment.shared.id

  account_name = azurerm_storage_account.production_data.name
  share_name   = azurerm_storage_share.production_data.name
  access_key   = azurerm_storage_account.production_data.primary_access_key
  access_mode  = "ReadWrite"
}

# ------------------------------------------------------------
# Production Managed Identity
# ------------------------------------------------------------

resource "azurerm_user_assigned_identity" "container_app" {
  name                = "uami-${local.name_prefix}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name

  tags = local.common_tags
}

# ------------------------------------------------------------
# Managed Identity permissions
# ------------------------------------------------------------

resource "azurerm_role_assignment" "container_app_acr_pull" {
  scope                = data.azurerm_container_registry.shared.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.container_app.principal_id
}

resource "azurerm_role_assignment" "container_app_key_vault_secrets_user" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.container_app.principal_id
}

# ------------------------------------------------------------
# Production Container App
# ------------------------------------------------------------

module "container_app" {
  source = "../../modules/container_app"

  name_prefix                = local.name_prefix
  location                   = azurerm_resource_group.this.location
  resource_group_name        = azurerm_resource_group.this.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id

  acr_login_server = data.azurerm_container_registry.shared.login_server
  container_image  = var.container_image

  container_cpu    = var.container_cpu
  container_memory = var.container_memory
  min_replicas     = var.min_replicas
  max_replicas     = var.max_replicas

  app_insights_connection_string = azurerm_application_insights.this.connection_string

  identity_id                  = azurerm_user_assigned_identity.container_app.id
  container_app_environment_id = data.azurerm_container_app_environment.shared.id

  azure_files_storage_name = azurerm_container_app_environment_storage.production_data.name

  tags = local.common_tags

  depends_on = [
    azurerm_role_assignment.container_app_acr_pull,
    azurerm_role_assignment.container_app_key_vault_secrets_user,
    azurerm_container_app_environment_storage.production_data,
  ]
}
