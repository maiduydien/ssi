# Initial operations runbook

## Local startup

1. Copy `.env.example` to `.env`.
2. Set `DUCKDB_PATH` to the correct local database path, or use `DATA_MODE=mock` for a demo.
3. Install `requirements-dev.txt` in a virtual environment.
4. Run `python -m app.main`.
5. Confirm `/health`, `/ready`, `/version` and the UI footer's data-source label.

## Container smoke test

- `docker build -t ssi-v57-platform:local .`
- `docker run --rm -p 8050:8050 -e DATA_MODE=mock ssi-v57-platform:local`
- Check `http://localhost:8050/health`, `/ready`, `/version`.

## Troubleshooting

- Missing DB in `auto`: expected demo fallback; inspect footer and logs.
- Missing DB in `duckdb`: `/ready` returns 503 and repository raises a clear error.
- Port conflict: change `DASH_PORT`.
- Azure revision unhealthy: inspect container logs, `/health`, `/ready`, image tag, and ACR managed identity `AcrPull` assignment.
- Terraform failure: run `terraform validate`, inspect provider version and Azure permissions, and do not apply until plan is reviewed.

## Rollback

Deploy the previously successful immutable image tag through the release pipeline, then verify `/health`, `/ready`, chart loading and logs. The initial CD YAML is a deployment template; rollback approval/automation and environment-specific resource names must be configured and tested before production use.
