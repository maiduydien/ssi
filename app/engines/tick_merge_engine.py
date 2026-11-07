"""RAM tick cache merge logic migrated from V57 unchanged."""
import pandas as pd

def merge_tick_frames(existing, incoming, max_rows=None):
    """Append timestamp-ordered incoming ticks efficiently.

    The incremental query starts at the latest existing timestamp, so most polls
    contain only the last timestamp's overlap plus new rows. Keep the large existing
    cache intact and deduplicate only the small incoming/boundary slice.
    """
    if existing is None or existing.empty:
        merged = incoming.copy() if incoming is not None else pd.DataFrame()
        if merged.empty:
            return merged
        merged = merged.sort_values("time").reset_index(drop=True)
        return merged.tail(max_rows).reset_index(drop=True) if max_rows else merged

    if incoming is None or incoming.empty:
        merged = existing
        return merged.tail(max_rows).reset_index(drop=True) if max_rows else merged

    # Maintain the chronological append fast path for the normal live case.
    # `load_ticks()` and this merge function maintain chronological order; avoid
    # rescanning hundreds of thousands of cached timestamps on every live append.
    incoming = incoming.sort_values("time").drop_duplicates(
        subset=["tick_id"] if "tick_id" in incoming.columns and incoming["tick_id"].notna().all()
        else ["time", "price", "volume"], keep="last"
    ).reset_index(drop=True)
    last_time = pd.Timestamp(existing["time"].iloc[-1])
    min_incoming = pd.Timestamp(incoming["time"].iloc[0])

    if min_incoming >= last_time:
        if "tick_id" in existing.columns and "tick_id" in incoming.columns:
            # Only IDs at the overlap timestamp can already exist in a chronological query.
            boundary_start = int(existing["time"].searchsorted(min_incoming, side="left"))
            boundary = existing.iloc[boundary_start:]["tick_id"].dropna()
            known_ids = set(boundary.astype(str).tolist())
            keep = incoming["tick_id"].isna() | ~incoming["tick_id"].astype(str).isin(known_ids)
            append_rows = incoming.loc[keep]
        else:
            boundary_start = int(existing["time"].searchsorted(min_incoming, side="left"))
            boundary = existing.iloc[boundary_start:][["time", "price", "volume"]]
            known_rows = set(map(tuple, boundary.astype({"time": "str"}).to_numpy().tolist()))
            incoming_keys = incoming.loc[:, ["time", "price", "volume"]].copy()
            incoming_keys["time"] = incoming_keys["time"].astype(str)
            keep = [tuple(row) not in known_rows for row in incoming_keys.to_numpy().tolist()]
            append_rows = incoming.loc[keep]
        if append_rows.empty:
            merged = existing
        else:
            merged = pd.concat([existing, append_rows], ignore_index=True, sort=False)
    else:
        # Rare out-of-order insertion: fall back to a complete, correct merge.
        merged = pd.concat([existing, incoming], ignore_index=True, sort=False)
        if "tick_id" in merged.columns and merged["tick_id"].notna().any():
            has_id = merged["tick_id"].notna()
            identified = merged.loc[has_id].drop_duplicates(subset=["tick_id"], keep="last")
            unidentified = merged.loc[~has_id].drop_duplicates(subset=["time", "price", "volume"], keep="last")
            merged = pd.concat([identified, unidentified], ignore_index=True, sort=False)
        else:
            merged = merged.drop_duplicates(subset=["time", "price", "volume"], keep="last")
        merged = merged.sort_values("time").reset_index(drop=True)

    if max_rows is not None:
        merged = merged.tail(max_rows).reset_index(drop=True)
    return merged


