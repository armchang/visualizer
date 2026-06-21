import os
from pathlib import Path

# Local machine paths can live in ignored config/local_config.py.
PROJECT_ROOT = Path(os.environ.get("DATASPIDER_PROJECT_ROOT", Path(__file__).resolve().parents[1])).expanduser()

try:
    from config import local_config
except ModuleNotFoundError as exc:
    if exc.name != "config.local_config":
        raise
    local_config = None

if local_config and hasattr(local_config, "PROJECT_ROOT"):
    PROJECT_ROOT = Path(local_config.PROJECT_ROOT).expanduser()

# Keep these names aligned with DataSpider so both projects can share database
# configuration.
DATABASE_TYPE = os.environ.get("DATABASE_TYPE", "postgresql").lower()
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:genius1019@localhost:5433/dataspider",
)

if local_config and hasattr(local_config, "DATABASE_TYPE"):
    DATABASE_TYPE = local_config.DATABASE_TYPE.lower()

if local_config and hasattr(local_config, "DATABASE_URL"):
    DATABASE_URL = local_config.DATABASE_URL

SUPPORTED_DATABASE_TYPES = {"postgresql", "sqlite"}
if DATABASE_TYPE not in SUPPORTED_DATABASE_TYPES:
    supported = ", ".join(sorted(SUPPORTED_DATABASE_TYPES))
    raise ValueError(f"Unsupported DATABASE_TYPE {DATABASE_TYPE!r}; expected one of: {supported}")

PAIR_NAME = os.environ.get("TRADING_PAIR", "BTCUSDT").strip().upper() or "BTCUSDT"
DAILY_LOSS_CAP = -0.1
COOLDOWN_BARS = 25
RESAMPLE_INTERVAL = "4h"
ATR_PERIOD = 21
STRATEGY = "scripts.strategies.ema_crossover"

YEARS_BACKTRACK = 5
TABLE_NAME = "ohclv"
SENSITIVITY = 2.0
USE_HEIKIN_ASHI = False
STARTING_BALANCE = 1000.0
EXCHANGE_FEE = 0.001
YEARS_BACKTRACK = 5
EMA_SMOOTHING = 10

# Volatility computation
TARGET_VOL = 0.02   
BAR_HOURS = 4                           # How may bars per hour based on the interval used
HORIZON_DAYS = 1
MAX_LEVERAGE = 3.0

# Growth Cool-Off
GROWTH_THRESHOLD = 0.50                 # 50% equity growth
COOL_OFF_BARS_AFTER_GROWTH = 10         # skip this many bars after exit

# Capital used every trade
CAPITAL = 0.9                           # Proportion in decimal percentage of capital used
BACKTEST_LEVERAGE = 10                   # Using leverage for backtesting to achieve 100% in 6 months
STOP_MULT = 1.5                         # Stop loss distance in ATR multiples — used in risk-based sizing
BACKTEST_MAX_LOSS_PCTG = 0.015

# Trend Break Retest Strategy
MAX_BARS_IN_TRADE = 40
TRAIL_ATR = 2.0
HARD_STOP_ATR = 1.5
