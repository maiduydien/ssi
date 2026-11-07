# SkillsMustHave / Azure CI-CD source mapping

This map is based on the uploaded `SkillsMustHave.txt` and `AzureDevOpsCI_CD.docx`. It distinguishes what the starter repo contains from what must still be learned, configured, and tested.

## SkillsMustHave

| Skill from the job description | Project/lab practice | Status in this starter ZIP |
|---|---|---|
| Communication, customer mindset, English technical collaboration | README/runbook, architecture notes, PR descriptions, incident and release notes | Documentation practice is present; real team/customer practice is future work |
| Public cloud hands-on (Azure preferred for this learning path) | Azure Container Apps default Terraform environment; App Service and AKS alternatives | Infrastructure templates present; no Azure resources deployed |
| Linux administration/troubleshooting | Python slim Linux container, Docker build, Azure container logs and probes | Container baseline present; Linux troubleshooting exercises still to be completed |
| Basic networking | Azure ingress, container port 8050, HTTPS endpoints, ACR access and identity | Basic service configuration present; private networking/VNet/NSG/ingress hardening is future work |
| Infrastructure as Code (Terraform) | Terraform environment, reusable ACA module, App Service and AKS target | Starter IaC present; not validated with Terraform CLI in this execution environment |
| Cloud architecture, security, HA | Managed identity, ACR Pull RBAC, Key Vault RBAC, environment separation, replica settings | Initial scaffold only; production threat model/HA review still required |
| CI/CD and automation | Azure DevOps CI/CD YAML, GitHub Actions CI, image versioning, test/scan stages | Pipeline templates present; service connections, branch policies and environment approvals need setup |
| Analytical troubleshooting | health/ready/version endpoints, logging, tests and runbook | Initial baseline present; metrics/alerts/SLO and live incident drills are future work |

## Nice-to-have skills from SkillsMustHave

| Skill | Where it is represented | Learning status |
|---|---|---|
| Cloud/Solution Architecture | `docs/architecture.md`, Azure deployment guide | Architecture foundations; deeper design exercises later |
| Docker, Kubernetes and container platforms | `Dockerfile`, ACA Terraform, App Service target, AKS target, `infra/kubernetes/` | Container baseline present; AKS deployment is optional and not run |
| Grafana/Prometheus/ELK/OpenTelemetry | Observability package, Azure Monitor/Application Insights/Log Analytics resources | Azure observability resources scaffolded; SDK instrumentation, dashboards, alerts and Prometheus/Grafana labs remain |
| Cloud migration, landing zone, DR, security | Azure Terraform and deployment/runbook docs | Only introductory scaffold; landing zone, DR and migration design are later modules |
| Customer-facing consulting/proposal | Deployment and architecture docs | Future exercises: architecture proposal, trade-off memo and customer walkthrough |
| AI/ML/GenAI infrastructure | Not required by current VN30F UI scope | Not implemented; can be a separate future learning track |
| Certifications | Azure/Terraform/Kubernetes exam topics can be mapped later | No certification preparation material in this ZIP yet |
| Multinational/global team work | English README, PR template and issue templates | Practice by writing PRs, incident reports and technical explanations in English |

## AzureDevOpsCI_CD.docx requirements mapping

- PR/merge CI: `azure-pipelines.yml` and `.github/workflows/ci.yml`.
- Code quality/tests/coverage: Ruff, pytest, pytest-cov; branch policy and coverage threshold must be configured in the platform.
- Dependency scan: `pip-audit`.
- Container build and scan: Docker build + Trivy.
- Immutable version tags: Azure Build ID and source commit; GHCR run number and commit SHA.
- ACR: Terraform creates ACR; Azure pipeline publishes only on `main` after ACR service connection configuration.
- Dev/Staging/Production: `pipelines/cd.yml`; Azure DevOps Environment approvals must be configured in the UI.
- Key Vault: Terraform provisions RBAC-enabled Key Vault; no app secrets exist yet, so secret injection is intentionally not wired. Use Key Vault references/managed identity when secrets become necessary.
- Workload identity federation/managed identity: ACA system identity and ACR Pull role assignment are scaffolded. Azure DevOps service connection must be configured with federated credentials/least privilege where available.
- Terraform: environment, modules, alternative hosting targets; remote state must be set up before team/prod use.
- App Service slot/ACA revision/AKS rollout and rollback: docs and target scaffolds included; rollout strategy and rollback must be rehearsed before production.
- Health/readiness/version: `/health`, `/ready`, `/version`.
- Monitoring: Log Analytics and Application Insights resources are scaffolded. SDK telemetry, alerts, availability tests, error/latency thresholds and deployment monitoring gates still need implementation.

## Important gap

The project currently contains infrastructure/pipeline templates, not an activated Azure CI/CD deployment. The user must configure Azure subscription, resource names, service connections, OIDC/managed identity, branch policies, approvals and remote state. No cloud resource has been created by this ZIP.
