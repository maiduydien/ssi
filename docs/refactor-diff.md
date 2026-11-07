# Refactor change summary

## Behavior-preserving moves

- Original `app.py` moved to `app/ui/dashboard.py`.
- Original Dash UI/replay/order callback body is unchanged except import statements, Dash `assets_folder` path, and removing the `if __name__ == '__main__'` launch block.
- `build_candles()` moved from `data_access.py` to `app/engines/candle_engine.py` with the same Pandas `resample().agg()` logic.
- `merge_tick_frames()` moved from `data_access.py` to `app/engines/tick_merge_engine.py` without changing its core algorithm.
- `make_mock_ticks()` moved to `app/fixtures/mock_data.py` with deterministic seed and same synthetic tick generation.
- `load_ticks()` and `load_ticks_since()` are implemented through `TickRepository` and `MarketDataService`; output columns and latest-N chronological ordering remain compatible.

## Intentional infrastructure/application changes

- `app/config.py` centralizes configuration and loads `.env`.
- `DATA_MODE=auto|duckdb|mock` distinguishes local demo fallback from strict DuckDB mode.
- In `auto`, missing/invalid/empty DuckDB is logged and visibly labeled as mock/demo fallback. In `duckdb`, data errors are surfaced.
- `/health`, `/ready`, `/version` routes were added.
- Dash asset lookup uses an explicit root `assets/` path after moving the app module.
- Azure/container startup uses `0.0.0.0` and environment-provided port.

## Not yet refactored

- Replay callback, timeframe switching, order callback and Dash layout still reside in the large `app/ui/dashboard.py` compatibility module. Splitting them into UI callback modules and pure Replay/Order Services is the next controlled refactor phase; it was not done here because the first package must preserve V57's stateful callback behavior.
