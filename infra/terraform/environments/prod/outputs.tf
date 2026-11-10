
output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "acr_login_server" {
  value = data.azurerm_container_registry.shared.login_server
}

output "container_app_url" {
  value = module.container_app.fqdn
}

output "key_vault_name" {
  value = azurerm_key_vault.this.name
}

output "storage_account_name" {
  value = azurerm_storage_account.production_data.name
}

output "storage_share_name" {
  value = azurerm_storage_share.production_data.name
}

output "application_insights_connection_string" {
  value     = azurerm_application_insights.this.connection_string
  sensitive = true
}

output "shared_container_app_environment_id" {
  value       = data.azurerm_container_app_environment.shared.id
  description = "Existing shared Container Apps Environment."
}
