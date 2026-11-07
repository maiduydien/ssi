# Optional AKS target. AKS has materially higher cost/operational overhead than ACA.
# Deploy this only when Kubernetes is a deliberate learning or architecture objective.
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
variable "cluster_name" { type = string }
variable "acr_id" { type = string }

resource "azurerm_kubernetes_cluster" "this" {
  name                = var.cluster_name
  location            = var.location
  resource_group_name = var.resource_group_name
  dns_prefix          = var.cluster_name
  sku_tier            = "Free"

  default_node_pool {
    name       = "system"
    node_count = 1
    vm_size    = "Standard_D2s_v5"
    type       = "VirtualMachineScaleSets"
  }

  identity { type = "SystemAssigned" }

  network_profile {
    network_plugin      = "azure"
    network_policy      = "azure"
    load_balancer_sku   = "standard"
    outbound_type       = "loadBalancer"
  }
}

resource "azurerm_role_assignment" "acr_pull" {
  scope                = var.acr_id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_kubernetes_cluster.this.kubelet_identity[0].object_id
}

output "cluster_name" { value = azurerm_kubernetes_cluster.this.name }
output "resource_group_name" { value = azurerm_kubernetes_cluster.this.resource_group_name }
