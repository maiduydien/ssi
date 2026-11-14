# SSI iBoard-like VN30F Back-Test Platform — Refactored V57 baseline

This repository is a **behavior-preserving first refactor** of the uploaded V57 Python/Dash application. It is an educational Back-Test/paper-trading UI, not an SSI product, not a broker integration, and does not send real orders.

## What changed in this refactor

- Moved application startup into the Python package: `python -m app.main`.
- Moved central configuration to `app/config.py` and added `.env` loading.
- Introduced a DuckDB connection/schema Repository and a Tick Repository.
- Moved OHLCV aggregation into `app/engines/candle_engine.py`.
- Moved tick-cache merge logic into `app/engines/tick_merge_engine.py`.
- Added a Market Data Service with explicit `DATA_MODE` policy.
- Kept a compatibility facade (`data_access.py`, `config.py`) for older imports.
- Preserved the existing Dash layout and callback behavior in `app/ui/dashboard.py` as a controlled migration boundary. The UI/replay/order callbacks are still largely in this V57 module; they are **not yet fully split** into callback/service/engine modules. This is deliberate so the first refactor can run before the later callback and business-logic refactors.
- Added `/health`, `/ready`, and `/version` endpoints.
- Added pytest tests, Docker, Azure DevOps CI/CD templates, GitHub Actions CI, and Terraform hosting options.

## Architecture (current migration stage)

```text
Browser / Dash UI
       |
       v
app/ui/dashboard.py  (existing V57 layout + callbacks, migration boundary)
       |
       +---- app/services/market_data_service.py
       |                 |
       |                 v
       |        app/data/tick_repository.py
       |                 |
       |                 v
       |        app/data/duckdb_repository.py ---> DuckDB read-only file
       |
       +---- app/engines/candle_engine.py
       +---- app/engines/tick_merge_engine.py

Startup / operational endpoints: app/main.py
Configuration: app/config.py
Mock data: app/fixtures/mock_data.py
```

### Target architecture (future refactor steps)

```text
app/
  ui/layout.py
  ui/components/
  ui/callbacks/{replay,chart,viewport,order}_callbacks.py
  services/{backtest,trading,account}_service.py
  engines/{replay,candle,chart,order,account}_engine.py
  data/{duckdb,tick,candle}_repository.py
  observability/{logging_config,metrics}.py
```

The callback-heavy original V57 code is retained together until callback registration and Dash shared-state dependencies are refactored and regression-tested. Do not assume this migration stage already provides per-user isolation or production-grade order state.

## Requirements

- Python 3.11 (recommended for local development and container builds)
- Windows 10/11, Linux, or macOS
- DuckDB file with a `vn30f1m_ticks` table (optional for demo mode)

Install:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

Copy `.env.example` to `.env` and update `DUCKDB_PATH` to the real local DuckDB path. `.env` is ignored by Git.

## Run on Windows

```powershell
python -m app.main
```

Or run `run_dashboard.bat`. The batch file creates `.venv`, installs requirements, copies `.env.example` to `.env` if needed, and starts the Dash app.

Open: http://127.0.0.1:8050

## Data source modes

`DATA_MODE` controls how the application handles data:

| Mode | Behavior | Appropriate use |
|---|---|---|
| `auto` | Read DuckDB if available; if missing/invalid/empty, log a warning and use synthetic ticks | Local UI development and initial Azure demo |
| `duckdb` | Require a working DuckDB file and schema; surface data errors instead of switching to mock | Strict local data validation |
| `mock` | Always use deterministic synthetic ticks | UI demos and tests only |

**Important:** In `auto` mode the UI can run with mock data. Confirm the footer data-source label before analyzing a chart. Do not use mock data for strategy research, trading decisions, or production back-test results.

Required tick columns: `DateTime`, `Price`, `Volume`. Optional: `ID`, `MarketOrderType`. Output columns are normalized to `time`, `price`, `volume`, `tick_id`, and `market_order_type` where available.

The loader retains V57's behavior: for `limit > 0`, it selects the latest N ticks using descending timestamp order, then returns those rows chronologically. `limit=0` loads all rows.

## Health endpoints

- `GET /health`: process is running.
- `GET /ready`: app can serve traffic under the configured data mode. In strict DuckDB mode, the repository must pass a basic query.
- `GET /version`: app version and build commit SHA.

These endpoints are intended for container/orchestrator probes. Azure Application Insights SDK instrumentation and business metrics are future work; the current app emits Python logs to stdout/stderr.

## Tests and lint

```powershell
pytest --cov=app --cov-report=term-missing
ruff check app/data app/engines app/services app/config.py app/main.py tests
```

The current unit tests cover OHLCV aggregation, basic DuckDB repository query behavior, and mock-mode data service. Integration/browser tests against the real Windows DuckDB database remain to be run on your machine.

## Docker

```powershell
docker build -t ssi-v57-platform:local .
docker run --rm -p 8050:8050 -e DATA_MODE=mock ssi-v57-platform:local
```

To use a DuckDB file in a container, mount it explicitly. Example (Linux Docker syntax):

```bash
docker run --rm -p 8050:8050 \
  -e DATA_MODE=duckdb \
  -e DUCKDB_PATH=/data/vn30f1m.duckdb \
  -v /your/local/data:/data:ro \
  ssi-v57-platform:local
```

DuckDB is a local file database. Do **not** mount the same writable DuckDB file concurrently across multiple Azure app/container replicas. For production multi-instance architecture, move shared tick storage to a suitable shared data service or use immutable per-run data files with a clear access strategy. The current Dash order/position state also remains browser-session based and is not shared or persisted server-side.

## Azure / CI/CD files

- `azure-pipelines.yml`: Azure DevOps CI, source checks/tests, dependency audit, Docker build/scan, optional ACR push on `main`.
- `pipelines/cd.yml`: ACA release template deploying a previously CI-tested immutable image tag through Dev, Staging, Production.
- `pipelines/cd-app-service.yml`: App Service deployment-slot and swap template.
- `.github/workflows/ci.yml`: GitHub Actions CI/CD for the existing Dev environment: checks, Docker build/Trivy scan, immutable ACR push on `develop`, Terraform Plan, protected Environment approval, Apply, and ACA smoke tests. See `docs/CI-CD-DEV-SETUP.md` before enabling it.
- `infra/terraform/environments/shared`: creates the shared ACR first. `dev`, `staging`, `prod` each create their own RG, Key Vault, Log Analytics, App Insights and ACA while referencing the shared ACR.
- `infra/terraform/targets/app_service`: alternative Azure App Service container hosting target.
- `infra/terraform/targets/aks`: optional AKS cluster target (higher operational/cost burden).
- `infra/kubernetes`: sample Kubernetes Deployment and Service.

Before using pipelines, replace service connection/ACR/resource names and configure Azure DevOps Environments approvals. CI/CD files are templates and are not connected to your Azure subscription automatically.

### Terraform notes

Terraform in `infra/terraform/environments/dev` uses local state for initial learning. Do not use local state for a team or production environment. Configure Azure Storage remote state with encryption, private access, restricted RBAC, state locking, and separate state per environment before shared deployment. Never commit `.tfstate`, `.tfvars`, or credentials.

Bootstrap order: apply `shared` first to create ACR; publish the first image; then apply `dev`/`staging`/`prod` with the exact existing image reference using `-var="container_image=..."`. The ACA template references a placeholder until then. `terraform apply` can create billable Azure resources; review `terraform plan` and cost before applying.

## Azure hosting decision

- **Azure Container Apps (default learning path):** containerized Dash app with lower operational overhead than AKS.
- **Azure App Service:** simpler web-app hosting alternative; use the target-specific Terraform folder.
- **AKS:** learn and deploy only when Kubernetes control/networking/orchestration requirements justify its cost and operational complexity.

Do not deploy all three targets simultaneously; they are alternatives.

## Security and production limitations

This baseline is not production-ready yet. Outstanding items include:

- Dash callback/replay/order code is still concentrated in `app/ui/dashboard.py`.
- No authentication/authorization or server-side per-user trade state.
- Simulated orders/account values are not persisted and are not broker orders.
- No session isolation for process-global replay caches and timeframe-switch state.
- DuckDB file is not a suitable shared writable database for horizontally scaled replicas.
- No backup/restore or disaster recovery procedure for market data.
- Application Insights SDK telemetry, alerts, SLOs, and rollback automation need configuration/testing.
- Real browser testing on Windows with the actual VN30F database is still required.

## Source preservation

`legacy/v57_original/` contains the original uploaded ZIP snapshot for comparison and rollback. It is not included in the runtime Docker image.

## Testing Azure board connection 
