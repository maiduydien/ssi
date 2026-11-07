import pandas as pd

from app.engines.candle_engine import build_candles


def sample_ticks():
    return pd.DataFrame({
        "time": pd.to_datetime([
            "2026-10-01 09:00:01",
            "2026-10-01 09:00:10",
            "2026-10-01 09:00:20",
            "2026-10-01 09:00:45",
        ]),
        "price": [1900.0, 1901.0, 1898.0, 1902.0],
        "volume": [2, 3, 1, 4],
    })


def test_build_one_minute_candle_ohlcv():
    candle = build_candles(sample_ticks(), "1m").iloc[0]
    assert candle["open"] == 1900.0
    assert candle["high"] == 1902.0
    assert candle["low"] == 1898.0
    assert candle["close"] == 1902.0
    assert candle["volume"] == 10


def test_empty_ticks_returns_expected_columns():
    result = build_candles(pd.DataFrame(), "1m")
    assert result.empty
    assert list(result.columns) == ["time", "open", "high", "low", "close", "volume"]


def test_unsorted_ticks_are_sorted_before_aggregation():
    ticks = sample_ticks().iloc[::-1].reset_index(drop=True)
    candle = build_candles(ticks, "1m").iloc[0]
    assert candle["open"] == 1900.0
    assert candle["close"] == 1902.0
