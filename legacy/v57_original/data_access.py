import duckdb
import numpy as np
import pandas as pd
from config import DB_PATH, TABLE_NAME, TICK_LOAD_LIMIT

def load_ticks(limit=None):
    # None uses config.TICK_LOAD_LIMIT; 0 means load all records.
    if limit is None:
        limit = TICK_LOAD_LIMIT
    limit = int(limit)
    limit_sql = f" LIMIT {limit}" if limit > 0 else ""
    if DB_PATH.exists():
        con=None
        try:
            con=duckdb.connect(str(DB_PATH),read_only=True)
            if not TABLE_NAME.replace("_","").isalnum(): raise ValueError("Tên bảng không hợp lệ")
            cols=set(con.execute(f"DESCRIBE {TABLE_NAME}").df()["column_name"])
            if {"DateTime","Price","Volume"}.issubset(cols):
                optional = []
                if "ID" in cols: optional.append("ID AS tick_id")
                if "MarketOrderType" in cols: optional.append("MarketOrderType AS market_order_type")
                extra = (", " + ", ".join(optional)) if optional else ""
                df=con.execute(f"SELECT DateTime AS time, Price AS price, Volume AS volume{extra} FROM {TABLE_NAME} WHERE DateTime IS NOT NULL AND Price IS NOT NULL ORDER BY DateTime DESC{limit_sql}").df()
                con.close()
                if not df.empty:
                    df["time"]=pd.to_datetime(df["time"])
                    return df.sort_values("time").reset_index(drop=True)
        except Exception:
            if con:
                try: con.close()
                except Exception: pass
    return make_mock_ticks()

def load_ticks_since(since_time, overlap_seconds=2):
    """Fetch only recent rows from DuckDB, with a small timestamp overlap."""
    if not DB_PATH.exists() or since_time is None:
        return pd.DataFrame()
    con = None
    try:
        con = duckdb.connect(str(DB_PATH), read_only=True)
        cols = set(con.execute(f"DESCRIBE {TABLE_NAME}").df()["column_name"])
        if not {"DateTime", "Price", "Volume"}.issubset(cols):
            return pd.DataFrame()
        optional = []
        if "ID" in cols: optional.append("ID AS tick_id")
        if "MarketOrderType" in cols: optional.append("MarketOrderType AS market_order_type")
        extra = (", " + ", ".join(optional)) if optional else ""
        since = pd.Timestamp(since_time) - pd.Timedelta(seconds=overlap_seconds)
        df = con.execute(
            f"SELECT DateTime AS time, Price AS price, Volume AS volume{extra} "
            f"FROM {TABLE_NAME} WHERE DateTime >= ? AND DateTime IS NOT NULL AND Price IS NOT NULL ORDER BY DateTime ASC",
            [since.to_pydatetime()]
        ).df()
        if not df.empty:
            df["time"] = pd.to_datetime(df["time"])
            df = df.sort_values("time").reset_index(drop=True)
        return df
    except Exception:
        return pd.DataFrame()
    finally:
        if con is not None:
            try: con.close()
            except Exception: pass


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



def make_mock_ticks(days=4,ticks_per_day=2500):
    rng=np.random.default_rng(42); n=days*ticks_per_day
    times=pd.date_range(end=pd.Timestamp.now().floor("min"),periods=n,freq="10s")
    prices=np.round((1888+np.cumsum(rng.normal(0,.18,n)))*2)/2
    return pd.DataFrame({"time":times,"price":prices,"volume":rng.integers(1,30,n)})

def build_candles(ticks,timeframe="5m"):
    """Aggregate chronologically ordered ticks into candles without renumbering away history.

    The chart controls its visible viewport separately; truncating here would shift
    every X index whenever a new candle arrived and break pan/zoom persistence.
    """
    if ticks is None or ticks.empty:
        return pd.DataFrame(columns=["time","open","high","low","close","volume"])
    rule={"1m":"1min","3m":"3min","5m":"5min","15m":"15min","30m":"30min","1h":"1h","4h":"4h","1D":"1D"}.get(timeframe,"5min")
    df=ticks.loc[:, ["time", "price", "volume"]].copy()
    df["time"] = pd.to_datetime(df["time"])
    df = df.dropna(subset=["time", "price"]).set_index("time")
    # DuckDB loader and replay slices are already chronological; only sort when needed.
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()
    candles = df.resample(rule).agg(
        open=("price", "first"), high=("price", "max"),
        low=("price", "min"), close=("price", "last"),
        volume=("volume", "sum")
    ).dropna().reset_index()
    return candles.reset_index(drop=True)

def load_market_snapshot():
    t=load_ticks(1000)
    return {"price":float(t.price.iloc[-1]) if not t.empty else 1877.2}

def get_data_status():
    return f"DuckDB: {DB_PATH.name}" if DB_PATH.exists() else "DỮ LIỆU MÔ PHỎNG (chưa tìm thấy DuckDB)"
