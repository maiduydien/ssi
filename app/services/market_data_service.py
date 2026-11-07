"""Application-facing market data service and explicit demo fallback policy."""
import logging
import pandas as pd

from app.config import DB_PATH, TABLE_NAME, TICK_LOAD_LIMIT, DATA_MODE
from app.data.duckdb_repository import DuckDBRepository, DataAccessError
from app.data.tick_repository import TickRepository
from app.fixtures.mock_data import make_mock_ticks

logger = logging.getLogger(__name__)


class MarketDataService:
    def __init__(self, db_path=DB_PATH, table_name=TABLE_NAME, mode=DATA_MODE,
                 default_limit=TICK_LOAD_LIMIT):
        self.db_path = db_path
        self.table_name = table_name
        self.mode = mode
        self.default_limit = int(default_limit)
        self.database = DuckDBRepository(db_path, table_name)
        self.tick_repository = TickRepository(self.database)
        self.last_source = "not_loaded"
        self.last_error = None

    def load_ticks(self, limit=None):
        if limit is None:
            limit = self.default_limit
        if self.mode == "mock":
            self.last_source = "mock"
            self.last_error = None
            return make_mock_ticks()
        if self.mode == "duckdb":
            df = self.tick_repository.load_ticks(limit)
            self.last_source = "duckdb"
            self.last_error = None
            return df
        if not self.db_path.is_file():
            self.last_source = "mock"
            self.last_error = f"DuckDB file not found: {self.db_path}"
            logger.warning("Using synthetic ticks because DuckDB is unavailable: %s", self.last_error)
            return make_mock_ticks()
        try:
            df = self.tick_repository.load_ticks(limit)
            if df.empty:
                self.last_source = "mock"
                self.last_error = "DuckDB query returned no tick rows"
                logger.warning("Using synthetic ticks: %s", self.last_error)
                return make_mock_ticks()
            self.last_source = "duckdb"
            self.last_error = None
            return df
        except DataAccessError as exc:
            self.last_source = "mock"
            self.last_error = str(exc)
            logger.exception("DuckDB read failed; auto/demo mode is falling back to mock ticks")
            return make_mock_ticks()

    def load_ticks_since(self, since_time, overlap_seconds=2):
        if self.mode == "mock":
            return pd.DataFrame()
        if not self.db_path.is_file():
            if self.mode == "duckdb":
                raise DataAccessError(f"DuckDB file not found: {self.db_path}")
            return pd.DataFrame()
        try:
            return self.tick_repository.load_ticks_since(since_time, overlap_seconds)
        except DataAccessError:
            if self.mode == "duckdb":
                raise
            logger.exception("Incremental tick query failed in auto mode")
            return pd.DataFrame()

    def load_market_snapshot(self):
        ticks = self.load_ticks(1000)
        return {"price": float(ticks.price.iloc[-1]) if not ticks.empty else 1877.2}

    def get_data_status(self):
        if self.last_source == "duckdb":
            return f"DuckDB: {self.db_path.name}"
        if self.last_source == "mock":
            return "DỮ LIỆU MÔ PHỎNG (demo/fallback)"
        if self.db_path.exists():
            return f"DuckDB: {self.db_path.name} (chưa tải)"
        return "DỮ LIỆU MÔ PHỎNG (chưa tìm thấy DuckDB)"

    def check_ready(self):
        if self.mode == "mock":
            self.last_source = "mock"
            return True, "mock mode configured"
        try:
            probe = self.tick_repository.load_ticks(limit=1)
            if probe.empty:
                if self.mode == "auto":
                    self.last_source = "mock"
                    self.last_error = "DuckDB table contains no ticks"
                    return True, "demo fallback active: DuckDB table contains no ticks"
                return False, "DuckDB query succeeded but the tick table is empty"
            self.last_source = "duckdb"
            self.last_error = None
            return True, "DuckDB query succeeded"
        except Exception as exc:
            if self.mode == "auto":
                self.last_source = "mock"
                self.last_error = str(exc)
                return True, f"demo fallback active: {exc}"
            return False, str(exc)


market_data_service = MarketDataService()


def load_ticks(limit=None):
    return market_data_service.load_ticks(limit)


def load_ticks_since(since_time, overlap_seconds=2):
    return market_data_service.load_ticks_since(since_time, overlap_seconds)


def load_market_snapshot():
    return market_data_service.load_market_snapshot()


def get_data_status():
    return market_data_service.get_data_status()
