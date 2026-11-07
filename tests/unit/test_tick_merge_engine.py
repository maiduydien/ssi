import pandas as pd

from app.engines.tick_merge_engine import merge_tick_frames


def frame(rows):
    return pd.DataFrame(rows, columns=["time", "price", "volume", "tick_id"])


def test_merge_deduplicates_overlapping_tick_id():
    existing = frame([
        (pd.Timestamp("2026-10-01 09:00:01"), 1900.0, 2, "T1"),
        (pd.Timestamp("2026-10-01 09:00:02"), 1901.0, 3, "T2"),
    ])
    incoming = frame([
        (pd.Timestamp("2026-10-01 09:00:02"), 1901.0, 3, "T2"),
        (pd.Timestamp("2026-10-01 09:00:03"), 1902.0, 1, "T3"),
    ])
    result = merge_tick_frames(existing, incoming)
    assert list(result["tick_id"]) == ["T1", "T2", "T3"]


def test_same_timestamp_price_volume_but_different_ids_are_kept():
    existing = frame([
        (pd.Timestamp("2026-10-01 09:00:01"), 1900.0, 2, "T1"),
    ])
    incoming = frame([
        (pd.Timestamp("2026-10-01 09:00:01"), 1900.0, 2, "T2"),
    ])
    result = merge_tick_frames(existing, incoming)
    assert list(result["tick_id"]) == ["T1", "T2"]
