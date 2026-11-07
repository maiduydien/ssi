"""Deterministic synthetic tick generator for demo mode and tests only."""
import numpy as np
import pandas as pd


def make_mock_ticks(days=4, ticks_per_day=2500):
    rng = np.random.default_rng(42)
    n = int(days) * int(ticks_per_day)
    times = pd.date_range(
        end=pd.Timestamp.now().floor("min"), periods=n, freq="10s"
    )
    prices = np.round((1888 + np.cumsum(rng.normal(0, .18, n))) * 2) / 2
    return pd.DataFrame({
        "time": times,
        "price": prices,
        "volume": rng.integers(1, 30, n),
    })
