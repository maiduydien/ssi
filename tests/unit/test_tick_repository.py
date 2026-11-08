import pytest

pytest.importorskip("duckdb")

from app.data.duckdb_repository import DataAccessError, DuckDBRepository  # noqa: E402
from app.data.tick_repository import TickRepository  # noqa: E402
from tests.fixtures.create_test_db import create_test_database  # noqa: E402


@pytest.fixture
def tick_repository(tmp_path):
    db_path = tmp_path / "test.duckdb"
    create_test_database(db_path)
    database = DuckDBRepository(db_path, "vn30f1m_ticks")
    return TickRepository(database)


def test_load_all_ticks(tick_repository):
    df = tick_repository.load_ticks(limit=0)
    assert len(df) == 4
    assert list(df.columns) == ["time", "price", "volume", "tick_id", "market_order_type"]
    assert df["time"].is_monotonic_increasing


def test_limit_selects_latest_ticks_but_returns_chronological(tick_repository):
    df = tick_repository.load_ticks(limit=2)
    assert len(df) == 2
    assert df.iloc[0]["tick_id"] == "A003"
    assert df.iloc[1]["tick_id"] == "A004"


def test_invalid_table_identifier_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        DuckDBRepository(tmp_path / "none.duckdb", "ticks; DROP TABLE x")


def test_missing_database_raises_data_access_error(tmp_path):
    repo = DuckDBRepository(tmp_path / "missing.duckdb", "ticks")
    with pytest.raises(DataAccessError):
        repo.get_table_columns()


def test_load_ticks_since_applies_overlap(tick_repository):
    df = tick_repository.load_ticks_since("2026-10-01 09:00:03", overlap_seconds=1)
    assert list(df["tick_id"]) == ["A002", "A003", "A004"]


def test_missing_table_raises_data_access_error(tmp_path):
    db_path = tmp_path / "empty_schema.duckdb"
    import duckdb

    con = duckdb.connect(str(db_path))
    con.execute("CREATE TABLE unrelated (value INTEGER)")
    con.close()
    repository = TickRepository(DuckDBRepository(db_path, "vn30f1m_ticks"))
    with pytest.raises(DataAccessError):
        repository.load_ticks(limit=1)
