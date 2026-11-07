# Azure deployment learning guide

## Recommended learning sequence

1. Run locally and validate tests.
2. Build the Docker image locally.
3. Push the code to Azure Repos and GitHub (separate practice repositories or mirrors).
4. Run CI on pull requests; require review, tests, lint, dependency audit, and image scan.
5. Create Azure resources using Terraform after reviewing cost and security.
6. Publish one immutable image to ACR.
7. Promote that same tag/digest Dev → Staging → Production.
8. Configure Azure DevOps Environment approval gates for staging/production.
9. Verify `/health`, `/ready`, `/version`, logs, and App Insights before/after rollout.
10. Practice rollback to the previous image tag.

## Resource/service checklist

- Azure Repos or GitHub for source control.
- Azure DevOps Pipelines or GitHub Actions for CI.
- Azure Container Registry (ACR) for container images.
- Azure Key Vault for future credentials and connection strings.
- Managed identity / workload identity federation instead of long-lived service principal secrets where supported.
- Azure Container Apps as the initial container host.
- Azure App Service as the simpler alternative.
- AKS as the Kubernetes learning/advanced hosting target, not the default production choice for this small app.
- Terraform for infrastructure.
- Azure Storage remote state with lock support, private access, encryption and least-privilege RBAC.
- Azure Monitor, Application Insights and Log Analytics for observability.
- Microsoft Defender for Cloud / container scanning for security posture.

## Environment layout

- `shared` provisions the shared ACR first.
- `dev`, `staging` and `prod` create their own app/resource environments and reference the shared ACR. Use separate Terraform state keys and service connections.
- App Service is an alternate hosting target with a staging slot. AKS is a separate optional target.

## First Terraform/image bootstrap

1. Apply `infra/terraform/environments/shared` to create the shared ACR.
2. Build/push an initial image to ACR (CI publishing requires the Azure Docker service connection).
3. Apply `dev` with `container_image` set to the published immutable image.
4. Repeat for Staging/Production when needed, using separate remote state keys.

## Before applying Terraform

- Install Terraform 1.7+ and Azure CLI.
- Run `az login` and select the intended subscription.
- Ensure the Azure identity has permissions to create the resources in the plan.
- Confirm ACR name uniqueness and region availability.
- Build and push an image tag first; replace the bootstrap image reference.
- Run `terraform fmt -recursive`, `terraform init`, `terraform validate`, and `terraform plan`.
- Review the plan and Azure cost. `terraform apply` is a billable external action and is not performed by this project package.
- For shared/prod environments, set up remote state in a secured Azure Storage account and separate state per environment before applying.

## Secrets and permissions

Do not store Azure credentials, Key Vault secrets, database credentials, access tokens, or production `.env` files in Git. Configure service connections in Azure DevOps/GitHub OIDC and grant least privilege. Use separate deployment identities and Key Vault permissions for Dev, Staging and Production.

## Database architecture warning

The current market data source is a local DuckDB file. Azure Container Apps/App Service/AKS ephemeral container filesystems are not persistent shared database storage. Multiple replicas should not concurrently write to a shared DuckDB file. For a future cloud-native design, select a supported shared query/storage service or package immutable data snapshots with a deliberate mount and single-writer/read-only access model.
