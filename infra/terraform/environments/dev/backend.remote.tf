# Copy this file to backend.tf only after provisioning the Azure Storage backend.
# Terraform backend blocks cannot use interpolated variables.
terraform {
  backend "azurerm" {}
}
