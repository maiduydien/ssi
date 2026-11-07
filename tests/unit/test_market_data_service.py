import pytest

pytest.importorskip("duckdb")

from app.services.market_data_service import MarketDataService  # noqa: E402


def test_mock_mode_is_explicit_and_returns_expected_shape(tmp_path):
    service = MarketDataService(
        db_path=tmp_path / "does-not-exist.duckdb",
        table_name="vn30f1m_ticks",
        mode="mock",
        default_limit=100,
    )
    ticks = service.load_ticks()
    assert len(ticks) == 10000
    assert list(ticks.columns) == ["time", "price", "volume"]
    assert service.last_source == "mock"
    assert service.check_ready() == (True, "mock mode configured")


def test_auto_mode_missing_database_falls_back_with_source_label(tmp_path):
    service = MarketDataService(
        db_path=tmp_path / "missing.duckdb",
        table_name="vn30f1m_ticks",
        mode="auto",
        default_limit=100,
    )
    ticks = service.load_ticks()
    assert not ticks.empty
    assert service.last_source == "mock"
    assert "fallback" in service.get_data_status()
