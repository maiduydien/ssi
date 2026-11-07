"""Compatibility facade for original V57 data_access imports.

New code should import repositories, services and engines directly.
"""
from app.services.market_data_service import (
    load_ticks, load_ticks_since, load_market_snapshot, get_data_status,
)
from app.engines.candle_engine import build_candles
from app.engines.tick_merge_engine import merge_tick_frames
from app.fixtures.mock_data import make_mock_ticks

__all__ = [
    "load_ticks", "load_ticks_since", "merge_tick_frames",
    "make_mock_ticks", "build_candles", "load_market_snapshot",
    "get_data_status",
]
