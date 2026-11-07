# Azure App Service alternative

This is an alternative to the default Azure Container Apps environment. It expects an existing resource group and ACR image.

1. `terraform init`
2. `terraform validate`
3. Create a local, ignored `terraform.tfvars` with resource group, region, app name, ACR login server, image repository and immutable image tag.
4. `terraform plan` and review cost/security.
5. `terraform apply` only after approval.

App Service is a lower-operations option for a conventional web app. Confirm Linux container support, plan SKU, managed-identity ACR pull, `WEBSITES_PORT=8050`, and health checks. For production, use deployment slots and swap after smoke tests; rollback by swapping back.
