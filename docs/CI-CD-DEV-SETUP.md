# GitHub Actions + Azure OIDC + Terraform + ACR + ACA (Dev)

> **Scope of the first rollout:** Development environment only. Staging/Production are not deployed by this workflow yet.
> This pipeline deliberately refuses to proceed if the expected existing Terraform State is missing or if the plan contains a delete/replacement.

## Pipeline

1. Push/merge code to `develop`.
2. GitHub Actions installs Python dependencies, runs Ruff, pytest, pip-audit, builds Docker, and scans the image with Trivy.
3. On `push` to `develop` only, GitHub Actions authenticates to Azure using OIDC and pushes the image to the existing ACR with the full Git commit SHA as an immutable tag.
4. Terraform validates the roots.
5. Terraform initializes the **existing Dev remote State**, verifies that the Dev Resource Group and Container App addresses are present, and creates a plan using the new image tag.
6. The workflow blocks plans that contain any `delete` action (including replacement).
7. The plan and review text are retained as a short-lived GitHub artifact.
8. The `dev` GitHub Environment pauses the Apply job for required reviewer approval.
9. After approval, the workflow applies the exact saved plan, then checks `/health`, `/ready`, and `/version` on ACA. The `/version` commit must match the deployed Git SHA.

Pull requests and pushes to `main` run CI/validation only. They do not push to ACR or deploy.

## Before enabling the workflow

### A. Check the Git repository contents

The repository should contain the application, Dockerfile, Terraform source, lock files, and this workflow. Do **not** commit:

- `.git/` as a nested archive directory;
- `.terraform/` provider downloads;
- `terraform.tfstate*`, state backups, or exported state JSON;
- `*.tfplan`, `*.plan`, `*-plan.txt`, or `tfplan-review.txt`;
- local `terraform.tfvars`;
- `.env`;
- Azure credentials, access keys, SAS tokens, or service-principal secrets.

`terraform.tfstate` and plan files can contain secrets even if Terraform marks some outputs as `sensitive`.

The active backend declaration (`backend.remote.tf`) is Terraform source and must be committed if it is the backend block used by this root. It contains only `terraform { backend "azurerm" {} }`. Do not commit the local `backend.remote.hcl` file; the workflow supplies backend parameters from GitHub Actions Variables.

### B. Confirm remote State before running CI/CD

This workflow expects the existing Dev State to contain at least:

```text
azurerm_resource_group.this
module.container_app.azurerm_container_app.this
```

Use your existing Dev backend configuration locally and check:

```powershell
terraform -chdir=infra/terraform/environments/dev state list
```

The output must point to the **existing Azure resources**, not an empty/new state. Confirm the remote blob key matches the current `backend.remote.hcl` values. Do not change the State key, re-import, or migrate State as part of the first CI/CD run.

If the state check fails in GitHub Actions, the workflow intentionally stops. Do not bypass the guard. Investigate the backend account/container/key and perform a deliberate State migration/import with a backup first.

### C. Azure OIDC identity

Use an Entra ID App Registration (or another supported federated identity) for GitHub Actions. Do not create a long-lived client secret for this pipeline.

Create **two Federated Credentials** for the same GitHub repository:

| Job type | Issuer | Audience | Subject |
|---|---|---|---|
| CI image push and Terraform Plan on `develop` | `https://token.actions.githubusercontent.com` | `api://AzureADTokenExchange` | `repo:<OWNER>/<REPO>:ref:refs/heads/develop` |
| Terraform Apply job using GitHub Environment `dev` | `https://token.actions.githubusercontent.com` | `api://AzureADTokenExchange` | `repo:<OWNER>/<REPO>:environment:dev` |

Replace `<OWNER>/<REPO>` with the exact GitHub organization/user and repository. The environment subject is required because the Apply job uses `environment: dev`.

In Azure Portal: **Microsoft Entra ID → App registrations → your app → Certificates & secrets → Federated credentials → Add credential → GitHub Actions**. Create the branch credential and the environment credential separately.

### D. Azure RBAC for the GitHub identity

Assign only the permissions needed, at the narrowest practical scopes:

| Scope | Role / permission | Purpose |
|---|---|---|
| Existing ACR | `AcrPush` | CI can push the Docker image |
| Existing ACR | Read access to the registry resource | Terraform can read the ACR data source |
| Dev Resource Group | `Contributor` | Terraform can update Dev resources |
| Terraform State Storage Account/container | `Storage Blob Data Contributor` | Terraform backend can read/write/lock the state blob using Entra ID |

**RBAC caution:** The Dev Terraform root also declares `azurerm_role_assignment` resources for the Container App UAMI (`AcrPull` and `Key Vault Secrets User`). `Contributor` cannot create role assignments. For the first image-only deployment, these assignments should already exist and should not change. If a future Plan needs to create/update role assignments, stop and review it; grant a narrowly scoped `Role Based Access Control Administrator` permission (preferably with an Azure role-assignment condition restricting allowed roles/principals) only when intentionally managing RBAC through CI. Do not grant subscription-wide Owner just to make the workflow pass.

For the remote backend, use Entra/OIDC (`use_oidc=true`, `use_azuread_auth=true`), not Storage Account access keys. The backend identity needs `Storage Blob Data Contributor` on the state storage scope. The State Storage Account must already exist and must not be recreated by this Dev workflow.

### E. GitHub Actions Variables

Open **GitHub repository → Settings → Secrets and variables → Actions → Variables** and add:

| Variable | Value |
|---|---|
| `AZURE_CLIENT_ID` | Application/identity client ID used for OIDC |
| `AZURE_TENANT_ID` | Microsoft Entra tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |
| `ACR_NAME` | `acrvn30f1mshared` |
| `ACR_LOGIN_SERVER` | `acrvn30f1mshared.azurecr.io` |
| `TFSTATE_RESOURCE_GROUP` | Resource group that contains the existing State Storage Account |
| `TFSTATE_STORAGE_ACCOUNT_NAME` | Existing State Storage Account name |
| `TFSTATE_CONTAINER_NAME` | Existing blob container name |
| `TFSTATE_KEY_DEV` | Exact existing Dev state blob key from your current backend config |

These are identifiers/configuration values, not client secrets. OIDC means this workflow does not need `AZURE_CLIENT_SECRET`.

Do not guess the State key. Copy the exact values from your existing `infra/terraform/environments/dev/backend.remote.hcl` and confirm them against the Azure Storage blob.

### F. Protect the GitHub Environment

In **Settings → Environments → New environment**, create `dev`:

- Add at least one required reviewer.
- Enable **Prevent self-review** if available/appropriate.
- Restrict deployment branches to `develop`.
- Ensure the person approving the run can inspect the Plan artifact and workflow logs.

The environment name alone does **not** guarantee a manual approval. Required reviewers must be configured in GitHub Settings.

### G. Protect `develop`

Recommended workflow:

```text
feature branch → Pull Request → CI checks → review/merge to develop → CI/CD Dev
```

Protect `develop` so developers cannot bypass review and CI by pushing directly. The deployment is triggered after a commit lands on `develop`.

## GitHub Actions outputs and artifacts

- Docker tag: `${ACR_LOGIN_SERVER}/lssiv01:<full-git-sha>`.
- No mutable `latest` tag is used for deployment.
- Terraform Plan artifact name: `terraform-plan-dev`.
- Plan artifact retention: 1 day. It includes a binary saved plan and human-readable plan output. Treat it as sensitive and limit repository/artifact access.
- The Apply job applies the exact saved Plan, not a newly recalculated Plan.
- `terraform apply` does not run until the `dev` Environment approval is granted.
- The automatic Dev pipeline rejects any Plan with a deletion/replacement action. If a resource replacement is intentionally needed, handle it through a separate reviewed maintenance procedure, not by disabling this guard casually.

## First deployment checklist

1. Commit the active `backend.remote.tf` declaration and `.github/workflows/ci.yml`.
2. Ensure `.gitignore` protects State, tfvars, backend config, plans, `.terraform/`, and `.env`.
3. Verify the exact remote Dev State key and resource addresses locally.
4. Configure Azure OIDC federated credentials and RBAC.
5. Configure GitHub Actions Variables.
6. Create the protected GitHub Environment `dev` with required reviewers.
7. Push a small, harmless change to a feature branch and open a PR; confirm CI passes and no ACR push/deploy occurs.
8. Merge to `develop`; confirm CI pushes the SHA image to ACR and Terraform Plan completes.
9. Review the `terraform-plan-dev` artifact. Confirm there are no deletes/replacements and only expected changes (normally the ACA image/revision).
10. Approve the `dev` Environment deployment.
11. Confirm Terraform Apply and all ACA smoke tests pass.

## Troubleshooting

- **Azure Login / federated credential error:** verify exact repository owner/name, branch subject for CI/Plan, and `environment:dev` subject for Apply. Check the GitHub Environment name and Azure tenant/app IDs.
- **ACR push denied:** verify `AcrPush` at the existing ACR scope and `ACR_NAME`/`ACR_LOGIN_SERVER` variables.
- **State backend 403:** verify the backend identity has `Storage Blob Data Contributor`, Entra auth is enabled, and the storage account/container/key are correct.
- **State guard failed:** likely wrong State blob key or missing resource addresses. Stop and verify remote State; do not apply against empty State.
- **Terraform role assignment permission denied:** the CI identity lacks RBAC assignment write permission. Do not grant broad Owner automatically. Review whether RBAC changes are actually required and provision those in a controlled bootstrap step or grant narrow RBAC Administrator permission.
- **Plan contains delete/replacement:** workflow stops intentionally. Review Provider/version/config drift and State before deciding how to proceed.
- **ACA smoke test fails:** inspect Container App revision, image pull status, `/health`, `/ready`, and logs. Do not destroy/recreate the Container App as the first troubleshooting step.

## Scope limitation

This workflow deploys only the existing Dev root. It does not apply `shared`, `staging`, `prod`, App Service, or AKS roots. ACR, the State Storage Account, and the current Dev resources must already exist. The first CI/CD rollout is an application/image update, not a full infrastructure bootstrap.
