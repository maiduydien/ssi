# Terraform layout

- `environments/shared`: creates the shared Resource Group and ACR first.
- `environments/dev`, `staging`, `prod`: each creates its own app Resource Group, Key Vault, Log Analytics, Application Insights and ACA; all reference the shared ACR.
- `modules/container_app`: reusable ACA environment + app module.
- `targets/app_service`: alternate App Service deployment with staging slot.
- `targets/aks`: optional AKS cluster target.

The three hosting targets (ACA, App Service, AKS) are alternatives. Start with ACA, not all at once.

## Bootstrap order

1. Apply `shared` Terraform to create the shared ACR.
2. Build and publish the first image to ACR using CI or an approved manual bootstrap process.
3. Apply `dev` with the exact existing image tag.
4. Apply `staging` and `prod` only when those environments are needed.
5. Promote the same ACR image tag through the CD pipeline.

Initial local Terraform state is only for learning. For team/staging/production, configure Azure Storage remote state, private access, encryption, locking, RBAC, and distinct state keys per environment. Terraform state may contain sensitive values; treat it as sensitive.
