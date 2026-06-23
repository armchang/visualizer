# Trading Strategy Visualizer

A Python backtesting and strategy-research project for OHLCV market data. It
loads candles from PostgreSQL or SQLite, resamples them, computes strategy
signals and risk features, runs long/short backtests, calculates performance
metrics, and opens an interactive Flask chart.

## Important: strategy search arrays

Optimal-settings arrays belong to each individual strategy file—not to
`config/config.py`.

- `scripts/strategies/ema_crossover.py` contains the EMA Crossover
  `search_criteria`.
- `scripts/strategies/trendline_break_retest.py` contains the Trendline Break
  Retest `search_criteria`.
- `scripts/strategies/utbot_strategy.py` does not currently define
  `search_criteria`, so UT Bot can run a normal backtest but cannot run the
  optimal-settings search yet.
- `scripts/strategies/lstm_filter_strategy.py` uses a separately trained model and does
  not participate in the normal parameter-grid search.

The first array controls the candle timeframes included in a search:

```python
search_criteria = {
    "interval": ["15min", "1h", "4h", "1d"],
    "cooldowns": [10, 15],
    "daily_loss_cap": [-0.1, -0.2],
    "atr_periods": [7, 14, 21, 28],
    "cooloff_bars": [14, 21, 28],
    "sensitivity": [2.5],
    "growth": [30],
    "hard_stop_atr": [1.5],
    "max_bars": [40],
    "trail_atr": [2.0],
}
```

The search builds the Cartesian product of these arrays and backtests every
combination. Adding values can therefore increase runtime quickly. Keep the ten
existing keys in their current order because `scripts/search_optimal_settings.py`
currently unpacks each combination positionally.

`RESAMPLE_INTERVAL` in `config/config.py` is the timeframe used for a normal
backtest. During an optimal-settings search, each strategy's `interval` array
temporarily replaces it.

## Features

- Interactive pair selection, defaulting to `BTCUSDT` when Enter is pressed.
- PostgreSQL and SQLite OHLCV data sources.
- EMA Crossover, Trendline Break Retest, UT Bot, and EMA + LSTM Filter
  strategies.
- Strategy-specific parameter-grid searches.
- Long and short backtesting with fees, capital sizing, cooldowns, daily loss
  controls, volatility targeting, and regime features.
- Annual return, volatility, Sharpe ratio, drawdown, win rate, trade count, and
  final-balance reporting.
- Browser chart showing candles, signals, trades, equity, and metrics.
- Optional Excel exports for candles and trades.
- Best-setting logs stored by pair and strategy.

## LSTM prediction module

For a focused explanation of every learning feature, filter, label, split, and
metric, see [`docs/LSTM_LEARNING.md`](docs/LSTM_LEARNING.md).

The LSTM is a **trade filter**, not a replacement trading bot:

```text
EMA strategy proposes BUY or SELL
              |
              v
LSTM checks the last 60 candles
              |
              v
High enough confidence? ---- no ----> skip entry
              |
             yes
              |
              v
        allow the trade
```

EMA Crossover still creates the original entry and exit signals. The LSTM only
confirms new entries. EMA exits and existing stop behavior remain responsible
for closing positions.

### LSTM features

The requested OHLCV, EMA20/50/200, RSI14, ATR14, MACD, volume ratio, and candle
return information is included. Instead of feeding changing absolute BTC price
levels directly to the model, the pipeline converts them into more stable,
normalized features:

- OHLC values relative to the previous close.
- 1-, 3-, and 12-candle logarithmic returns.
- Candle range, body, upper wick, and lower wick percentages.
- Price distance from EMA20, EMA50, and EMA200.
- EMA20/EMA50 and EMA50/EMA200 trend spreads.
- Scaled RSI14.
- ATR14 as a percentage of price.
- MACD, signal, and histogram as percentages of price.
- Volume change and volume relative to its 20-candle average.
- 12- and 48-candle realized volatility.
- Cyclical hour-of-day and day-of-week features.

The final input shape is 60 candles by 28 features. Feature scaling is fitted
only on the chronological training portion, then reused for validation, testing,
and backtesting. This avoids letting future validation or test values influence
the scaler.

### Install the ML dependency

TensorFlow is optional because the regular strategies do not need it:

```bash
python -m pip install -r requirements-ml.txt
```

### Train a model

Train one model for each pair and timeframe you intend to use. The configured
database must already contain that pair.

BTCUSDT 4-hour example:

```bash
python -m ml.train_lstm \
  --pair BTCUSDT \
  --interval 4h \
  --model-path ml/models/btcusdt_4h_lstm.keras
```

If BTCUSDT is stored in SQLite while the normal project configuration points to
PostgreSQL, override the database for training only:

```bash
python -m ml.train_lstm \
  --pair BTCUSDT \
  --interval 4h \
  --model-path ml/models/btcusdt_4h_lstm.keras \
  --database-type sqlite \
  --database-url sqlite:////absolute/path/to/dataspider.db
```

These options do not change `config/config.py` or `config/local_config.py`.

BTCUSDT 1-hour example:

```bash
python -m ml.train_lstm \
  --pair BTCUSDT \
  --interval 1h \
  --model-path ml/models/btcusdt_1h_lstm.keras
```

Training defaults to:

- 60-candle sequences.
- Predicting direction one candle ahead.
- Ignoring future moves smaller than 0.1% during training.
- 70% chronological training data, 15% validation data, and 15% test data.
- Early stopping and learning-rate reduction.
- Class weighting when upward and downward labels are imbalanced.

The command creates two files:

```text
ml/models/btcusdt_4h_lstm.keras
ml/models/btcusdt_4h_lstm.metadata.json
```

The metadata stores the pair, timeframe, sequence length, ordered feature list,
training-only scaler, chronological split timestamps, and held-out test metrics.
Both generated files are ignored by Git. The predictor rejects a model trained
for a different pair or timeframe.

### Run the LSTM filter

With `LSTM_MODEL_PATH = None`, the project automatically looks for:

```text
ml/models/<lowercase-pair>_<interval>_lstm.keras
```

You can instead set an explicit model in `config/config.py` or the ignored
`config/local_config.py`:

```python
LSTM_MODEL_PATH = "ml/models/btcusdt_4h_lstm.keras"
LSTM_BUY_THRESHOLD = 0.60
LSTM_SELL_THRESHOLD = 0.40
LSTM_OUT_OF_SAMPLE_ONLY = True
```

Then run `python _main.py`, choose option **4. EMA + LSTM Entry Filter**, and
answer `n` to optimal-settings search. An EMA buy is accepted when the model's
up probability is at least `0.60`; an EMA short entry is accepted when it is at
most `0.40`. Probabilities in between cause the entry to be skipped.

`LSTM_OUT_OF_SAMPLE_ONLY = True` is the safe default. It suppresses trades
before the held-out test period recorded during training, preventing an
apparently good backtest from including the model's own training candles. Set it
to `False` only when you intentionally need in-sample diagnostics.

The model is experimental and its test accuracy is not evidence of future
profitability. Compare the filtered and unfiltered EMA backtests, include fees,
and retrain with walk-forward periods before considering live use.

### ML implementation files

- `data/market_data_loader.py`: loads and resamples configured database data.
- `indicators/indicators.py`: creates past-only technical indicators.
- `ml/feature_builder.py`: selects features, scales them, and creates sequences.
- `ml/train_lstm.py`: trains, evaluates, and saves the LSTM and metadata.
- `ml/predict_lstm.py`: performs memory-bounded, timestamp-aligned inference.
- `scripts/strategies/lstm_filter_strategy.py`: applies predictions to EMA entries.
- `tests/test_lstm_pipeline.py`: checks features, sequence prediction, and entry
  filtering without requiring TensorFlow.

The sequence and normalization approach follows the official
[TensorFlow time-series tutorial](https://www.tensorflow.org/tutorials/structured_data/time_series)
and [Keras time-series examples](https://keras.io/examples/timeseries/). Models
use the documented [Keras `.keras` save format](https://keras.io/api/models/model_saving_apis/model_saving_and_loading/).
The feature design keeps information derived from raw OHLCV while adding
normalized market-state signals; published experiments indicate that raw OHLCV
can remain competitive and that feature-set choice materially affects financial
sequence models ([OHLCV study](https://arxiv.org/abs/2504.02249),
[feature-engineering study](https://arxiv.org/abs/1904.05384)).

## Requirements and installation

Python 3.11 is the version used by the included setup script.

On Windows PowerShell, the one-command launcher creates or reuses `venv`, then
opens a new shell with the environment activated:

```powershell
.\start_venv.ps1
```

Install or refresh the dependencies before opening the shell:

```powershell
.\start_venv.ps1 -Install
```

Prepare the environment without opening another PowerShell window:

```powershell
.\start_venv.ps1 -Install -NoShell
```

If script execution is blocked, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_venv.ps1
```

Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

On Windows PowerShell, activate it with:

```powershell
.\venv\Scripts\Activate.ps1
```

Install the core runtime packages and the PostgreSQL driver:

```bash
python -m pip install numpy pandas tqdm flask openpyxl
python -m pip install -r requirements.txt
```

SQLite support uses Python's built-in `sqlite3` module. The alternative plotter
modules additionally require `matplotlib`, `plotly`, and `dash` if you use them.

The repository also includes:

- `setup/setup_venv.sh` for a pyenv-based macOS/Linux environment. It recreates
  `venv` and installs its basic packages; run the runtime installation commands
  above afterward.
- `setup/install-pyenv-win.ps1` for installing pyenv-win.

## Database configuration

Database settings use the same `DATABASE_TYPE` and `DATABASE_URL` convention as
DataSpider. Supported database types are `postgresql` and `sqlite`; values such
as `SQLite` are normalized to lowercase.

The database must contain an `ohclv` table with these columns:

```text
open_time, close_time, pair, open, high, low, close, volume
```

### PostgreSQL

Set the connection through environment variables:

```bash
export DATABASE_TYPE=postgresql
export DATABASE_URL=postgresql://user:password@localhost:5432/dataspider
```

PowerShell equivalent:

```powershell
$env:DATABASE_TYPE = "postgresql"
$env:DATABASE_URL = "postgresql://user:password@localhost:5432/dataspider"
```

PostgreSQL connectivity uses `psycopg`, installed through `requirements.txt`.

### SQLite

Use a SQLite URL pointing to the DataSpider database:

```bash
export DATABASE_TYPE=sqlite
export DATABASE_URL=sqlite:////absolute/path/to/dataspider.db
```

A project-relative URL is also accepted:

```text
sqlite:///datas/dataspider.db
```

### Local machine overrides

Machine-specific paths and credentials can be placed in
`config/local_config.py`, which is ignored by Git:

```python
from pathlib import Path

PROJECT_ROOT = Path("/path/to/dataspider")
DATABASE_TYPE = "postgresql"
DATABASE_URL = "postgresql://user:password@localhost:5432/dataspider"
```

Configuration is resolved in layers:

1. `PROJECT_ROOT` uses `DATASPIDER_PROJECT_ROOT`, then falls back to this
   repository's root.
2. `DATABASE_TYPE` and `DATABASE_URL` use environment variables, then their
   defaults.
3. Values present in `config/local_config.py` override those settings.

Do not commit database passwords in `config/config.py`.

## Runtime configuration

The normal backtest defaults live in `config/config.py`. Important settings
include:

- `PAIR_NAME`: defaults to `BTCUSDT`; `TRADING_PAIR` can provide an environment
  default.
- `RESAMPLE_INTERVAL`: normal-backtest candle timeframe.
- `STRATEGY`: default strategy module.
- `TABLE_NAME`: OHLCV database table.
- `YEARS_BACKTRACK`: amount of recent history included.
- `STARTING_BALANCE`, `EXCHANGE_FEE`, and `CAPITAL`: portfolio assumptions.
- `DAILY_LOSS_CAP`, `COOLDOWN_BARS`, and `COOL_OFF_BARS_AFTER_GROWTH`: trading
  controls.
- `ATR_PERIOD`, `SENSITIVITY`, `HARD_STOP_ATR`, `TRAIL_ATR`, and
  `MAX_BARS_IN_TRADE`: strategy and risk parameters.
- `TARGET_VOL`, `HORIZON_DAYS`, and `MAX_LEVERAGE`: volatility targeting.
- `LSTM_MODEL_PATH`, `LSTM_BUY_THRESHOLD`, `LSTM_SELL_THRESHOLD`, and
  `LSTM_OUT_OF_SAMPLE_ONLY`: optional LSTM entry-filter configuration.

The pair entered at startup overrides `PAIR_NAME` for that run. Pressing Enter
without typing a pair uses the configured default.

## Running the project

Activate the virtual environment, then run:

```bash
python _main.py
```

The program will:

1. Ask for a trading pair. Press Enter for `BTCUSDT`.
2. Ask you to choose EMA Crossover, Trendline Break Retest, UT Bot, or the EMA
   + LSTM Entry Filter.
3. Ask whether to search for optimal settings.
4. Run the selected backtest or parameter search.
5. Optionally export candles and trades to Excel after a short prompt.
6. Start the Flask chart server and print its local URL.

When a normal backtest is selected, the application first looks for
`logs/best_configs_<PAIR>_<STRATEGY>.log`. If no valid saved configuration is
available, it falls back to `config/config.py`.

## Outputs

- `logs/`: saved best configurations by pair and strategy.
- `scripts/tracing/files/`: timestamped Excel exports, split at one million
  rows per file.
- Browser chart: OHLCV candles, signals, trade markers, equity curve, drawdown
  markers, and performance metrics.

## Project structure

```text
_main.py                         Interactive entry point
config/config.py                 Database and normal-backtest defaults
config/local_config.py           Ignored machine-specific overrides
data/market_data_loader.py       Shared database-to-candle loader
indicators/indicators.py         LSTM technical and normalized features
ml/feature_builder.py            Feature selection, scaling, and sequences
ml/train_lstm.py                 Chronological LSTM training command
ml/predict_lstm.py               Saved-model inference
ml/models/                       Generated models and metadata
scripts/strategies/lstm_filter_strategy.py  EMA entry filter using LSTM confidence
backtest/engine.py               Public wrapper for the active engine
visualization/chart.py           Public wrapper for the browser chart
scripts/engine.py                Data, strategy, risk, backtest, and metric flow
scripts/fetch.py                 PostgreSQL/SQLite loading and resampling
scripts/backtest.py              Active backtesting loop
scripts/search_optimal_settings.py  Parameter-grid search
scripts/strategies/              Strategy implementations and search arrays
scripts/risk_controls/           Volatility and regime features
scripts/plotters/                Flask, Plotly/Dash, and Matplotlib plotters
scripts/tracing/                 Screen and Excel output helpers
scripts/util/                    Logging, grid, countdown, and backtest helpers
logs/                            Best-setting logs and pattern rules
docs/                            Additional strategy documentation
setup/                           Environment setup helpers
start_venv.ps1                   PowerShell virtual-environment launcher
tests/test_lstm_pipeline.py      TensorFlow-free ML pipeline tests
```

Files such as `backtest_old.py`, `backtest_with_tp.py`, and
`backtest_plugnplay.py` are retained experiments; the active engine imports
`scripts/backtest.py`.
