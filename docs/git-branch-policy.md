# Source control and branch policy (Azure Repos + GitHub practice)

## Branch model from the Azure CI/CD reference

- `feature/<work-item>-short-name`: individual work.
- `develop`: shared integration and automatic Development CI/deploy path.
- `main`: release-ready code; CI validates, scans, and publishes an immutable image.
- `hotfix/<issue>`: urgent production fix; review, test and release through Staging before Production.

## Pull Request policy to configure in Azure Repos and GitHub

- Require at least one reviewer (two for production-sensitive changes).
- Require successful CI status checks.
- Require unit tests and coverage reporting. The initial refactor baseline has low coverage; establish and increase the threshold after more callback/business logic is extracted instead of pretending the current project meets 70–80%.
- Require dependency and container scan review.
- Require no unresolved comments.
- Link a work item/change request where the team requires it.
- Prevent direct pushes to `main`; use protected branches and PR completion.

## Azure Repos and GitHub

The same code can be practiced in both systems:

1. Create an Azure Repos Git repository and push the project.
2. Configure `azure-pipelines.yml` and Azure Repos branch policies.
3. Create a separate GitHub repository (or mirror) and enable `.github/workflows/ci.yml`.
4. Compare PR checks, status checks, branch protection, service connection/OIDC setup and release controls.

Do not commit `.env`, `.tfstate`, `.tfvars`, DuckDB data files, Azure credentials, certificates or secrets.
