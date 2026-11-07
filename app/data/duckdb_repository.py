"""DuckDB connection and schema operations."""
import re
from contextlib import contextmanager
from pathlib import Path

import duckdb


class DataAccessError(RuntimeError):
    """Raised when the configured data source cannot be accessed."""


class DuckDBRepository:
    REQUIRED_COLUMNS = {"DateTime", "Price", "Volume"}

    def __init__(self, db_path, table_name):
        self.db_path = Path(db_path)
        self.table_name = str(table_name)
        self._validate_table_name()

    def _validate_table_name(self):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.table_name):
            raise ValueError(f"Invalid DuckDB table identifier: {self.table_name!r}")

    @contextmanager
    def connection(self):
        if not self.db_path.is_file():
            raise DataAccessError(f"DuckDB file not found: {self.db_path}")
        con = None
        try:
            con = duckdb.connect(str(self.db_path), read_only=True)
            yield con
        except DataAccessError:
            raise
        except Exception as exc:
            raise DataAccessError(f"DuckDB operation failed: {exc}") from exc
        finally:
            if con is not None:
                con.close()

    def get_table_columns(self, con=None):
        if con is not None:
            try:
                rows = con.execute(f'DESCRIBE "{self.table_name}"').fetchdf()
                return set(rows["column_name"].tolist())
            except Exception as exc:
                raise DataAccessError(
                    f"Unable to inspect table {self.table_name!r}: {exc}"
                ) from exc
        with self.connection() as conn:
            return self.get_table_columns(conn)

    def validate_schema(self, con=None):
        columns = self.get_table_columns(con)
        missing = self.REQUIRED_COLUMNS - columns
        if missing:
            raise DataAccessError(
                f"Table {self.table_name!r} is missing required columns: {sorted(missing)}"
            )
        return columns
