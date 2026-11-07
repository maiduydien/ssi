"""Tick-to-OHLCV aggregation. Keeps V57's Pandas resampling semantics."""
import pandas as pd

EMPTY_CANDLE_COLUMNS = ["time", "open", "high", "low", "close", "volume"]
TIMEFRAME_RULES = {
    "1m": "1min", "3m": "3min", "5m": "5min", "15m": "15min",
    "30m": "30min", "1h": "1h", "4h": "4h", "1D": "1D",
}


def build_candles(ticks, timeframe="5m"):
    """Aggregate chronologically ordered ticks without changing history indexes."""
    if ticks is None or ticks.empty:
        return pd.DataFrame(columns=EMPTY_CANDLE_COLUMNS)
    rule = TIMEFRAME_RULES.get(timeframe, "5min")
    df = ticks.loc[:, ["time", "price", "volume"]].copy()
    df["time"] = pd.to_datetime(df["time"])
    df = df.dropna(subset=["time", "price"]).set_index("time")
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()
    candles = df.resample(rule).agg(
        open=("price", "first"), high=("price", "max"),
        low=("price", "min"), close=("price", "last"),
        volume=("volume", "sum"),
    ).dropna().reset_index()
    return candles.reset_index(drop=True)
