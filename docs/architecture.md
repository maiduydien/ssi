# Architecture and migration record

## Source-to-target mapping

| Original V57 element | New location | Migration status |
|---|---|---|
| `config.py` | `app/config.py` | Moved; root facade retained |
| DuckDB connection/schema checks in `data_access.py` | `app/data/duckdb_repository.py` | Refactored into repository/context manager |
| `load_ticks`, `load_ticks_since` | `app/data/tick_repository.py` + `app/services/market_data_service.py` | Moved; service handles source mode/fallback |
| `merge_tick_frames` | `app/engines/tick_merge_engine.py` | Moved from V57 algorithm with behavior retained |
| `build_candles` | `app/engines/candle_engine.py` | Moved; Pandas resampling behavior retained |
| `make_mock_ticks` | `app/fixtures/mock_data.py` | Moved; clearly labeled synthetic data |
| `load_market_snapshot`, `get_data_status` | `app/services/market_data_service.py` | Moved |
| Dash layout, callbacks, replay/order state | `app/ui/dashboard.py` | Preserved as a transitional monolith for behavior safety |
| startup | `app/main.py` | New package entrypoint |
| app health/readiness/version | Flask routes registered by `app/main.py` | Added |

## Data flow

1. `app/main.py` imports the Dash app and starts it.
2. Dash layout initialization calls the market-data service for the market snapshot/status.
3. `MarketDataService` applies `DATA_MODE` policy.
4. `TickRepository` opens read-only DuckDB connections through `DuckDBRepository`.
5. Query result columns are normalized to the V57-compatible tick schema.
6. The existing dashboard cache holds tick data in process RAM.
7. `CandleEngine` computes OHLCV from the cached tick DataFrame.
8. The existing replay callback and browser-side callback update chart/replay state.

## State boundaries (not changed in this refactor)

- DuckDB tick history: persistent local file.
- `_TICKS_CACHE`, candle caches, replay caches and timeframe-switch executor: process RAM.
- `dcc.Store` state: browser memory/session storage.
- drawing lines: browser `localStorage` via `assets/chart_interactions.js`.
- orders/positions/account: simulated browser-session state; not durable server state.

## Fallback policy

`auto` preserves the old local-demo behavior but now logs a warning and marks the source as mock. `duckdb` is strict and raises data-access errors. `mock` is explicit demo mode. For Azure production, prefer strict mode only after data source architecture is settled; with the current single-file DuckDB design, multiple replicas are not safe to share the same writable DB.

## Known issues intentionally not fixed here

- `merge_tick_frames` without tick IDs uses `(time, price, volume)` as a duplicate key; distinct trades can share these values. Preserved for behavior continuity pending a data identity decision.
- V57 `build_candles` uses generic Pandas resampling, not an exchange-session-aware VN30F calendar.
- Dashboard callback/global-state isolation remains unresolved.
- Real-browser regression tests have not been run in this environment.
