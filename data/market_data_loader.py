"""Load and resample OHLCV data using the project's configured database."""

import pandas as pd

from config import config
from scripts import fetch


def load_market_data(pair=None, interval=None, database_type=None, database_url=None):
    """Return OHLCV candles for one pair at the requested interval."""
    pair = (pair or config.PAIR_NAME).strip().upper()
    interval = interval or config.RESAMPLE_INTERVAL
    frame = load_ohlcv_from_db(pair, database_type, database_url)
    return resample_ohlcv(frame, interval)


def load_ohlcv_from_db(pair=None, database_type=None, database_url=None):
    """Return the database's raw OHLCV candles without resampling them."""
    pair = (pair or config.PAIR_NAME).strip().upper()
    database_type = (database_type or config.DATABASE_TYPE).lower()
    database_url = database_url or config.DATABASE_URL

    return fetch.get_ohlcv_data(
        database_type,
        database_url,
        config.TABLE_NAME,
        pair,
    )


def resample_ohlcv(frame, interval, source_interval=None, drop_incomplete=False):
    """Aggregate OHLCV candles into a larger pandas-compatible interval."""
    resampled = frame.resample(interval).agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    ).dropna()

    if drop_incomplete:
        if not source_interval:
            raise ValueError("source_interval is required when drop_incomplete=True")
        target_duration = pd.Timedelta(interval)
        source_duration = pd.Timedelta(source_interval)
        if target_duration % source_duration:
            raise ValueError("interval must be an exact multiple of source_interval")
        expected_rows = int(target_duration / source_duration)
        rows_per_candle = frame["close"].resample(interval).count()
        resampled = resampled.loc[rows_per_candle >= expected_rows]

    resampled["open_time"] = resampled.index
    return resampled
