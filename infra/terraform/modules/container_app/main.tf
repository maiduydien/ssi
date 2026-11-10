
# ------------------------------------------------------------
# Container Apps Environment
# ------------------------------------------------------------

resource "azurerm_container_app_environment" "this" {
  count = var.container_app_environment_id == null ? 1 : 0

  name                       = "cae-${var.name_prefix}"
  location                   = var.location
  resource_group_name        = var.resource_group_name
  logs_destination           = "log-analytics"
  log_analytics_workspace_id = var.log_analytics_workspace_id

  tags = var.tags

  lifecycle {
    ignore_changes = [
      workload_profile,
    ]
  }
}

locals {
  container_app_environment_id = (
    var.container_app_environment_id != null
    ? var.container_app_environment_id
    : azurerm_container_app_environment.this[0].id
  )
}

# ------------------------------------------------------------
# Container App
# ------------------------------------------------------------

resource "azurerm_container_app" "this" {
  name                         = "ca-${var.name_prefix}"
  container_app_environment_id = local.container_app_environment_id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"

  tags = var.tags

  lifecycle {
    ignore_changes = [
      workload_profile_name,
    ]
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [var.identity_id]
  }

  registry {
    server   = var.acr_login_server
    identity = var.identity_id
  }

  template {
    min_replicas = var.min_replicas
    max_replicas = var.max_replicas

    # Attach Azure Files only when a storage registration is supplied.
    dynamic "volume" {
      for_each = var.azure_files_storage_name == null ? [] : [var.azure_files_storage_name]

      content {
        name         = "duckdb-data"
        storage_type = "AzureFile"
        storage_name = volume.value
      }
    }

    container {
      name   = "ssi-v57"
      image  = var.container_image
      cpu    = var.container_cpu
      memory = var.container_memory

      env {
        name  = "DASH_HOST"
        value = "0.0.0.0"
      }

      env {
        name  = "DASH_PORT"
        value = "8050"
      }

      env {
        name  = "DATA_MODE"
        value = "auto"
      }

      env {
        name  = "DUCKDB_PATH"
        value = "/app/data/vn30f1m.duckdb"
      }

      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = var.app_insights_connection_string
      }

      dynamic "volume_mounts" {
        for_each = var.azure_files_storage_name == null ? [] : [1]

        content {
          name = "duckdb-data"
          path = "/app/data"
        }
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8050
    transport        = "auto"

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }
}
