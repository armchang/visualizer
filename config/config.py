import os
from pathlib import Path

# Resolve the project root directory
PROJECT_ROOT = Path("D:/Projects/Python/dataspider")

# Absolute path to the SQLite database
DATABASE_PATH = PROJECT_ROOT / 'datas' / 'dataspider.db'

PAIR_NAME = os.environ.get("TRADING_PAIR", "ETHUSDT")
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
