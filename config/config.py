import os
from pathlib import Path

# Resolve the project root directory
PROJECT_ROOT = Path("/Users/user/Projects/dataspider")

# Absolute path to the SQLite database
DATABASE_PATH = PROJECT_ROOT / 'datas' / 'dataspider.db'

PAIR_NAME = os.environ.get("TRADING_PAIR", "BTCUSDT")
DAILY_LOSS_CAP = -0.1
COOLDOWN_BARS = 25
RESAMPLE_INTERVAL = "4h"
ATR_PERIOD = 21

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
