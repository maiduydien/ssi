"""Central application configuration loaded from environment / .env."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = PROJECT_ROOT / "assets"
APP_TITLE = os.getenv("APP_TITLE", "SSI iBoard Backtest UI")
HOST = os.getenv("DASH_HOST", "127.0.0.1")
PORT = int(os.getenv("DASH_PORT", "8050"))
DEBUG = os.getenv("DASH_DEBUG", "false").lower() == "true"
DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "VN30F1M")
DB_PATH = Path(os.getenv(
    "DUCKDB_PATH",
    r"F:\New Projects\Chung_Khoan\GiaKhopLenh\data\database\vn30f1m.duckdb"
)).expanduser()
TABLE_NAME = os.getenv("DUCKDB_TABLE", "vn30f1m_ticks")
DATA_MODE = os.getenv("DATA_MODE", "auto").strip().lower()
if DATA_MODE not in {"auto", "duckdb", "mock"}:
    raise ValueError("DATA_MODE must be one of: auto, duckdb, mock")
TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1D"]
TICK_LOAD_LIMIT = int(os.getenv("TICK_LOAD_LIMIT", "10000000"))
INITIAL_NET_ASSET_VND = float(os.getenv("INITIAL_NET_ASSET_VND", "25000000"))
MARGIN_PER_CONTRACT_VND = float(os.getenv("MARGIN_PER_CONTRACT_VND", "9000000"))
FEE_PER_CONTRACT_VND = float(os.getenv("FEE_PER_CONTRACT_VND", "70000"))
POINT_VALUE_VND = float(os.getenv("POINT_VALUE_VND", "100000"))
DEFAULT_ORDER_SYMBOL = os.getenv("DEFAULT_ORDER_SYMBOL", "VN30FM1")
APP_VERSION = os.getenv("APP_VERSION", "0.1.0")
GIT_SHA = os.getenv("GIT_SHA", "unknown")
