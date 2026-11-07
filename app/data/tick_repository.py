"""Tick queries against DuckDB. Returned columns are normalized for the app."""
import pandas as pd

from app.data.duckdb_repository import DataAccessError


class TickRepository:
    def __init__(self, database):
        self.database = database

    @staticmethod
    def _select_columns(columns):
        required = {"DateTime", "Price", "Volume"}
        missing = required - columns
        if missing:
            raise DataAccessError(f"Missing required tick columns: {sorted(missing)}")
        selected = [
            '"DateTime" AS time',
            '"Price" AS price',
            '"Volume" AS volume',
        ]
        if "ID" in columns:
            selected.append('"ID" AS tick_id')
        if "MarketOrderType" in columns:
            selected.append('"MarketOrderType" AS market_order_type')
        return ", ".join(selected)

    @staticmethod
    def _normalize(df):
        if df.empty:
            return df
        df["time"] = pd.to_datetime(df["time"])
        return df.sort_values("time").reset_index(drop=True)

    def load_ticks(self, limit=None):
        if limit is not None:
            limit = int(limit)
            if limit < 0:
                raise ValueError("limit must be >= 0; use 0 for all rows")
        limit_sql = f" LIMIT {limit}" if limit is not None and limit > 0 else ""
        with self.database.connection() as con:
            columns = self.database.validate_schema(con)
            select_sql = self._select_columns(columns)
            sql = (
                f'SELECT {select_sql} FROM "{self.database.table_name}" '
                'WHERE "DateTime" IS NOT NULL AND "Price" IS NOT NULL '
                f'ORDER BY "DateTime" DESC{limit_sql}'
            )
            df = con.execute(sql).fetchdf()
        return self._normalize(df)

    def load_ticks_since(self, since_time, overlap_seconds=2):
        if since_time is None:
            return pd.DataFrame()
        if overlap_seconds < 0:
            raise ValueError("overlap_seconds must be >= 0")
        since = (
            pd.Timestamp(since_time)
            - pd.Timedelta(seconds=float(overlap_seconds))
        )
        with self.database.connection() as con:
            columns = self.database.validate_schema(con)
            select_sql = self._select_columns(columns)
            sql = (
                f'SELECT {select_sql} FROM "{self.database.table_name}" '
                'WHERE "DateTime" >= ? AND "DateTime" IS NOT NULL '
                'AND "Price" IS NOT NULL ORDER BY "DateTime" ASC'
            )
            df = con.execute(sql, [since.to_pydatetime()]).fetchdf()
        return self._normalize(df)
