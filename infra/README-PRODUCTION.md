# CI-CD Production — rollout package

## Design

- Branch: `main`; trigger: manual `workflow_dispatch`.
- Terraform: `1.9.8`; remote state: `vn30f1m/production.tfstate`.
- Production owns `rg-vn30f1m-production`, its Log Analytics workspace, Application Insights, Key Vault, UAMI, role assignments and Container App.
- Production reads the existing shared CAE (`cae-vn30f1m-dev` in `rg-vn30f1m-dev`) and ACR (`acrvn30f1mshared` in `rg-vn30f1m-shared`) as data sources. It does not manage either shared resource.
- Image is immutable and tagged with `${GITHUB_SHA}`.
- All deployment configuration is read from GitHub Environment secrets, not `vars.*`.
- Plan and Apply use separate Environments: `production-plan` and `production`.

## Repository placement

Copy into repository `maiduydien/ssi`:

- `infra/terraform/environments/production/*.tf`
- `.github/workflows/ci-cd-production.yml`
- `bootstrap/*` (operator-run bootstrap helpers; not part of the workflow runtime)

Keep the existing shared module at `infra/terraform/modules/container_app`; the Production root uses the same module interface as Staging.

## GitHub Environments

Create both Environments under **Settings → Environments**. Restrict both to the selected branch `main`.

### `production-plan`

- No required reviewer; this job creates the plan before the approval gate.
- Add all nine Environment secrets listed below.

### `production`

- Add Required reviewers (the production approver).
- Disable administrator bypass if the repository plan/UI supports it.
- Add the same nine Environment secrets; Environment secrets are only exposed to jobs referencing that Environment.

Add these secrets to BOTH Environments:

- `AZURE_CLIENT_ID` — Production app registration client ID (same in both Environments).
- `AZURE_TENANT_ID` — existing tenant ID.
- `AZURE_SUBSCRIPTION_ID` — target subscription ID.
- `TFSTATE_RESOURCE_GROUP` — existing Terraform state resource group.
- `TFSTATE_STORAGE_ACCOUNT_NAME` — existing state storage account.
- `TFSTATE_CONTAINER_NAME` — existing state container.
- `TFSTATE_KEY_PRODUCTION` — exactly `vn30f1m/production.tfstate`.
- `ACR_NAME` — `acrvn30f1mshared`.
- `ACR_LOGIN_SERVER` — actual login server returned by `az acr show`; do not guess it.

Copy shared backend/tenant/subscription/ACR values from the existing Staging configuration. Do not copy the Staging client ID or Staging state key.

**Plan availability:** GitHub's Required reviewers protection is plan/visibility dependent. For private repositories, confirm the account/organization plan supports required reviewers before relying on this gate. If the setting is unavailable, do not treat the Environment as approval-protected.

## OIDC Federation

The Production deployment app registration requires two federated identity credentials, one per GitHub Environment. The helper scripts in `bootstrap/` inspect the working Staging FIC and derive the exact repository subject prefix before creating the two Production credentials. This is important because GitHub repositories created after July 15, 2026, renamed/transferred after that date, or opted into immutable subjects use owner/repository IDs in the subject claim.

Expected subject suffixes:

- `:environment:production-plan`
- `:environment:production`

Issuer and audience are copied from the existing working Staging credential (normally `https://token.actions.githubusercontent.com` and `api://AzureADTokenExchange`).

## Azure RBAC

Follow `bootstrap/production-rbac.md`. The Production deployment identity needs scoped access to the state container, shared ACR, shared CAE and Production resource group. Terraform creates two workload role assignments: `AcrPull` for the Production UAMI on the shared ACR and `Key Vault Secrets User` for that UAMI on the Production Key Vault. The deployment identity therefore needs narrowly conditioned Role Based Access Control Administrator permission at those two scopes.

Do not grant subscription-wide Owner. The Production Resource Group is pre-created by an administrator; the workflow imports that Resource Group into the new Production state before planning, avoiding subscription-wide Contributor for the deployment identity.

## First deployment safeguards

- Ensure the shared module exists at `infra/terraform/modules/container_app`.
- Ensure the Production state key is new and not the Staging key.
- Ensure `rg-vn30f1m-production` exists before dispatch. The workflow imports it only when the Production state is empty; it refuses partial/mismatched state.
- Inspect the plan artifact before approving the `production` Environment. It must contain only Production-owned resources and no CAE/ACR resources.
- The CI pipeline must have published `${GITHUB_SHA}` to `acrvn30f1mshared.azurecr.io/lssiv01` for the exact commit on `main`; otherwise the image existence check fails. Confirm the Dev build workflow publishes main commits before deploying Production.
- The plan artifact contains a sensitive binary Terraform plan. Retention is one day; do not commit or publicly share it.
- Smoke tests verify `/health`, `/ready`, and `/version`, including the deployed commit SHA.
