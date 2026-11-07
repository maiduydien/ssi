from dash import Dash, html, dcc, Input, Output, State, callback_context, no_update, ALL
import plotly.graph_objects as go
import pandas as pd
import time
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from plotly.subplots import make_subplots
from app.services.market_data_service import load_ticks, load_market_snapshot, get_data_status
from app.engines.candle_engine import build_candles
from app.config import APP_TITLE, HOST, PORT, DEBUG, DEFAULT_SYMBOL, TIMEFRAMES, INITIAL_NET_ASSET_VND, MARGIN_PER_CONTRACT_VND, FEE_PER_CONTRACT_VND, POINT_VALUE_VND, DEFAULT_ORDER_SYMBOL, ASSETS_DIR

app = Dash(__name__, title=APP_TITLE, suppress_callback_exceptions=True, assets_folder=str(ASSETS_DIR))


_TICKS_CACHE = None
_TICKS_TIME_INDEX = None
_REPLAY_CANDLE_CACHE = {}
_TIMEFRAME_SWITCH_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="timeframe-switch")
_TIMEFRAME_SWITCH_LOCK = threading.Lock()
_ACTIVE_TIMEFRAME_SWITCH = None
_FULL_CANDLE_CACHE = {}
_CANDLE_CACHE_LOCK = threading.Lock()
_CANDLE_CACHE_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="candle-cache")
_CANDLE_CACHE_PREWARM_FUTURE = None

# Fixed historical back-test data is preloaded once; replay consumes bounded batches from RAM.
REPLAY_BATCH_TICKS = max(100, int(os.getenv("REPLAY_BATCH_TICKS", "10000")))
CHART_REFRESH_SECONDS = max(0.5, float(os.getenv("CHART_REFRESH_SECONDS", "1.25")))


def append_ticks_to_candles(candles, new_ticks, timeframe):
    """Vectorized OHLCV append; avoid Python iteration over thousands of ticks."""
    if new_ticks is None or new_ticks.empty:
        return candles
    batch = build_candles(new_ticks, timeframe)
    if batch.empty:
        return candles
    if candles is None or candles.empty:
        return batch.reset_index(drop=True)

    # The replay cache is chronological. A tick bucket earlier than the final
    # cached candle means another callback changed the cache/timeframe: ask caller
    # to rebuild instead of corrupting OHLCV.
    left = candles.copy().reset_index(drop=True)
    left["time"] = pd.to_datetime(left["time"])
    batch["time"] = pd.to_datetime(batch["time"])
    last_time = pd.Timestamp(left.iloc[-1]["time"])
    first_time = pd.Timestamp(batch.iloc[0]["time"])
    if first_time < last_time:
        return None

    if first_time == last_time:
        # Merge the shared, still-open candle with the new batch's aggregate.
        left_idx = left.index[-1]
        left.at[left_idx, "high"] = max(float(left.at[left_idx, "high"]), float(batch.iloc[0]["high"]))
        left.at[left_idx, "low"] = min(float(left.at[left_idx, "low"]), float(batch.iloc[0]["low"]))
        left.at[left_idx, "close"] = float(batch.iloc[0]["close"])
        left.at[left_idx, "volume"] = float(left.at[left_idx, "volume"] or 0) + float(batch.iloc[0]["volume"] or 0)
        batch = batch.iloc[1:]
    if batch.empty:
        return left
    return pd.concat([left, batch], ignore_index=True).reset_index(drop=True)

def _prewarm_full_candle_cache(ticks):
    """Build immutable full-history candle series off the request thread.

    These aggregates are used only for fully closed candles. The currently open
    candle is always rebuilt from ticks up to the committed replay cursor.
    """
    for tf in ("1m", "5m", "15m", "30m", "1h", "4h", "1D"):
        with _CANDLE_CACHE_LOCK:
            if tf in _FULL_CANDLE_CACHE:
                continue
        try:
            candles = build_candles(ticks, tf)
            with _CANDLE_CACHE_LOCK:
                _FULL_CANDLE_CACHE.setdefault(tf, candles)
        except Exception:
            # A failed prewarm must never stop RUN; timeframe switching has a
            # bounded-window fallback in _candles_for_cursor().
            continue

def _candles_for_cursor(ticks, end_idx, timeframe, display_cutoff, fallback_visible):
    """Get cached closed candles plus a cursor-accurate partial candle."""
    with _CANDLE_CACHE_LOCK:
        full = _FULL_CANDLE_CACHE.get(timeframe)
    if full is None or full.empty or end_idx <= 0:
        return build_candles(fallback_visible, timeframe)

    cursor_time = pd.Timestamp(ticks["time"].iloc[end_idx - 1])
    rule = {"1m":"1min", "3m":"3min", "5m":"5min", "15m":"15min",
            "30m":"30min", "1h":"1h", "4h":"4h", "1D":"1D"}.get(timeframe, "5min")
    bucket_start = cursor_time.floor(rule)
    candle_times = pd.DatetimeIndex(pd.to_datetime(full["time"]))
    # Include the candle whose bucket overlaps the display cutoff.
    cutoff_bucket = pd.Timestamp(display_cutoff).floor(rule)
    left = int(candle_times.searchsorted(cutoff_bucket, side="left"))
    right = int(candle_times.searchsorted(bucket_start, side="left"))
    closed = full.iloc[left:right]

    # Rebuild only the active bucket with ticks actually processed so future ticks
    # contained in the precomputed full-history aggregate never leak into replay.
    start_tick = int(ticks["time"].searchsorted(bucket_start, side="left"))
    start_tick = min(start_tick, end_idx)
    active = build_candles(ticks.iloc[start_tick:end_idx], timeframe) if start_tick < end_idx else pd.DataFrame()
    if closed.empty and active.empty:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
    if closed.empty:
        return active.reset_index(drop=True)
    if active.empty:
        return closed.reset_index(drop=True).copy()
    return pd.concat([closed, active], ignore_index=True).reset_index(drop=True)


def _start_candle_cache_prewarm(ticks):
    global _CANDLE_CACHE_PREWARM_FUTURE
    if ticks is None or ticks.empty:
        return
    with _CANDLE_CACHE_LOCK:
        if _CANDLE_CACHE_PREWARM_FUTURE is None:
            _CANDLE_CACHE_PREWARM_FUTURE = _CANDLE_CACHE_EXECUTOR.submit(_prewarm_full_candle_cache, ticks)


def cached_ticks():
    global _TICKS_CACHE, _TICKS_TIME_INDEX
    if _TICKS_CACHE is None:
        _TICKS_CACHE = load_ticks()
        if _TICKS_CACHE is not None and not _TICKS_CACHE.empty:
            _TICKS_CACHE = _TICKS_CACHE.sort_values("time").reset_index(drop=True)
            # Build the datetime search index once. Rebuilding a DatetimeIndex over
            # millions of ticks on every timeframe selection was the main UI stall.
            _TICKS_TIME_INDEX = pd.DatetimeIndex(pd.to_datetime(_TICKS_CACHE["time"]))
            _start_candle_cache_prewarm(_TICKS_CACHE)
    return _TICKS_CACHE


def refresh_cached_ticks():
    """Compatibility wrapper: fixed back-test data is loaded once and never polled during RUN."""
    return cached_ticks()


def parse_x_range(relayout):
    if not isinstance(relayout, dict): return None
    lo = hi = None
    for axis in ("xaxis", "xaxis2"):
        pair = relayout.get(f"{axis}.range")
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            lo, hi = pair
            break
        lo, hi = relayout.get(f"{axis}.range[0]"), relayout.get(f"{axis}.range[1]")
        if lo is not None and hi is not None: break
    try:
        lo, hi = float(lo), float(hi)
        if pd.notna(lo) and pd.notna(hi) and hi > lo: return [lo, hi]
    except (TypeError, ValueError): pass
    return None

def chart_window_duration(timeframe):
    """Calendar window large enough to supply up to 500 real trading candles.

    Intraday windows deliberately span multiple sessions because overnight and
    weekend gaps contain no candles. A wall-clock window of only 8 hours often
    yields fewer than 500 one-minute candles and makes the chart look truncated.
    """
    return {
        "1m": pd.Timedelta(days=5),
        "5m": pd.Timedelta(days=20),
        "15m": pd.Timedelta(days=45),
        "30m": pd.Timedelta(days=90),
        "1h": pd.Timedelta(days=180),
        "4h": pd.Timedelta(days=365),
        "1D": pd.Timedelta(days=730),
    }.get(timeframe, pd.Timedelta(days=20))


def chart(timeframe="5m", ticks=None, relayout=None, filter_window=True, set_initial_range=False, viewport_range=None, candles_override=None):
    source = None if candles_override is not None else (ticks if ticks is not None else cached_ticks())
    # Filter before OHLCV aggregation to avoid processing the entire tick cache.
    # The window spans enough calendar days to collect up to 500 bars despite
    # sessions, overnight gaps, weekends, and holidays.
    if source is not None and not source.empty:
        source = source.sort_values("time") if not source["time"].is_monotonic_increasing else source
        # Replay callers already pass a fixed history slice. For the full immutable
        # tick cache, search the index built once by cached_ticks(); never allocate a
        # second 20M-row DatetimeIndex on every timeframe switch.
        if filter_window:
            cutoff = pd.to_datetime(source["time"].iloc[-1]) - chart_window_duration(timeframe)
            if source is _TICKS_CACHE and _TICKS_TIME_INDEX is not None:
                start_idx = int(_TICKS_TIME_INDEX.searchsorted(cutoff, side="left"))
            else:
                time_values = pd.DatetimeIndex(pd.to_datetime(source["time"]))
                start_idx = int(time_values.searchsorted(cutoff, side="left"))
            source = source.iloc[start_idx:]
    candles = (candles_override.copy() if candles_override is not None else build_candles(source, timeframe))
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=.025, row_heights=[.72,.28])
    if not candles.empty:
        candles = candles.sort_values("time").reset_index(drop=True)
        # Use sequential positions rather than datetime x-values. Plotly's datetime axis
        # otherwise leaves large visual gaps overnight/weekends when there were no trades.
        xpos = list(range(len(candles)))
        labels = candles["time"].dt.strftime("%d/%m %H:%M:%S").tolist()
        stride = max(1, len(candles) // 8)
        tickvals = list(range(0, len(candles), stride))
        if tickvals[-1] != len(candles)-1:
            tickvals.append(len(candles)-1)
        up = candles.close >= candles.open
        fig.add_trace(go.Candlestick(
            x=xpos, open=candles.open, high=candles.high, low=candles.low, close=candles.close,
            customdata=[[label, pd.Timestamp(ts).isoformat()] for label, ts in zip(labels, candles["time"])],
            hovertemplate="Thời gian: %{customdata[0]}<br>Mở: %{open:.2f}<br>Cao: %{high:.2f}<br>Thấp: %{low:.2f}<br>Đóng: %{close:.2f}<extra></extra>",
            increasing=dict(line=dict(color="#00d2ad", width=1.2), fillcolor="#00c7a2"),
            decreasing=dict(line=dict(color="#ff5365", width=1.2), fillcolor="#f04455"),
            whiskerwidth=0.0, name="VN30F1M", uid=f"candles-{timeframe}"
        ), row=1, col=1)
        fig.add_trace(go.Bar(
            x=xpos, y=candles.volume, width=0.62, customdata=[[label, pd.Timestamp(ts).isoformat()] for label, ts in zip(labels, candles["time"])],
            marker_color=["#087d70" if v else "#9b3545" for v in up],
            hovertemplate="Thời gian: %{customdata[0]}<br>Khối lượng: %{y:,.0f}<extra></extra>",
            name="Khối lượng", uid=f"volume-{timeframe}"
        ), row=2, col=1)
        last_price = float(candles.close.iloc[-1])
        # High-contrast current-price guide and a label on the right edge.
        fig.add_hline(
            y=last_price,
            line_dash="dot",
            line=dict(color="rgba(0,199,162,0.62)", width=1.1),
            opacity=0.82,
            row=1, col=1,
        )
        fig.add_annotation(
            x=1.0, xref="x domain",
            y=last_price, yref="y",
            text=f"{last_price:,.1f}",
            showarrow=False,
            xanchor="left", yanchor="middle",
            xshift=4,
            bgcolor="rgba(0,199,162,0.92)",
            bordercolor="rgba(0,230,184,0.9)",
            borderwidth=1,
            borderpad=3,
            font=dict(color="#06130f", size=10, family="Arial"),
            row=1, col=1,
        )
        fig.update_xaxes(tickmode="array", tickvals=tickvals,
                         ticktext=[labels[i] for i in tickvals], row=2, col=1)
    else:
        fig.add_annotation(text="Không có giao dịch tại hoặc sau thời điểm đã chọn",
                           x=.5, y=.5, xref="paper", yref="paper", showarrow=False)
    fig.update_layout(template="plotly_dark", paper_bgcolor="#08090f", plot_bgcolor="#08090f",
        margin=dict(l=8,r=8,t=5,b=5), height=390, showlegend=False, xaxis_rangeslider_visible=False,
        hovermode="closest", dragmode="pan", bargap=0.32, uirevision=f"price-action-layout-{timeframe}")
    # Axis-specific uirevision is essential here: X values are ordinal candle
    # indexes, so the same numeric range means different candles in different
    # timeframes. Changing timeframe resets both shared X axes; replay refreshes
    # within the same timeframe preserve the user's pan/zoom.
    fig.update_xaxes(uirevision=f"price-action-x-{timeframe}",
                      showgrid=True, gridcolor="#24242e", tickfont=dict(size=10), zeroline=False,
                      showspikes=True, spikesnap="cursor", spikemode="across",
                      spikecolor="rgba(220,225,240,0.55)", spikethickness=1)
    fig.update_yaxes(autorange=True, uirevision=f"price-action-y-{timeframe}", showgrid=True, gridcolor="#24242e", side="right", tickfont=dict(size=10), zeroline=False,
                      showspikes=True, spikesnap="cursor", spikemode="across",
                      spikecolor="rgba(220,225,240,0.75)", spikethickness=1,
                      showline=False)
    # Do not reapply relayoutData on each replay update. Writing a fixed X range
    # into every new figure overrides the pan/zoom state the user just selected.
    # Plotly's stable uirevision preserves the viewport during same-timeframe updates.
    # Set a default range only on initial render or explicit reset/timeframe change.
    if not candles.empty:
        chosen_range = viewport_range
        if chosen_range is None and set_initial_range:
            chosen_range = [max(-0.5, len(candles) - 110 - 0.5), max(0.5, len(candles) - 0.5 + 20)]
        if isinstance(chosen_range, (list, tuple)) and len(chosen_range) == 2:
            xlo, xhi = float(chosen_range[0]), float(chosen_range[1])
            fig.update_xaxes(range=[xlo, xhi], autorange=False, row=1, col=1)
            fig.update_xaxes(range=[xlo, xhi], autorange=False, row=2, col=1)
            # Scale price axis to the actual high/low values inside the visible window.
            # This preserves true OHLC heights and avoids distant, off-screen extremes
            # flattening the candles. The OHLC values themselves are never altered.
            left = max(0, int(xlo // 1))
            right = min(len(candles), int(xhi // 1) + 2)
            visible_candles = candles.iloc[left:right]
            if not visible_candles.empty:
                ymin = float(visible_candles["low"].min())
                ymax = float(visible_candles["high"].max())
                padding = max((ymax - ymin) * 0.04, 0.25)
                if ymax <= ymin:
                    padding = 0.5
                fig.update_yaxes(range=[ymin - padding, ymax + padding], autorange=False, row=1, col=1)
    # Per-timeframe uirevision prevents old ordinal ranges crossing aggregations.
    return fig

def mini_chart(seed, base):
    import numpy as np
    rng=np.random.default_rng(seed); y=base+np.cumsum(rng.normal(0,.7,50))
    f=go.Figure(go.Scatter(x=list(range(50)),y=y,mode="lines",line=dict(color="#f04455",width=1)))
    f.update_layout(template="plotly_dark",paper_bgcolor="#171724",plot_bgcolor="#171724",margin=dict(l=0,r=0,t=0,b=0),
                    height=45,showlegend=False,xaxis_visible=False,yaxis_visible=False)
    return f

def tabs(*labels):
    return html.Div([html.Span(x,className="tab active" if i==0 else "tab") for i,x in enumerate(labels)],className="tabs")

def layout():
    snap=load_market_snapshot()
    book=[]
    sizes=[24,2,1,2,3,17,47,17,8,93]
    for i in range(10):
        p=snap["price"]-i*.1
        book.append(html.Div([html.Span(str(sizes[i])),html.Span(f"{p-.1:.1f}",className="red"),
                              html.Span(f"{p:.1f}",className="green"),html.Span(str(sizes[-i-1]))],className="book-row"))
    return html.Div([
      html.Header([html.Div([html.B("SSI",className="ssi-logo"),html.B("iBoard")],className="brand-area"),
        html.Div([html.B("07:12:22"),html.Span("Hỗ trợ"),html.Span("♧"),html.Span("99+"),html.Span("☾"),html.Span("🇻🇳"),
                  html.Button("♟  Tài khoản Q015168",className="account")],className="header-right")],className="topbar"),
      html.Nav([html.Span(x,className="nav-item"+(" active" if i==3 else "")) for i,x in enumerate([
        "Bảng giá","Thông tin thị trường ⌄","Giao dịch cơ sở ⌄","Giao dịch phái sinh ⌄","Giao dịch tiền ⌄",
        "Quản lý tài sản ⌄","Margin - Vay ký quỹ","Sản phẩm đầu tư ⌄","Dịch vụ & Tiện ích ⌄","Giao diện của tôi"])],className="main-nav"),
      html.Div([
        html.Div([html.Span("BACK-TEST", className="replay-title"),
          dcc.DatePickerSingle(id="replay-date", date=(cached_ticks().time.iloc[-1].date().isoformat() if cached_ticks() is not None and not cached_ticks().empty else None),
                               display_format="DD/MM/YYYY", placeholder="Ngày", className="replay-date"),
          dcc.Dropdown(id="replay-hour", options=[{"label":f"{i:02d}","value":i} for i in range(24)], value=9, clearable=False, searchable=False, className="replay-time"),
          html.Span(":", className="time-colon"),
          dcc.Dropdown(id="replay-minute", options=[{"label":f"{i:02d}","value":i} for i in range(60)], value=0, clearable=False, searchable=False, className="replay-time"),
          html.Span(":", className="time-colon"),
          dcc.Dropdown(id="replay-second", options=[{"label":f"{i:02d}","value":i} for i in range(60)], value=0, clearable=False, searchable=False, className="replay-time"),
          html.Button("▶ RUN", id="run-backtest", n_clicks=0, className="run-button"),
          html.Button("■ STOP", id="stop-backtest", n_clicks=0, className="stop-button", disabled=True),
          html.Div([
              html.Span("Tốc độ", className="replay-speed-label"),
              html.Button("1×", id="speed-1x", n_clicks=0, className="replay-speed-button active"),
               html.Button("2×", id="speed-2x", n_clicks=0, className="replay-speed-button"),
              html.Button("5×", id="speed-5x", n_clicks=0, className="replay-speed-button"),
              html.Button("15×", id="speed-15x", n_clicks=0, className="replay-speed-button"),
              html.Button("30×", id="speed-30x", n_clicks=0, className="replay-speed-button"),
          ], id="replay-speed-controls", className="replay-speed-controls"),
          html.Button("↺ Reset Back-Test", id="reset-backtest", n_clicks=0, className="stop-button reset-backtest-button", title="Xóa lệnh, vị thế, lãi/lỗ và phí; giữ nguyên dữ liệu tick và đường line"),
          html.Span("Chọn ngày/giờ rồi nhấn RUN", id="replay-status", className="replay-status")], className="replay-controls"),
        dcc.Store(id="backtest-result-candidate", data=None),
        dcc.Store(id="replay-state", data=None),
        dcc.Store(id="replay-speed", data=1),
        dcc.Store(id="order-state", storage_type="session", data={"orders": [], "position": None, "realized_gross": 0.0, "fees": 0.0, "last_cursor": 0, "next_id": 1}),
        dcc.Store(id="order-mode-store", data="LIMIT"),
        dcc.Store(id="trade-ui-state", data={"modal": None, "side": None, "order_id": None}),
        dcc.Store(id="edit-order-store", data=None),
        dcc.Store(id="viewport-state", data={"mode":"follow","range":None,"span":110,"timeframe":"5m"}),
        dcc.Interval(id="replay-interval", interval=500, n_intervals=0, disabled=True),
        dcc.Interval(id="timeframe-switch-poll", interval=200, n_intervals=0, disabled=True)
      ], className="replay-bar"),
      html.Main([
        html.Div([
          html.Section([tabs("Biểu đồ","Bảng giá"),
            html.Div([html.B("⌕  VN30F1M"),html.Button("+"),dcc.Dropdown(id="timeframe", options=[{"label":t,"value":t} for t in TIMEFRAMES],
              value="5m", clearable=False, searchable=False, className="timeframe-native",
              persistence=True, persistence_type="memory"),html.Span("", id="timeframe-switch-indicator", className="timeframe-switch-indicator", role="status", **{"aria-live":"polite"}), html.Button("Về nến mới nhất", id="follow-latest", n_clicks=0, className="follow-latest-button"),
              html.Span("Line:", className="draw-label"),
              html.Select([html.Option("Liền", value="solid", selected=True),html.Option("Đứt", value="dash"),html.Option("Chấm", value="dot"),html.Option("Gạch-chấm", value="dashdot")], id="line-style", className="draw-select", title="Kiểu đường"),
              dcc.Input(id="line-color", type="color", value="#ffd166", className="draw-color"),
              html.Select([html.Option("1 px", value="1"),html.Option("2 px", value="2", selected=True),html.Option("3 px", value="3"),html.Option("4 px", value="4"),html.Option("5 px", value="5")], id="line-width", className="draw-select draw-width", title="Độ dày"),
              html.Button("／", id="draw-line-toggle", n_clicks=0, className="draw-line-button icon-only", title="Vẽ line"),
              html.Button("🗑", id="delete-line", n_clicks=0, className="draw-delete-button icon-only", title="Xóa line đang chọn"),
              html.Span("♧"),html.Span("ƒx  Các chỉ báo"),html.Span("▦"),html.Span("↶"),html.Span("↷"),html.Span("Lưu",className="save")],className="chart-toolbar"),
            dcc.Graph(
              id="price-chart",
              figure=chart(set_initial_range=True),
              config={
                "displayModeBar": True,
                "displaylogo": False,
                "modeBarButtonsToAdd": ["drawline", "eraseshape"],
                "scrollZoom": True,
                "doubleClick": "reset",
                "edits": {"shapePosition": True, "annotationPosition": True},
                "modeBarButtonsToRemove": ["lasso2d", "select2d"],
              },
            ),
            html.Div([html.Span(x) for x in ["1d","5d","1m","3m","6m","1y","5y","All"]]+[
              html.Span("--:--:-- (UTC+7)", id="chart-clock", className="push-right"),html.Span("%"),html.Span("log"),html.Span("tự động")],className="chart-footer")],className="chart-panel"),
          html.Section([tabs("Số lệnh","Số lệnh điều kiện","Danh mục","Tài sản"),
            html.Div([dcc.Dropdown(options=[{"label":"Q015168 - MAI D...","value":"a"}],value="a",clearable=False),
              dcc.Dropdown(options=[{"label":"Long/Short","value":"all"}],value="all",clearable=False),
              dcc.Dropdown(options=[{"label":"Tất cả","value":"all"}],value="all",clearable=False),
              dcc.Input(placeholder="Tìm kiếm CK"),html.Span("● Connected",className="connected"),html.Button("▤ Xuất dữ liệu",className="flat-btn")],className="orders-filters"),
            html.Div([html.Div([html.Span(x) for x in ["Mã CK","Long/Short","KL đặt","Giá đặt","KL khớp","Giá khớp TB","Trạng thái","Sửa/Hủy"]],className="orders-head order-head-v13"),
              html.Div(id="orders-list", children=html.Div("Chưa có lệnh",className="empty-orders")),
              html.Div([html.Span("Tổng lệnh"),html.Span("0",id="order-count",className="total")],className="orders-bottom")],className="orders-table")],className="orders-panel")
        ],className="left-column"),
        html.Div([tabs("Độ sâu thị trường","Khớp lệnh"),html.Div([html.B("⌕  4111G9000"),html.B(f"{snap['price']:,.1f} (-3.00 -0.16%)",className="red")],className="book-symbol"),
          html.Div([html.Span("KL"),html.Span("Giá mua"),html.Span("Giá bán"),html.Span("KL")],className="book-head"),html.Div(book),
          html.Div([html.Span("Dư mua: 2,567"),html.Span("Dư bán: 7,202")],className="book-summary"),
          html.Section([tabs("Tài sản"),
            html.Div([html.Span("Tổng tài sản ròng"),html.B(id="asset-net", children=f"{INITIAL_NET_ASSET_VND:,.0f} ₫")],className="metric"),
            html.Div([html.Span("Tiền có thể rút"),html.B(id="asset-withdrawable", children="0 ₫")],className="metric"),
            html.Div([html.Span("Tổng lãi lỗ"),html.B(id="asset-pnl", children="0 ₫")],className="metric"),
            html.Div([html.Span("Tổng phí thuế"),html.B(id="asset-fees", children="0 ₫")],className="metric"),html.Hr(),
            html.Div([html.Span("Tỷ lệ sử dụng TSKQ SSI | VSDC (%)"),html.B("- | -")],className="metric")],className="assets-panel")],className="middle-column"),
        html.Div([html.Div([html.Div([html.Div([html.Span("VNINDEX"),html.Span("▼ 1,735.09 (-0.22%)",className="red")]),
          dcc.Graph(figure=mini_chart(3,1735),config={"displayModeBar":False})],className="mini-card"),
          html.Div([html.Div([html.Span("VN30"),html.Span("▼ 1,873.43 (-0.19%)",className="red")]),
          dcc.Graph(figure=mini_chart(7,1873),config={"displayModeBar":False})],className="mini-card")],className="mini-charts"),
          html.Section([html.H4("Đặt lệnh"),html.Div("ϟ  Tăng sức mua                         ✓ Đã kích hoạt   ›",className="buying-power"),
          html.Div([html.B(f"⌕  {DEFAULT_ORDER_SYMBOL}"),html.Span(f"{snap['price']:,.1f} (-3.00 -0.16%)",className="red"),
            html.Span("2,011.8",className="blue"),html.Span("1,880.2",className="yellow")],className="contract-line"),
          html.Div("HĐTL VN30 đáo hạn 15/10/2026",className="muted"),
          html.Div([html.Span("HĐ lệch  +3.77"),html.Span("Tổng KL 273,544"),html.Span("● Phiên trước giờ")],className="contract-meta"),
          html.Div([html.Span(id="max-open-qty", children="KL tối đa 0 HĐ"),html.Span(id="buying-power-display", children="Sức mua 0 ₫")],className="buy-sell-limit"),
          html.Div([html.Button("Lệnh thường",className="order-tab selected"),html.Button("Lệnh điều kiện",className="order-tab"),html.Button("⚙")],className="order-tabs"),
          html.Div([html.Label("Khối lượng"),html.Div([
            html.Div([html.Button(x, id=f"qty-preset-{x}", n_clicks=0, className="qty-preset") for x in ["1","5","10","20"]],
                     className="quantity-presets"),
            html.Div([dcc.Input(id="custom-quantity", type="number", min=1, step=1, value=2, debounce=True,
                                className="custom-quantity", inputMode="numeric"),
                      html.Button("−", id="qty-minus", n_clicks=0, className="qty-step"),
                      html.Button("+", id="qty-plus", n_clicks=0, className="qty-step")], className="custom-quantity-box")
          ],className="quantity-control"),
          html.Div([html.Div(id="position-summary", children="Chưa có vị thế mở", className="position-summary"),
            html.Div([html.Button("Đảo chiều", id="position-reverse", n_clicks=0, className="modal-secondary"), html.Button("Đóng", id="position-close", n_clicks=0, className="modal-primary")], className="position-actions")], className="inline-position"),
          html.Div(id="quantity-validation", children="KL phải nhỏ hơn hoặc bằng KL tối đa", className="quantity-validation")],className="field-row quantity-field"),
          html.Div([html.Label("Giá"),html.Div([dcc.Input(value=None,id="order-price", type="number", placeholder="Giá đặt"),html.Button("−",id="price-minus",n_clicks=0),html.Button("+",id="price-plus",n_clicks=0),html.Button("AUTO",id="auto-mode-toggle",n_clicks=0,className="auto-mode-button")],className="price-row")],className="field-row"),
          html.Div([html.Label("Loại lệnh"),html.Div([
            html.Button(x, id=f"order-type-{x.lower()}", n_clicks=0, className="order-type-btn" + (" selected" if x=="MTL" else ""))
            for x in ["ATO","ATC","MTL","MOK","MAK"]
          ],className="order-type-row")],className="field-row order-type-field"),
          html.Div([html.Label("Kiểu xác thực"),html.Div([html.Span("Smart OTP"),dcc.Checklist(options=[{"label":"Lưu xác thực","value":"yes"}],value=["yes"],inline=True),
            dcc.Dropdown(options=[{"label":"8 Giờ","value":"8h"}],value="8h",clearable=False)],className="auth-row")],className="field-row"),
          html.Div([html.Button("Long",id="long-btn",className="long-btn"),html.Button("Short",id="short-btn",className="short-btn")],className="trade-buttons"),
          html.Div(id="trade-feedback",className="trade-feedback")],className="order-entry")],className="right-column")
      ],className="workspace"),
      dcc.ConfirmDialog(id="quantity-required-dialog", message="Vui lòng nhập khối lượng hợp lệ trước khi đặt lệnh."),
      html.Div([html.Div([html.H4(id="market-confirm-title", children="Xác nhận lệnh thị trường"),
        html.Div([html.Span("Giá hiện tại: "),html.B(id="market-confirm-price", children="Đang chờ giá replay…")],className="modal-price"),
        html.Div([html.Button("Quay lại",id="market-cancel",n_clicks=0,className="modal-secondary"),html.Button("Xác nhận",id="market-confirm",n_clicks=0,className="modal-primary")],className="modal-actions")],className="trade-modal-card")],id="market-modal",className="trade-modal-overlay",style={"display":"none"}),
      html.Div([html.Div([html.H4("Sửa lệnh chờ khớp"),
        html.Label("Mã CK"),dcc.Input(id="edit-symbol",value=DEFAULT_ORDER_SYMBOL,disabled=True),
        html.Label("Loại lệnh"),dcc.Dropdown(id="edit-side",options=[{"label":"LONG","value":"LONG"},{"label":"SHORT","value":"SHORT"}],clearable=False),
        html.Label("Khối lượng"),dcc.Input(id="edit-quantity",type="number",min=1,step=1),
        html.Label("Giá đặt"),dcc.Input(id="edit-price",type="number"),
        html.Div([html.Button("Đóng",id="edit-cancel",n_clicks=0,className="modal-secondary"),html.Button("Lưu thay đổi",id="edit-save",n_clicks=0,className="modal-primary")],className="modal-actions")],className="trade-modal-card edit-modal-card")],id="edit-modal",className="trade-modal-overlay",style={"display":"none"}),
      html.Div([html.Div([html.H4(id="position-action-title", children="Đóng vị thế"),
        html.Div([html.Span("Giá thực hiện: "), dcc.Input(id="position-action-price", type="number", min=0, step=0.1)], className="modal-price"),
        html.Div("Giá nhập là giá kích hoạt; hành động sẽ được đưa vào hàng chờ và thực hiện khi replay chạm giá.", className="muted"),
        html.Div([html.Button("Hủy", id="position-action-cancel", n_clicks=0, className="modal-secondary"), html.Button("Xác nhận", id="position-action-confirm", n_clicks=0, className="modal-primary")], className="modal-actions")], className="trade-modal-card")], id="position-action-modal", className="trade-modal-overlay", style={"display":"none"}),
      html.Footer([html.Span("SSI iBoard • Giao diện mô phỏng phục vụ nghiên cứu/back-test"),
        html.Span("Nguồn dữ liệu: "+get_data_status(),className="push-right")],className="app-footer"),
    ],className="app-shell")

app.layout=layout

def history_duration(timeframe):
    """Historical context for replay, aligned with the chart's candle window."""
    return chart_window_duration(timeframe)


def candle_bucket_key(timestamp, timeframe):
    """Return the time bucket of a tick; used to avoid redrawing an unchanged candle."""
    if timestamp is None or pd.isna(timestamp):
        return None
    rule = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
            "1h": "1h", "4h": "4h", "1D": "1D"}.get(timeframe, "5min")
    return pd.Timestamp(timestamp).floor(rule).isoformat()


def latest_bucket_for_slice(ticks, end_idx, timeframe):
    if end_idx <= 0 or ticks is None or ticks.empty:
        return None
    return candle_bucket_key(ticks["time"].iloc[end_idx - 1], timeframe)


def replay_clock(state):
    """Simulated time from a wall-clock anchor and selectable playback speed."""
    if not state or not state.get("start_time"):
        return None
    anchor_wall = float(state.get("speed_anchor_wall", state.get("wall_start", time.time())))
    anchor_sim = pd.Timestamp(state.get("speed_anchor_sim", state["start_time"]))
    speed = max(1.0, float(state.get("speed", 1.0) or 1.0))
    elapsed = max(0.0, time.time() - anchor_wall) * speed
    return anchor_sim + pd.to_timedelta(elapsed, unit="s")


def clock_label(value):
    return value.strftime("%H:%M:%S (UTC+7)") if value is not None else "--:--:-- (UTC+7)"


def resolve_replay_start(times_index, requested_time):
    """
    Pick the first stored tick at/after the requested time.
    If the request is beyond the newest loaded tick, fall back to the newest available tick
    instead of returning an empty-chart/no-trades error.
    """
    idx = int(times_index.searchsorted(requested_time, side="left"))
    used_fallback = False
    if idx >= len(times_index):
        idx = len(times_index) - 1
        used_fallback = True
    actual_time = pd.Timestamp(times_index[idx])
    return idx, actual_time, used_fallback


@app.callback(
    Output("viewport-state", "data"),
    Input("price-chart", "relayoutData"),
    Input("follow-latest", "n_clicks"),
    Input("timeframe", "value"),
    Input("run-backtest", "n_clicks"),
    Input("stop-backtest", "n_clicks"),
    State("viewport-state", "data"),
    State("price-chart", "figure"),
    prevent_initial_call=True,
)
def update_viewport_state(relayout, follow_clicks, timeframe, run_clicks, stop_clicks, current, figure):
    """Keep pan/zoom state separate from replay state to prevent callback races."""
    current = dict(current or {"mode": "follow", "range": None, "span": 110})
    trigger = callback_context.triggered_id
    span = max(10, min(1000, int(current.get("span", 110) or 110)))

    if trigger == "follow-latest":
        return {"mode": "follow", "range": None, "span": span, "timeframe": timeframe or "5m"}
    if trigger == "run-backtest":
        # RUN starts replay but must not force Follow Latest. Preserve the
        # browser viewport like Manual View; Follow Latest remains an explicit action.
        return {"mode": "manual", "range": None, "span": span, "timeframe": timeframe or "5m"}
    if trigger == "timeframe":
        # Candle X coordinates are ordinal and differ by timeframe. Drop the old
        # numeric range, but preserve the user's viewing mode (Manual/Follow).
        # The replay callback will seed a fresh range for the new aggregation.
        mode = current.get("mode", "manual")
        return {"mode": mode, "range": None, "span": span, "timeframe": timeframe or "5m"}
    if trigger == "stop-backtest":
        return {"mode": "follow", "range": None, "span": 110, "timeframe": timeframe or "5m"}

    if trigger == "price-chart" and isinstance(relayout, dict):
        # Double-click/autorange means return to Follow Latest.
        if relayout.get("xaxis.autorange") is True or relayout.get("xaxis2.autorange") is True:
            return {"mode": "follow", "range": None, "span": span, "timeframe": timeframe or "5m"}

        new_range = parse_x_range(relayout)
        if new_range is None:
            return current

        # Ignore a relayout that merely echoes the range already authored into
        # the latest figure. A user's pan/zoom differs from this server range.
        expected = None
        try:
            layout = (figure or {}).get("layout", {})
            axis = layout.get("xaxis", {}) if isinstance(layout, dict) else {}
            value = axis.get("range") if isinstance(axis, dict) else None
            if isinstance(value, (list, tuple)) and len(value) == 2:
                expected = [float(value[0]), float(value[1])]
        except (TypeError, ValueError, AttributeError):
            expected = None
        if expected and abs(expected[0] - new_range[0]) < 0.01 and abs(expected[1] - new_range[1]) < 0.01:
            return current

        new_span = max(10, min(1000, new_range[1] - new_range[0]))
        return {"mode": "manual", "range": new_range, "span": new_span, "timeframe": timeframe or "5m"}

    return current


@app.callback(
    Output("replay-speed", "data"),
    Output("speed-1x", "className"), Output("speed-2x", "className"),
    Output("speed-5x", "className"), Output("speed-15x", "className"),
    Output("speed-30x", "className"),
    Input("speed-1x", "n_clicks"), Input("speed-2x", "n_clicks"),
    Input("speed-5x", "n_clicks"), Input("speed-15x", "n_clicks"),
    Input("speed-30x", "n_clicks"),
    State("replay-speed", "data"), prevent_initial_call=True)
def choose_replay_speed(n1, n2, n5, n15, n30, current_speed):
    selected = {"speed-1x": 1, "speed-2x": 2, "speed-5x": 5, "speed-15x": 15, "speed-30x": 30}
    trigger = callback_context.triggered_id
    speed = selected.get(trigger, current_speed or 1)
    classes = {key: ("replay-speed-button active" if key == trigger or (trigger is None and int(speed) == value)
                     else "replay-speed-button") for key, value in selected.items()}
    return speed, classes["speed-1x"], classes["speed-2x"], classes["speed-5x"], classes["speed-15x"], classes["speed-30x"]


def figure_payload(timeframe, figure):
    if figure is no_update:
        return no_update
    return {"timeframe": timeframe, "figure": figure.to_plotly_json() if hasattr(figure, "to_plotly_json") else figure}


app.clientside_callback(
    """function(candidate, selectedTimeframe, currentState) {
        const noUpdate = window.dash_clientside.no_update;
        const selectedTf = selectedTimeframe || '5m';
        const browserTriggers = (window.dash_clientside.callback_context &&
            window.dash_clientside.callback_context.triggered) || [];
        const timeframeChanged = browserTriggers.some(t => t && t.prop_id === 'timeframe.value');

        // Pause the replay interval synchronously in the browser as soon as the user
        // changes timeframe. The server will rebuild candles from the last committed
        // cursor; only its accepted timeframe response may re-enable the interval.
        // This branch intentionally does not modify replay-state or the trade engine.
        const matchingSwitchResponse = candidate && candidate.timeframe === selectedTf &&
            Array.isArray(candidate.outputs) && (candidate.trigger === 'timeframe' || candidate.trigger === 'timeframe-complete');
        if (timeframeChanged && currentState && currentState.running && !matchingSwitchResponse) {
            return [noUpdate, noUpdate, 'Đang chuyển khung thời gian…', true,
                    noUpdate, noUpdate, noUpdate, noUpdate, noUpdate, noUpdate, noUpdate];
        }

        if (!candidate || candidate.timeframe !== selectedTf || !Array.isArray(candidate.outputs)) {
            return Array(11).fill(noUpdate);
        }
        const trigger = candidate.trigger;
        const vals = candidate.outputs;
        const decode = v => (v && v.__no_update__ === true) ? noUpdate : v;
        const next = (vals[1] && vals[1].__no_update__ === true) ? currentState : vals[1];

        // Reject an older interval result if RUN has stopped, the timeframe changed,
        // the session changed, the cursor regressed, or the speed anchor was replaced.
        if (trigger === 'replay-interval') {
            if (!currentState || !currentState.running || !next || !next.running) return Array(11).fill(noUpdate);
            // If the browser selection and committed state differ, only the explicit
            // timeframe-triggered response may complete the switch. A queued interval
            // request must never impersonate that response.
            if (currentState.timeframe !== selectedTf) return Array(11).fill(noUpdate);
            if (next.timeframe !== selectedTf) return Array(11).fill(noUpdate);
            const sameSession = currentState.replay_session_key === next.replay_session_key;
            if (sameSession && Number(next.cursor || 0) < Number(currentState.cursor || 0)) return Array(11).fill(noUpdate);
            if (sameSession && (Number(next.speed || 1) !== Number(currentState.speed || 1) ||
                Number(next.speed_anchor_wall || 0) !== Number(currentState.speed_anchor_wall || 0))) return Array(11).fill(noUpdate);
        }
        // A request that began before RUN/STOP must not undo the newer lifecycle state.
        if (currentState && currentState.running && (!next || !next.running) && trigger !== 'stop-backtest') return Array(11).fill(noUpdate);
        if ((!currentState || !currentState.running) && next && next.running && trigger !== 'run-backtest' && trigger !== 'timeframe') {
            if (trigger !== 'follow-latest') return Array(11).fill(noUpdate);
        }
        if (next && next.running && next.timeframe !== selectedTf) return Array(11).fill(noUpdate);
        if (currentState && currentState.running && next && next.running && trigger !== 'run-backtest') {
            if (currentState.replay_session_key !== next.replay_session_key) return Array(11).fill(noUpdate);
            if (Number(next.cursor || 0) < Number(currentState.cursor || 0)) return Array(11).fill(noUpdate);
        }

        // Commit the chart, replay state, interval switch, status and controls together.
        // This prevents a late response from disabling the interval after RUN or restoring stale controls.
        const figurePayload = vals[0];
        let figure = noUpdate;
        if (figurePayload && figurePayload.__no_update__ !== true && figurePayload.timeframe === selectedTf && figurePayload.figure) {
            figure = figurePayload.figure;
        }
        return [figure, decode(vals[1]), decode(vals[2]), decode(vals[3]), decode(vals[4]),
                decode(vals[5]), decode(vals[6]), decode(vals[7]), decode(vals[8]), decode(vals[9]), decode(vals[10])];
    }""",
    Output("price-chart", "figure"),
    Output("replay-state", "data"),
    Output("replay-status", "children"),
    Output("replay-interval", "disabled"),
    Output("chart-clock", "children"),
    Output("replay-date", "disabled"),
    Output("replay-hour", "disabled"),
    Output("replay-minute", "disabled"),
    Output("replay-second", "disabled"),
    Output("run-backtest", "disabled"),
    Output("stop-backtest", "disabled"),
    Input("backtest-result-candidate", "data"),
    Input("timeframe", "value"),
    State("replay-state", "data"),
    prevent_initial_call=True,
)


def _drive_backtest_impl(run_clicks, stop_clicks, interval_n, selected_speed, timeframe, follow_clicks, selected_date, hour, minute, second, state, viewport, chart_relayout, trigger_override=None):
    trigger = trigger_override or callback_context.triggered_id
    tf = timeframe or "5m"
    # The back-test dataset is immutable for this session. Load once into the process
    # cache, then all replay/timeframe/order processing reads the same in-memory frame.
    ticks = cached_ticks()

    if ticks is None or ticks.empty:
        return (figure_payload(tf, chart(tf, ticks, set_initial_range=True)), None, "Không có dữ liệu tick trong DuckDB.", True,
                "--:--:-- (UTC+7)", False, False, False, False, False, True)

    times_index = ticks["time"]  # pandas searchsorted is O(log N); do not rebuild a 500k-row DatetimeIndex every poll

    def controls(running):
        # Lock date/time and RUN while replay is active; STOP is the only way to end it.
        return (running, running, running, running, running, not running)

    if trigger == "run-backtest":
        if not selected_date:
            return (figure_payload(tf, chart(tf, ticks, set_initial_range=True)), None, "Hãy chọn ngày bắt đầu.", True,
                    "--:--:-- (UTC+7)", False, False, False, False, False, True)
        try:
            requested_time = pd.Timestamp(
                f"{selected_date} {int(hour or 0):02d}:{int(minute or 0):02d}:{int(second or 0):02d}"
            )
        except Exception:
            return (figure_payload(tf, chart(tf, ticks, set_initial_range=True)), None, "Thời gian không hợp lệ.", True,
                    "--:--:-- (UTC+7)", False, False, False, False, False, True)

        replay_idx, actual_start, used_fallback = resolve_replay_start(times_index, requested_time)
        history_idx = int(times_index.searchsorted(actual_start - history_duration(tf), side="left"))
        replay_key = f"{time.time_ns()}:{tf}"
        state = {
            "running": True,
            "replay_key": replay_key,
            "replay_session_key": replay_key.split(":", 1)[0],
            "history_idx": history_idx,
            "replay_idx": replay_idx,
            "cursor": replay_idx,
            "start_time": actual_start.isoformat(),
            "requested_time": requested_time.isoformat(),
            "timeframe": tf,
            "wall_start": time.time(),
            "speed": max(1.0, float(selected_speed or 1.0)),
            "speed_anchor_wall": time.time(),
            "speed_anchor_sim": actual_start.isoformat(),
            "used_fallback": used_fallback,
            "last_chart_bucket": latest_bucket_for_slice(ticks, replay_idx, tf),
            "last_chart_update_wall": time.monotonic(),
            # RUN replay behaves like Manual View: new ticks update candles
            # without moving the user's X viewport to the newest candle.
            "viewport_mode": "manual",
            "viewport_range": None,
            "viewport_span": max(10, min(1000, int((viewport or {}).get("span", 110) or 110))),
        }
        visible = ticks.iloc[history_idx:replay_idx]
        initial_candles = build_candles(visible, tf)
        _REPLAY_CANDLE_CACHE[replay_key] = initial_candles
        initial_span = max(10, min(1000, int((viewport or {}).get("span", 110) or 110)))
        stored_view_range = (viewport or {}).get("range")
        if (viewport or {}).get("mode") == "manual" and isinstance(stored_view_range, (list, tuple)) and len(stored_view_range) == 2:
            initial_range = [float(stored_view_range[0]), float(stored_view_range[1])]
        else:
            initial_range = [max(-0.5, len(initial_candles) - initial_span - 0.5), max(0.5, len(initial_candles) - 0.5 + 20)]
        state["viewport_range"] = initial_range
        if used_fallback:
            status = (
                f"Không có tick sau mốc đã chọn; bắt đầu từ tick gần nhất trong dữ liệu: "
                f"{actual_start:%d/%m/%Y %H:%M:%S}"
            )
        else:
            status = (
                f"Back-Test đang chạy • lịch sử {history_duration(tf)} • "
                f"bắt đầu {actual_start:%d/%m/%Y %H:%M:%S}"
            )
        return (figure_payload(tf, chart(tf, visible, None, filter_window=False, set_initial_range=False, viewport_range=initial_range, candles_override=initial_candles)), state, status, False, clock_label(actual_start),
                True, True, True, True, True, False)

    if trigger == "follow-latest":
        if state and state.get("running"):
            hist = int(state.get("history_idx", 0))
            end = min(int(state.get("cursor", len(ticks))), len(ticks))
            visible = ticks.iloc[hist:end]
            replay_key = state.get("replay_key")
            replay_candles = _REPLAY_CANDLE_CACHE.get(replay_key)
            if replay_candles is None:
                replay_candles = build_candles(visible, tf)
                _REPLAY_CANDLE_CACHE[replay_key] = replay_candles
            count = len(replay_candles)
            span = max(10, min(1000, int((viewport or {}).get("span", state.get("viewport_span", 110)) or 110)))
            view_range = [max(-0.5, count - span - 0.5), max(0.5, count - 0.5 + 20)]
            new_state = {**state, "viewport_mode": "follow", "viewport_range": view_range, "viewport_span": span}
            return (figure_payload(tf, chart(tf, visible, None, filter_window=False, set_initial_range=False, viewport_range=view_range, candles_override=replay_candles)),
                    new_state, "Đang theo dõi nến mới nhất", False, no_update,
                    True, True, True, True, True, False)
        return (figure_payload(tf, chart(tf, ticks, None, set_initial_range=True)), state, "Đã đưa biểu đồ về nến mới nhất", True,
                no_update, False, False, False, False, False, True)

    if trigger == "stop-backtest":
        # Stop explicitly and reset the chart to the historical context around the selected start.
        try:
            requested_time = pd.Timestamp(
                f"{selected_date} {int(hour or 0):02d}:{int(minute or 0):02d}:{int(second or 0):02d}"
            )
            replay_idx, actual_start, used_fallback = resolve_replay_start(times_index, requested_time)
            history_idx = int(times_index.searchsorted(actual_start - history_duration(tf), side="left"))
            visible = ticks.iloc[history_idx:replay_idx]
            message = f"Đã STOP • biểu đồ đặt lại trước {actual_start:%d/%m/%Y %H:%M:%S}"
            if used_fallback:
                message += " • mốc chọn nằm sau tick mới nhất trong DB"
            return (figure_payload(tf, chart(tf, visible, None, filter_window=False, set_initial_range=True)), None, message, True, clock_label(actual_start),
                    False, False, False, False, False, True)
        except Exception:
            return (figure_payload(tf, chart(tf, ticks, None, set_initial_range=True)), None, "Đã STOP • chọn lại thời gian để chạy tiếp.", True,
                    "--:--:-- (UTC+7)", False, False, False, False, False, True)

    if trigger == "replay-speed":
        new_speed = max(1.0, float(selected_speed or 1.0))
        if state and state.get("running"):
            now = time.time()
            current_sim = replay_clock(state)
            next_state = {**state, "speed": new_speed,
                          "speed_anchor_wall": now,
                          "speed_anchor_sim": current_sim.isoformat() if current_sim is not None else state["start_time"]}
            return (no_update, next_state, f"Back-Test đang chạy • tốc độ {int(new_speed)}×", no_update, no_update,
                    no_update, no_update, no_update, no_update, no_update, no_update)
        return (no_update, state, f"Đã chọn tốc độ {int(new_speed)}× • nhấn RUN để bắt đầu", no_update, no_update,
                no_update, no_update, no_update, no_update, no_update, no_update)

    # A timeframe change can overlap a replay-interval request. Compare the
    # selected timeframe with replay-state as well as checking triggered_id, so
    # an interval callback cannot append old-timeframe candles after the switch.
    if trigger == "timeframe" or (state and state.get("running") and state.get("timeframe") != tf):
        if state and state.get("running"):
            actual_start = pd.Timestamp(state["start_time"])
            replay_idx = int(state.get("replay_idx", times_index.searchsorted(actual_start, side="left")))
            sim_now = replay_clock(state)
            # Keep the actually processed cursor authoritative. At 15x/30x the
            # simulated clock can run ahead of batch processing; never jump cursor.
            end_idx = max(replay_idx, min(int(state.get("cursor", replay_idx)), len(ticks)))

            # Aggregate only the recent display window around the processed cursor.
            # Rebuilding from the original start can process millions of ticks and
            # block the UI during a timeframe change at high replay speeds.
            if end_idx > 0:
                cursor_time = pd.Timestamp(ticks["time"].iloc[end_idx - 1])
                display_cutoff = cursor_time - chart_window_duration(tf)
                history_idx = int(times_index.searchsorted(display_cutoff, side="left"))
            else:
                history_idx = max(0, replay_idx - 1)
            visible = ticks.iloc[history_idx:end_idx]
            replay_candles = _candles_for_cursor(ticks, end_idx, tf, display_cutoff if end_idx > 0 else pd.Timestamp(ticks["time"].iloc[0]), visible)
            # Cache key must include timeframe. Concurrent interval requests may
            # still be finishing for the previous timeframe; isolating caches keeps
            # those responses from corrupting the newly aggregated candle series.
            replay_session = state.get("replay_session_key") or state.get("replay_key") or str(time.time_ns())
            replay_key = f"{replay_session}|{tf}"
            _REPLAY_CANDLE_CACHE[replay_key] = replay_candles
            # Switching timeframe changes ordinal candle indexes. Preserve Manual
            # versus Follow mode, but never reuse the old timeframe's X range.
            # Seed a fresh range around the current end; if the user was in Manual,
            # this becomes a fixed viewport and later ticks must not push it right.
            old_mode = state.get("viewport_mode") or (viewport or {}).get("mode", "manual")
            if (viewport or {}).get("timeframe") == tf:
                old_mode = (viewport or {}).get("mode", old_mode)
            old_mode = "follow" if old_mode == "follow" else "manual"
            span = max(10, min(1000, int((viewport or {}).get("span", state.get("viewport_span", 110)) or 110)))
            candle_count = len(replay_candles)
            fresh_range = [max(-0.5, candle_count - span - 0.5), max(0.5, candle_count - 0.5 + 20)]
            switch_completed_wall = time.time()
            frozen_sim_time = sim_now.isoformat() if sim_now is not None else state.get("speed_anchor_sim", state["start_time"])
            next_state = {**state, "replay_key": replay_key, "history_idx": history_idx, "replay_idx": replay_idx,
                          "cursor": end_idx, "timeframe": tf, "running": True,
                          # Freeze the simulation clock while the chart was being rebuilt.
                          # The next replay tick resumes from this simulated instant.
                          "speed_anchor_wall": switch_completed_wall,
                          "speed_anchor_sim": frozen_sim_time,
                          "ignore_relayout_once": True,
                          # relayoutData persists across dcc.Graph figure updates; mark
                          # its old-timeframe range so it cannot be replayed next tick.
                          "stale_relayout_range": parse_x_range(chart_relayout),
                          "last_chart_bucket": latest_bucket_for_slice(ticks, end_idx, tf),
                          "last_chart_update_wall": time.monotonic(), "viewport_mode": old_mode,
                          "viewport_range": fresh_range, "viewport_span": span}
            status = f"Back-Test đang chạy • khung {tf} • cửa sổ {history_duration(tf)} • {max(0, end_idx-history_idx):,} tick đã xử lý"
            return (figure_payload(tf, chart(tf, visible, None, filter_window=False, set_initial_range=False, viewport_range=fresh_range, candles_override=replay_candles)), next_state, status, False, clock_label(sim_now),
                    True, True, True, True, True, False)
        return (figure_payload(tf, chart(tf, ticks, None, set_initial_range=True)), state, "Chọn thời gian rồi nhấn RUN", True,
                "--:--:-- (UTC+7)", False, False, False, False, False, True)

    if trigger == "replay-interval" and state and state.get("running"):
        sim_now = replay_clock(state)
        history_idx = int(state["history_idx"])
        replay_idx = int(state["replay_idx"])
        target_end_idx = int(times_index.searchsorted(sim_now, side="right"))
        target_end_idx = max(replay_idx, min(target_end_idx, len(ticks)))
        previous_cursor = int(state.get("cursor", replay_idx))
        # Process a bounded batch per 500ms pulse. If replay time runs ahead, the
        # cursor catches up over subsequent pulses without skipping any tick.
        end_idx = min(target_end_idx, previous_cursor + REPLAY_BATCH_TICKS)
        new_ticks = ticks.iloc[previous_cursor:end_idx] if end_idx > previous_cursor else ticks.iloc[0:0]
        replay_key = state.get("replay_key")
        replay_candles = _REPLAY_CANDLE_CACHE.get(replay_key)
        if replay_candles is None:
            replay_candles = build_candles(ticks.iloc[history_idx:previous_cursor], tf)
        chart_changed = end_idx > previous_cursor
        if chart_changed:
            updated_candles = append_ticks_to_candles(replay_candles, new_ticks, tf)
            if updated_candles is None:
                # A late/out-of-order record was inserted; rebuild only as a recovery path.
                updated_candles = build_candles(ticks.iloc[history_idx:end_idx], tf)
            replay_candles = updated_candles
            _REPLAY_CANDLE_CACHE[replay_key] = replay_candles
        current_bucket = latest_bucket_for_slice(ticks, end_idx, tf)
        previous_bucket = state.get("last_chart_bucket")
        now_mono = time.monotonic()
        last_chart_wall = float(state.get("last_chart_update_wall", 0.0) or 0.0)
        new_candle = current_bucket is not None and current_bucket != previous_bucket
        render_chart = chart_changed and (new_candle or now_mono - last_chart_wall >= CHART_REFRESH_SECONDS)
        next_state = {**state, "cursor": end_idx, "running": True,
                      "last_chart_bucket": current_bucket if current_bucket is not None else previous_bucket,
                      "last_chart_update_wall": now_mono if render_chart else last_chart_wall,
                      "target_cursor": target_end_idx}
        if end_idx >= len(ticks):
            status = (
                f"Back-Test đang chạy • đã phát hết tick hiện có trong DB • "
                f"đồng hồ mô phỏng {clock_label(sim_now)} • nhấn STOP để kết thúc"
            )
        else:
            latest_tick = pd.to_datetime(ticks["time"].iloc[end_idx-1]).strftime("%H:%M:%S") if end_idx > history_idx else "chờ tick"
            elapsed = sim_now - pd.Timestamp(state["start_time"])
            backlog = max(0, target_end_idx - end_idx)
            status = (
                f"Back-Test đang chạy • mô phỏng +{elapsed} • "
                f"{max(0, end_idx-history_idx):,} tick • tick cuối {latest_tick}"
                + (f" • đang xử lý tiếp {backlog:,} tick" if backlog else "")
            )
        # Replay state is the authoritative mode: viewport-state is updated by a
        # separate callback and can lag one event behind. Follow mode is changed
        # in replay-state only by the explicit Follow Latest action.
        mode = state.get("viewport_mode", (viewport or {}).get("mode", "manual"))
        saved_range = state.get("viewport_range")
        if saved_range is None:
            saved_range = (viewport or {}).get("range")
        # The Store is updated by a separate callback and may lag behind a fast
        # pan when replay-interval fires. relayoutData belongs to dcc.Graph itself
        # and is the freshest browser-side range available to this callback.
        # In Manual View, prefer that range so each server figure refresh preserves
        # the exact viewport instead of falling back to the newest candle.
        browser_range = parse_x_range(chart_relayout)
        # Plotly relayoutData survives figure changes. Ignore it for one or more updates
        # after a timeframe switch; its ordinal X coordinates refer to the old candle series.
        if state.get("timeframe") != tf or state.get("ignore_relayout_once"):
            browser_range = None
        stale_range = state.get("stale_relayout_range")
        same_as_stale = False
        if browser_range is not None and isinstance(stale_range, (list, tuple)) and len(stale_range) == 2:
            same_as_stale = abs(browser_range[0] - float(stale_range[0])) < 0.01 and abs(browser_range[1] - float(stale_range[1])) < 0.01
        ignore_stale_relayout = bool(state.get("ignore_relayout_once")) or same_as_stale
        # viewport-state is ordinal-indexed and therefore valid only for the timeframe
        # in which it was captured. Never apply the previous timeframe's range to this one.
        viewport_tf = (viewport or {}).get("timeframe")
        stored_range = (viewport or {}).get("range") if viewport_tf == tf else None
        # Prefer the separately captured viewport store only when it belongs to this timeframe;
        # otherwise retain the fresh range seeded by the timeframe-switch callback.
        if mode == "manual" and isinstance(stored_range, (list, tuple)) and len(stored_range) == 2:
            saved_range = [float(stored_range[0]), float(stored_range[1])]
        if mode == "manual" and browser_range is not None and not ignore_stale_relayout:
            differs_from_store = not (isinstance(stored_range, (list, tuple)) and len(stored_range) == 2
                and abs(browser_range[0] - float(stored_range[0])) < 0.01
                and abs(browser_range[1] - float(stored_range[1])) < 0.01)
            if differs_from_store:
                saved_range = browser_range
                next_state["stale_relayout_range"] = None
        span = max(10, min(1000, int((viewport or {}).get("span", state.get("viewport_span", 110)) or 110)))
        if render_chart:
            candle_count = len(replay_candles)
            if mode == "follow":
                current_range = [max(-0.5, candle_count - span - 0.5), max(0.5, candle_count - 0.5 + 20)]
            else:
                current_range = saved_range
        else:
            current_range = saved_range
        next_state["viewport_mode"] = mode
        next_state["viewport_range"] = current_range
        next_state["viewport_span"] = span
        # The latest manual range is authored into the new figure only after it
        # has been selected from current replay state/browser relayoutData. On a
        # timeframe switch we seed a fresh range and ignore one stale relayout
        # event; afterward normal user pans are honored. This avoids both stale
        # range snap-back and Follow Latest accidentally taking over Manual View.
        figure_range = current_range if current_range is not None else None
        figure_update = figure_payload(tf, chart(tf, None, None, filter_window=False, set_initial_range=False,
                              viewport_range=figure_range, candles_override=replay_candles)) if render_chart else no_update
        if next_state.get("ignore_relayout_once"):
            # Consume the one-cycle guard even if no new tick arrived. Otherwise
            # stale relayoutData from the old timeframe could be ignored forever.
            next_state["ignore_relayout_once"] = False
        return (figure_update, next_state, status, False, clock_label(sim_now),
                True, True, True, True, True, False)

    # Initial page load or a non-running state.
    return (figure_payload(tf, chart(tf, ticks, set_initial_range=True)), state, "Chọn ngày/giờ rồi nhấn RUN", True,
            "--:--:-- (UTC+7)", False, False, False, False, False, True)


app.clientside_callback(
    """function(candidate, selectedTimeframe, currentState) {
        const noUpdate = window.dash_clientside.no_update;
        const tf = selectedTimeframe || '5m';
        const ctx = (window.dash_clientside.callback_context && window.dash_clientside.callback_context.triggered) || [];
        const changed = ctx.some(x => x && x.prop_id === 'timeframe.value');
        const pending = candidate && candidate.trigger === 'timeframe-pending' && candidate.timeframe === tf;
        const completed = candidate && (candidate.trigger === 'timeframe-complete' || candidate.trigger === 'timeframe') && candidate.timeframe === tf;
        if (changed && currentState && currentState.running) {
            return [false, true, '⏳ Đang chuyển khung thời gian sang ' + tf + '…'];
        }
        if (pending) return [false, true, '⏳ Đang chuyển khung thời gian sang ' + tf + '…'];
        if (candidate && candidate.trigger === 'timeframe-error' && candidate.timeframe === tf) {
            const message = candidate.outputs && candidate.outputs[2] && candidate.outputs[2].__no_update__ !== true ? candidate.outputs[2] : 'Không thể chuyển khung thời gian.';
            return [true, false, '⚠ ' + message];
        }
        if (completed || (candidate && candidate.trigger === 'stop-backtest')) return [true, false, ''];
        return [noUpdate, noUpdate, noUpdate];
    }""",
    Output("timeframe-switch-poll", "disabled"),
    Output("timeframe", "disabled"),
    Output("timeframe-switch-indicator", "children"),
    Input("backtest-result-candidate", "data"),
    Input("timeframe", "value"),
    State("replay-state", "data"),
    prevent_initial_call=True,
)


@app.callback(
    Output("backtest-result-candidate", "data"),
    Input("run-backtest","n_clicks"),
    Input("stop-backtest","n_clicks"),
    Input("replay-interval","n_intervals"),
    Input("timeframe-switch-poll","n_intervals"),
    Input("replay-speed","data"),
    Input("timeframe","value"),
    Input("follow-latest","n_clicks"),
    State("replay-date","date"),
    State("replay-hour","value"),
    State("replay-minute","value"),
    State("replay-second","value"),
    State("replay-state","data"),
    State("viewport-state","data"),
    State("price-chart","relayoutData"),
    prevent_initial_call=False)

def drive_backtest(run_clicks, stop_clicks, interval_n, switch_poll_n, selected_speed, timeframe, follow_clicks, selected_date, hour, minute, second, state, viewport, chart_relayout):
    global _ACTIVE_TIMEFRAME_SWITCH
    trigger = callback_context.triggered_id
    tf = timeframe or "5m"

    def encode(value):
        return {"__no_update__": True} if value is no_update else value

    def candidate(result, trigger_name, pending=False, switch_id=None):
        if not isinstance(result, tuple) or len(result) != 11:
            return result
        return {"timeframe": tf, "trigger": trigger_name, "outputs": [encode(value) for value in result],
                "switch_pending": bool(pending), "switch_id": switch_id}

    # A timeframe change during RUN is acknowledged immediately. The expensive
    # candle aggregation + Plotly serialization runs in a worker, not inside the
    # Dash request thread, so the browser can show a reliable progress indicator.
    if trigger == "timeframe" and state and state.get("running"):
        switch_id = f"{state.get('replay_session_key', 'session')}:{time.time_ns()}:{tf}"
        args = (run_clicks, stop_clicks, interval_n, selected_speed, tf, follow_clicks,
                selected_date, hour, minute, second, dict(state), dict(viewport or {}), chart_relayout)
        with _TIMEFRAME_SWITCH_LOCK:
            old = _ACTIVE_TIMEFRAME_SWITCH
            if old and old.get("future") and not old["future"].done():
                old["future"].cancel()
            future = _TIMEFRAME_SWITCH_EXECUTOR.submit(_drive_backtest_impl, *args, trigger_override="timeframe")
            _ACTIVE_TIMEFRAME_SWITCH = {"id": switch_id, "timeframe": tf,
                                        "session": state.get("replay_session_key"),
                                        "cursor": int(state.get("cursor", 0)), "future": future}
        pending_result = (no_update, no_update, f"Đang chuyển khung thời gian sang {tf}…", True,
                          no_update, no_update, no_update, no_update, no_update, no_update, no_update)
        return candidate(pending_result, "timeframe-pending", pending=True, switch_id=switch_id)

    if trigger == "timeframe-switch-poll":
        with _TIMEFRAME_SWITCH_LOCK:
            job = _ACTIVE_TIMEFRAME_SWITCH
        if not job:
            return candidate((no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update),
                             "timeframe-pending", pending=True)
        # Ignore a completed job if the user selected another timeframe or ended/restarted replay.
        if job.get("timeframe") != tf or not state or not state.get("running") or state.get("replay_session_key") != job.get("session"):
            with _TIMEFRAME_SWITCH_LOCK:
                if _ACTIVE_TIMEFRAME_SWITCH and _ACTIVE_TIMEFRAME_SWITCH.get("id") == job.get("id"):
                    _ACTIVE_TIMEFRAME_SWITCH = None
            return candidate((no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update),
                             "timeframe-pending", pending=True)
        future = job["future"]
        if not future.done():
            pending_result = (no_update, no_update, f"Đang chuyển khung thời gian sang {tf}…", True,
                              no_update, no_update, no_update, no_update, no_update, no_update, no_update)
            return candidate(pending_result, "timeframe-pending", pending=True, switch_id=job.get("id"))
        try:
            result = future.result()
        except Exception as exc:
            with _TIMEFRAME_SWITCH_LOCK:
                if _ACTIVE_TIMEFRAME_SWITCH and _ACTIVE_TIMEFRAME_SWITCH.get("id") == job.get("id"):
                    _ACTIVE_TIMEFRAME_SWITCH = None
            failed = (no_update, no_update, f"Lỗi chuyển khung {tf}: {type(exc).__name__}: {exc}", True,
                      no_update, no_update, no_update, no_update, no_update, no_update, no_update)
            return candidate(failed, "timeframe-error", switch_id=job.get("id"))
        with _TIMEFRAME_SWITCH_LOCK:
            if _ACTIVE_TIMEFRAME_SWITCH and _ACTIVE_TIMEFRAME_SWITCH.get("id") == job.get("id"):
                _ACTIVE_TIMEFRAME_SWITCH = None
        return candidate(result, "timeframe-complete", switch_id=job.get("id"))

    result = _drive_backtest_impl(run_clicks, stop_clicks, interval_n, selected_speed, tf, follow_clicks,
                                  selected_date, hour, minute, second, state, viewport, chart_relayout)
    return candidate(result, trigger or "unknown")


@app.callback(
    Output("custom-quantity","value"),
    Input("qty-preset-1","n_clicks"), Input("qty-preset-5","n_clicks"),
    Input("qty-preset-10","n_clicks"), Input("qty-preset-20","n_clicks"),
    Input("qty-minus","n_clicks"), Input("qty-plus","n_clicks"),
    State("custom-quantity","value"), prevent_initial_call=True)
def update_quantity(n1,n5,n10,n20,nminus,nplus,current):
    trigger = callback_context.triggered_id
    presets = {"qty-preset-1":1, "qty-preset-5":5, "qty-preset-10":10, "qty-preset-20":20}
    if trigger in presets:
        return presets[trigger]
    try:
        current = max(1, int(current or 1))
    except (TypeError, ValueError):
        current = 1
    return max(1, current - 1) if trigger == "qty-minus" else current + 1

@app.callback(Output("quantity-validation","children"), Output("quantity-validation","className"),
    Input("custom-quantity","value"), Input("order-state","data"))
def validate_quantity(value, order_state):
    state = order_state or {}
    net_assets = INITIAL_NET_ASSET_VND + float(state.get("realized_gross", 0)) - float(state.get("fees", 0))
    max_total = max(0, int(max(0, net_assets) // MARGIN_PER_CONTRACT_VND))
    pos = state.get("position") or {}
    used = int(pos.get("qty", 0) or 0)
    pending = sum(int(o.get("qty", 0) or 0) for o in state.get("orders", []) if o.get("status") == "Chờ khớp")
    max_new = max(0, max_total - used - pending)
    try:
        q = int(value)
        valid = value is not None and float(value) == q and q >= 1 and q <= max_new
    except (TypeError, ValueError):
        valid = False
    if valid:
        return f"KL hợp lệ • tối đa có thể đặt thêm: {max_new}", "quantity-validation valid"
    return f"Nhập KL nguyên từ 1 đến {max_new} (ký quỹ {MARGIN_PER_CONTRACT_VND:,.0f} ₫/HĐ)", "quantity-validation invalid"

@app.callback(Output("order-type-ato","className"), Output("order-type-atc","className"),
    Output("order-type-mtl","className"), Output("order-type-mok","className"), Output("order-type-mak","className"),
    Input("order-type-ato","n_clicks"), Input("order-type-atc","n_clicks"), Input("order-type-mtl","n_clicks"),
    Input("order-type-mok","n_clicks"), Input("order-type-mak","n_clicks"), prevent_initial_call=True)
def select_order_type(*clicks):
    selected = callback_context.triggered_id
    ids = ["order-type-ato","order-type-atc","order-type-mtl","order-type-mok","order-type-mak"]
    return tuple("order-type-btn selected" if item == selected else "order-type-btn" for item in ids)

@app.callback(Output("order-mode-store","data"), Output("auto-mode-toggle","className"), Output("auto-mode-toggle","children"),
    Output("order-price","value"),
    Input("auto-mode-toggle","n_clicks"),
    Input("order-type-ato","n_clicks"), Input("order-type-atc","n_clicks"), Input("order-type-mtl","n_clicks"),
    Input("order-type-mok","n_clicks"), Input("order-type-mak","n_clicks"),
    State("order-mode-store","data"), prevent_initial_call=True)
def toggle_auto_mode(auto_clicks, ato_clicks, atc_clicks, mtl_clicks, mok_clicks, mak_clicks, mode):
    trigger = callback_context.triggered_id
    if trigger == "auto-mode-toggle":
        new_mode = "MAK" if mode != "MAK" else "LIMIT"
    elif trigger == "order-type-mak":
        new_mode = "MAK"
    else:
        new_mode = "LIMIT"
    price_value = None if new_mode == "MAK" else no_update
    label = "MAK" if new_mode == "MAK" else "AUTO"
    return new_mode, ("auto-mode-button active" if new_mode == "MAK" else "auto-mode-button"), label, price_value

def _current_replay_price(replay_state):
    ticks = cached_ticks()
    if ticks is None or ticks.empty:
        return None
    try:
        replay = replay_state or {}
        cursor = int(replay.get("cursor", 0))
        if replay.get("running") and cursor <= 0:
            return None
        if cursor > 0:
            return float(ticks.iloc[min(cursor, len(ticks))-1]["price"])
        return float(ticks.iloc[-1]["price"])
    except (TypeError, ValueError, KeyError, IndexError):
        return None

def _money(value):
    return f"{float(value):,.0f} ₫"

def _max_open_contracts(state):
    net_assets = INITIAL_NET_ASSET_VND + float(state.get("realized_gross", 0)) - float(state.get("fees", 0))
    return max(0, int(max(0, net_assets) // MARGIN_PER_CONTRACT_VND))

def _execute_fill(state, order, fill_price, fill_time=None):
    qty = int(order["qty"])
    side = order["side"]
    pos = state.get("position")
    realized = 0.0
    if not pos or int(pos.get("qty", 0)) <= 0:
        state["position"] = {"side": side, "qty": qty, "entry_price": float(fill_price)}
    elif pos["side"] == side:
        old_qty = int(pos["qty"])
        pos["entry_price"] = (float(pos["entry_price"])*old_qty + float(fill_price)*qty)/(old_qty+qty)
        pos["qty"] = old_qty + qty
    else:
        old_qty = int(pos["qty"])
        close_qty = min(old_qty, qty)
        direction = 1 if pos["side"] == "LONG" else -1
        realized = (float(fill_price)-float(pos["entry_price"]))*close_qty*POINT_VALUE_VND*direction
        state["realized_gross"] = float(state.get("realized_gross", 0)) + realized
        remaining_old = old_qty-close_qty
        remaining_new = qty-close_qty
        if remaining_old > 0:
            pos["qty"] = remaining_old
        elif remaining_new > 0:
            state["position"] = {"side": side, "qty": remaining_new, "entry_price": float(fill_price)}
        else:
            state["position"] = None
    state["fees"] = float(state.get("fees", 0)) + qty*FEE_PER_CONTRACT_VND
    order["status"] = "Đã khớp"
    order["filled_qty"] = qty
    order["avg_fill_price"] = float(fill_price)
    order["fill_time"] = str(fill_time) if fill_time is not None else "MAK tức thời"
    return realized

def _render_orders(state):
    orders = list(state.get("orders", []))
    if not orders:
        return html.Div("Chưa có lệnh", className="empty-orders"), "0"
    rows=[]
    for order in reversed(orders):
        status=order.get("status", "Chờ khớp")
        actions=[]
        if status == "Chờ khớp":
            actions=[html.Button("Sửa", id={"type":"edit-order","index":str(order["id"])}, n_clicks=0, className="order-action-edit"),
                     html.Button("Hủy", id={"type":"cancel-order","index":str(order["id"])}, n_clicks=0, className="order-action-cancel")]
        rows.append(html.Div([
            html.Span(order.get("symbol", DEFAULT_ORDER_SYMBOL)),
            html.Span(order.get("side", "-"), className="order-long" if order.get("side")=="LONG" else "order-short"),
            html.Span(str(order.get("qty", 0))),
            html.Span(f"{float(order.get('price', 0)):,.2f}"),
            html.Span(str(order.get("filled_qty", 0))),
            html.Span("-" if order.get("avg_fill_price") is None else f"{float(order['avg_fill_price']):,.2f}"),
            html.Span(status, className="order-status " + ("filled" if status=="Đã khớp" else "pending" if status=="Chờ khớp" else "cancelled")),
            html.Span(actions, className="order-row-actions")
        ], className="order-data-row", key=str(order["id"])))
    return html.Div(rows, className="orders-rows-scroll"), str(len(orders))

@app.callback(
    Output("order-state","data"), Output("orders-list","children"), Output("order-count","children"),
    Output("asset-net","children"), Output("asset-withdrawable","children"), Output("asset-pnl","children"), Output("asset-fees","children"),
    Output("trade-feedback","children"), Output("quantity-required-dialog","displayed"), Output("trade-ui-state","data"),
    Output("edit-price","value"), Output("edit-quantity","value"), Output("edit-side","value"),
    Output("max-open-qty","children"), Output("buying-power-display","children"),
    Output("position-summary","children"), Output("position-action-modal","style"), Output("position-action-title","children"), Output("position-action-price","value"),
    Input("long-btn","n_clicks"), Input("short-btn","n_clicks"), Input("replay-state","data"), Input("reset-backtest","n_clicks"),
    Input("market-confirm","n_clicks"), Input("market-cancel","n_clicks"),
    Input("position-close","n_clicks"), Input("position-reverse","n_clicks"), Input("position-action-confirm","n_clicks"), Input("position-action-cancel","n_clicks"),
    Input({"type":"edit-order","index":ALL},"n_clicks"), Input({"type":"cancel-order","index":ALL},"n_clicks"),
    Input("edit-save","n_clicks"), Input("edit-cancel","n_clicks"), Input("order-mode-store","data"),
    State("order-state","data"), State("order-price","value"), State("custom-quantity","value"),
    State("trade-ui-state","data"), State("edit-price","value"), State("edit-quantity","value"), State("edit-side","value"), State("position-action-price","value"),
    prevent_initial_call=True)
def manage_orders(long_clicks, short_clicks, replay_state, reset_clicks, market_confirm, market_cancel,
                  position_close, position_reverse, position_action_confirm, position_action_cancel,
                  edit_clicks, cancel_clicks, edit_save, edit_cancel, mode, order_state, price_value, quantity,
                  ui_state, edit_price, edit_quantity, edit_side, position_action_price):
    state = dict(order_state or {})
    state.setdefault("orders", []); state.setdefault("position", None); state.setdefault("realized_gross", 0.0); state.setdefault("fees", 0.0); state.setdefault("next_id", 1)
    ui = dict(ui_state or {"modal":None,"side":None,"order_id":None})
    trigger = callback_context.triggered_id
    feedback = no_update
    show_qty_dialog = False
    out_edit_price, out_edit_qty, out_edit_side = no_update, no_update, no_update
    position_modal_style = {"display":"none"}; position_modal_title = no_update; out_position_action_price = no_update
    ticks = cached_ticks()
    cursor = int((replay_state or {}).get("cursor", 0) or 0)

    # Reset only the simulated account state. Tick data in DuckDB and chart drawings are untouched.
    if trigger == "reset-backtest":
        state = {"orders": [], "position": None, "realized_gross": 0.0, "fees": 0.0,
                 "last_cursor": cursor, "next_id": 1,
                 "replay_key": (replay_state or {}).get("replay_key")}
        ui = {"modal": None, "side": None, "order_id": None}
        feedback = "Đã reset Back-Test: tài sản về mức ban đầu, xóa toàn bộ lệnh và vị thế; dữ liệu tick và đường line được giữ nguyên."
        out_edit_price = None
        out_edit_qty = None
        out_edit_side = "LONG"
        out_position_action_price = None
    # First process ticks that appeared since the last order-engine cursor. The same engine survives timeframe changes.
    elif trigger == "replay-state" and ticks is not None and not ticks.empty:
        replay_key = (replay_state or {}).get("replay_key")
        previous_replay_key = state.get("replay_key")
        if replay_key != previous_replay_key:
            # A new RUN establishes a new replay timeline; do not scan ticks from the prior run.
            state["last_cursor"] = min(cursor, len(ticks))
            state["replay_key"] = replay_key
        prev = int(state.get("last_cursor", cursor) or 0)
        end = min(cursor, len(ticks))
        if end > prev:
            for idx in range(max(0, prev), end):
                tick = ticks.iloc[idx]
                tick_price = float(tick["price"])
                tick_time = tick["time"]
                for order in state["orders"]:
                    if order.get("status") != "Chờ khớp":
                        continue
                    limit = float(order["price"])
                    touched = tick_price <= limit if order["side"] == "LONG" else tick_price >= limit
                    if touched:
                        _execute_fill(state, order, limit, tick_time)
                        if order.get("position_action") == "close":
                            order["status"] = "Đã khớp"
                        elif order.get("position_action") == "reverse":
                            order["status"] = "Đã khớp"
            state["last_cursor"] = end
    current_price = _current_replay_price(replay_state)

    if trigger in ("long-btn", "short-btn"):
        side = "LONG" if trigger == "long-btn" else "SHORT"
        try:
            q = int(quantity)
            qty_ok = quantity is not None and float(quantity) == q and q > 0
        except (TypeError, ValueError):
            qty_ok = False; q = 0
        if not qty_ok:
            show_qty_dialog = True
            feedback = "Cần nhập khối lượng trước khi đặt lệnh."
        else:
            pos = state.get("position") or {}
            existing = int(pos.get("qty", 0) or 0)
            total_max = _max_open_contracts(state)
            pending_qty = sum(int(o.get("qty", 0) or 0) for o in state["orders"] if o.get("status")=="Chờ khớp")
            need_open = q if not pos else (q if pos.get("side")==side else max(0, q-existing))
            if ((not pos and q + pending_qty > total_max) or
                (pos and pos.get("side")==side and existing + pending_qty + q > total_max) or
                (pos and pos.get("side")!=side and q > existing and (q-existing) + pending_qty > total_max)):
                feedback = f"Không đủ tài sản ký quỹ. Sức chứa hiện tại theo tài sản: {max(0,total_max-existing-pending_qty)} HĐ; yêu cầu {q} HĐ."
            elif mode == "MAK":
                ui = {"modal":"market", "side":side, "order_id":None}
                feedback = f"Xác nhận lệnh thị trường {side} • KL {q}."
            else:
                try:
                    limit_price = float(price_value)
                    if not (limit_price > 0): raise ValueError()
                except (TypeError, ValueError):
                    feedback = "Vui lòng nhập giá đặt hợp lệ hoặc bật AUTO/MAK để đặt lệnh thị trường."
                else:
                    order={"id":str(state.get("next_id",1)),"symbol":DEFAULT_ORDER_SYMBOL,"side":side,"qty":q,"price":limit_price,
                           "filled_qty":0,"avg_fill_price":None,"status":"Chờ khớp","created_time":str((replay_state or {}).get("start_time") or "")}
                    state["next_id"] = int(state.get("next_id",1))+1
                    # Marketable limit orders execute at the current replay price, never at a worse limit price.
                    marketable = current_price is not None and ((side == "LONG" and limit_price >= current_price) or (side == "SHORT" and limit_price <= current_price))
                    if marketable:
                        _execute_fill(state, order, float(current_price), (replay_state or {}).get("start_time"))
                        feedback=f"Đã khớp {side} {q} HĐ tại giá hiện tại {current_price:,.2f} (giá đặt {limit_price:,.2f})."
                    else:
                        state["orders"].append(order)
                        feedback=f"Đã thêm lệnh {side} {q} HĐ tại {limit_price:,.2f} vào sổ lệnh chờ khớp."
                    if marketable:
                        state["orders"].append(order)
                    state["last_cursor"] = cursor
    elif trigger in ("position-close", "position-reverse"):
        pos = state.get("position") or {}
        if not pos or int(pos.get("qty", 0) or 0) <= 0:
            feedback = "Hiện không có vị thế mở để thao tác."
        else:
            ui = {"modal":"position_action", "position_action":"close" if trigger == "position-close" else "reverse", "side":pos["side"]}
            position_modal_style = {"display":"flex"}
            position_modal_title = "Đóng vị thế" if trigger == "position-close" else "Đảo chiều vị thế"
            out_position_action_price = current_price
    elif trigger == "position-action-cancel":
        ui = {"modal":None,"side":None,"order_id":None}
    elif trigger == "position-action-confirm" and ui.get("modal") == "position_action":
        pos = state.get("position") or {}
        try:
            action_price = float(position_action_price)
            if not pos or int(pos.get("qty",0)) <= 0 or action_price <= 0: raise ValueError()
            close_side = "SHORT" if pos["side"] == "LONG" else "LONG"
            pos_qty = int(pos["qty"])
            action = ui.get("position_action")
            action_qty = pos_qty if action == "close" else pos_qty * 2
            order = {"id":str(state.get("next_id",1)),"symbol":DEFAULT_ORDER_SYMBOL,"side":close_side,"qty":action_qty,"price":action_price,
                     "filled_qty":0,"avg_fill_price":None,"status":"Chờ khớp","position_action":action,
                     "created_time":str((replay_state or {}).get("start_time") or "")}
            state["next_id"] = int(state.get("next_id",1))+1
            state["orders"].append(order)
            feedback = ("Đã tạo lệnh chờ đóng vị thế" if action == "close" else "Đã tạo lệnh chờ đảo chiều") + f" tại {action_price:,.2f}."
        except (TypeError, ValueError):
            feedback = "Giá thực hiện không hợp lệ hoặc không còn vị thế mở."
        ui = {"modal":None,"side":None,"order_id":None}
    elif isinstance(trigger, dict) and trigger.get("type") == "edit-order":
        order=next((o for o in state["orders"] if str(o.get("id"))==str(trigger.get("index")) and o.get("status")=="Chờ khớp"),None)
        if order:
            ui={"modal":"edit","side":order["side"],"order_id":str(order["id"])}
            out_edit_price=order["price"]; out_edit_qty=order["qty"]; out_edit_side=order["side"]
    elif isinstance(trigger, dict) and trigger.get("type") == "cancel-order":
        order=next((o for o in state["orders"] if str(o.get("id"))==str(trigger.get("index")) and o.get("status")=="Chờ khớp"),None)
        if order:
            order["status"]="Đã hủy"; order["cancelled_qty"]=int(order.get("qty",0))-int(order.get("filled_qty",0)); feedback=f"Đã hủy lệnh #{order['id']}."
    elif trigger == "edit-save" and ui.get("modal")=="edit":
        order=next((o for o in state["orders"] if str(o.get("id"))==str(ui.get("order_id")) and o.get("status")=="Chờ khớp"),None)
        try:
            new_q=int(edit_quantity); new_p=float(edit_price)
            if order is None or new_q<1 or float(edit_quantity)!=new_q or new_p<=0 or edit_side not in ("LONG","SHORT"):
                raise ValueError()
            position=state.get("position") or {}
            current_qty=int(position.get("qty",0) or 0)
            total_max=_max_open_contracts(state)
            other_pending=sum(int(o.get("qty",0) or 0) for o in state["orders"] if o.get("status")=="Chờ khớp" and str(o.get("id"))!=str(order.get("id")))
            need_open=new_q if not position else (new_q if position.get("side")==edit_side else max(0,new_q-current_qty))
            over_limit=((not position and new_q+other_pending>total_max) or
                        (position and position.get("side")==edit_side and current_qty+other_pending+new_q>total_max) or
                        (position and position.get("side")!=edit_side and new_q>current_qty and (new_q-current_qty)+other_pending>total_max))
            if over_limit:
                feedback=f"Không thể sửa: vượt hạn mức ký quỹ hiện tại ({total_max} HĐ tối đa)."
            else:
                order.update({"qty":new_q,"price":new_p,"side":edit_side})
                feedback=f"Đã cập nhật lệnh #{order['id']}."
        except (TypeError,ValueError):
            feedback="Thông số sửa lệnh không hợp lệ; kiểm tra khối lượng và giá."
        ui={"modal":None,"side":None,"order_id":None}
    elif trigger == "edit-cancel":
        ui={"modal":None,"side":None,"order_id":None}
    elif trigger == "market-cancel":
        ui={"modal":None,"side":None,"order_id":None}
    elif trigger == "market-confirm" and ui.get("modal")=="market":
        side=ui.get("side")
        try:
            q=int(quantity); qty_ok=quantity is not None and float(quantity)==q and q>0
        except (TypeError,ValueError): qty_ok=False; q=0
        price=_current_replay_price(replay_state)
        if not qty_ok:
            show_qty_dialog=True; feedback="Cần nhập khối lượng trước khi xác nhận lệnh thị trường."
        elif price is None:
            feedback="Chưa có giá replay để khớp lệnh thị trường."
        else:
            pos=state.get("position") or {}; existing=int(pos.get("qty",0) or 0); total_max=_max_open_contracts(state)
            pending_qty=sum(int(o.get("qty",0) or 0) for o in state["orders"] if o.get("status")=="Chờ khớp")
            if ((not pos and q+pending_qty > total_max) or
                (pos and pos.get("side")==side and existing+q+pending_qty > total_max) or
                (pos and pos.get("side")!=side and q>existing and (q-existing)+pending_qty > total_max)):
                feedback=f"Không đủ tài sản ký quỹ để mở vị thế {q} HĐ."
            else:
                order={"id":str(state.get("next_id",1)),"symbol":DEFAULT_ORDER_SYMBOL,"side":side,"qty":q,"price":price,
                       "filled_qty":0,"avg_fill_price":None,"status":"Chờ khớp"}
                state["next_id"]=int(state.get("next_id",1))+1
                _execute_fill(state,order,price,(replay_state or {}).get("start_time"))
                state["orders"].append(order); feedback=f"Đã khớp MAK {side} {q} HĐ tại {price:,.2f}."
        ui={"modal":None,"side":None,"order_id":None}
    # Toggle mode itself does not alter orders.
    state["last_cursor"] = max(int(state.get("last_cursor",0) or 0), min(cursor, len(ticks) if ticks is not None else cursor))
    orders_children, order_count = _render_orders(state)
    fees=float(state.get("fees",0))
    realized_net=float(state.get("realized_gross",0))-fees
    net=INITIAL_NET_ASSET_VND+realized_net
    withdrawable = net - realized_net - fees
    pos = state.get("position") or {}
    position_qty=int(pos.get("qty",0) or 0)
    unrealized = 0.0
    if position_qty:
        side = pos.get("side", "LONG")
        entry = float(pos.get("entry_price", 0) or 0)
        mark = float(current_price if current_price is not None else entry)
        direction = 1 if side == "LONG" else -1
        unrealized = (mark-entry)*position_qty*POINT_VALUE_VND*direction
    pnl = float(state.get("realized_gross", 0)) + unrealized - fees
    if position_qty:
        position_view = html.Div([
            html.Div([html.B("Vị thế mở"), html.Span(f"{side} {position_qty} HĐ", className="position-long" if side=="LONG" else "position-short")], className="position-line"),
            html.Div([html.Span("Giá vào"), html.B(f"{entry:,.2f}")], className="position-line"),
            html.Div([html.Span("Lãi/lỗ chưa chốt"), html.B(_money(unrealized), className="position-long" if unrealized>=0 else "position-short")], className="position-line")
        ])
    else:
        position_view = html.Div([html.B("Vị thế mở"), html.Span("Chưa có vị thế"), html.Div([html.Span("Lãi/lỗ chưa chốt"), html.B("0 ₫")], className="position-line")])
    pending_qty=sum(int(o.get("qty",0) or 0) for o in state["orders"] if o.get("status")=="Chờ khớp")
    max_total=_max_open_contracts(state)
    available=max(0,max_total-position_qty-pending_qty)
    buying_power=max(0,net-position_qty*MARGIN_PER_CONTRACT_VND)
    position_modal_style = {"display":"flex"} if ui.get("modal")=="position_action" else {"display":"none"}
    position_modal_title = ("Đóng vị thế" if ui.get("position_action")=="close" else "Đảo chiều vị thế") if ui.get("modal")=="position_action" else no_update
    return (state, orders_children, order_count, _money(net), _money(withdrawable), _money(pnl), _money(fees), feedback,
            show_qty_dialog, ui, out_edit_price, out_edit_qty, out_edit_side,
            f"KL mở thêm tối đa {available} HĐ", f"Sức mua {_money(buying_power)}", position_view, position_modal_style, position_modal_title, out_position_action_price)

@app.callback(Output("market-modal","style"), Output("edit-modal","style"), Output("market-confirm-title","children"),
    Input("trade-ui-state","data"))
def render_trade_modals(ui):
    ui=ui or {}
    hidden={"display":"none"}; shown={"display":"flex"}
    side=ui.get("side") or "LONG"
    return shown if ui.get("modal")=="market" else hidden, shown if ui.get("modal")=="edit" else hidden, f"Xác nhận lệnh MAK {side}"

@app.callback(Output("market-confirm-price","children"), Input("replay-state","data"))
def update_market_confirm_price(replay_state):
    price=_current_replay_price(replay_state)
    return "Chưa có giá replay" if price is None else f"{price:,.2f}"

