import os
from pathlib import Path
APP_TITLE = "SSI iBoard Backtest UI"
HOST = os.getenv("DASH_HOST", "127.0.0.1")
PORT = int(os.getenv("DASH_PORT", "8050"))
DEBUG = os.getenv("DASH_DEBUG", "false").lower() == "true"
DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "VN30F1M")
DB_PATH = Path(os.getenv("DUCKDB_PATH", r"F:\New Projects\Chung_Khoan\GiaKhopLenh\data\database\vn30f1m.duckdb"))
TABLE_NAME = os.getenv("DUCKDB_TABLE", "vn30f1m_ticks")
TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1D"]

# Maximum tick records loaded from DuckDB at startup; 0 means load all rows.
TICK_LOAD_LIMIT = int(os.getenv("TICK_LOAD_LIMIT", "10000000"))

# Paper-trading/backtest account settings (all amounts in VND).
INITIAL_NET_ASSET_VND = float(os.getenv("INITIAL_NET_ASSET_VND", "25000000"))
MARGIN_PER_CONTRACT_VND = float(os.getenv("MARGIN_PER_CONTRACT_VND", "9000000"))
FEE_PER_CONTRACT_VND = float(os.getenv("FEE_PER_CONTRACT_VND", "70000"))
# VN30F contract point multiplier; configurable for backtest assumptions.
POINT_VALUE_VND = float(os.getenv("POINT_VALUE_VND", "100000"))
DEFAULT_ORDER_SYMBOL = os.getenv("DEFAULT_ORDER_SYMBOL", "VN30FM1")
