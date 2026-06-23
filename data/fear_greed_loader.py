"""Load and align daily Fear & Greed values with candle data."""

from pathlib import Path

import pandas as pd


FEAR_GREED_FEATURE_COLUMNS = [
    "fear_greed_scaled",
    "fear_greed_change_1",
    "fear_greed_change_7",
    "fear_greed_extreme_fear",
    "fear_greed_extreme_greed",
]


def load_fear_greed_csv(path):
    """Load a CSV with date/timestamp and value columns.

    Expected columns:
    - `date`, `timestamp`, or `time`
    - `value`

    `value` should be the standard Crypto Fear & Greed Index from 0 to 100.
    """
    path = Path(path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Fear & Greed CSV not found: {path}")

    data = pd.read_csv(path)
    timestamp_column = next(
        (column for column in ("timestamp", "date", "time") if column in data.columns),
        None,
    )
    if timestamp_column is None:
        raise ValueError("Fear & Greed CSV must contain a date, timestamp, or time column")
    if "value" not in data.columns:
        raise ValueError("Fear & Greed CSV must contain a value column")

    result = data[[timestamp_column, "value"]].copy()
    result[timestamp_column] = pd.to_datetime(result[timestamp_column], utc=True)
    result["value"] = pd.to_numeric(result["value"], errors="coerce")
    result = result.dropna(subset=[timestamp_column, "value"])
    result = result.sort_values(timestamp_column).drop_duplicates(timestamp_column, keep="last")
    result = result.set_index(timestamp_column)
    result.index.name = "timestamp"
    return result


def add_fear_greed_features(frame, fear_greed):
    """Merge daily Fear & Greed data onto candles without looking ahead."""
    if isinstance(fear_greed, (str, Path)):
        fear_greed = load_fear_greed_csv(fear_greed)
    if fear_greed is None or fear_greed.empty:
        raise ValueError("Fear & Greed data is empty")

    result = frame.copy()
    candle_index = pd.DatetimeIndex(result.index)
    candle_utc = candle_index.tz_localize("UTC") if candle_index.tz is None else candle_index.tz_convert("UTC")

    sentiment = fear_greed.copy()
    sentiment.index = pd.DatetimeIndex(sentiment.index)
    sentiment.index = (
        sentiment.index.tz_localize("UTC")
        if sentiment.index.tz is None
        else sentiment.index.tz_convert("UTC")
    )
    sentiment.index.name = "timestamp"
    sentiment = sentiment.sort_index()
    sentiment["fear_greed_scaled"] = (sentiment["value"] - 50.0) / 50.0
    sentiment["fear_greed_change_1"] = sentiment["value"].diff() / 100.0
    sentiment["fear_greed_change_7"] = sentiment["value"].diff(7) / 100.0
    sentiment["fear_greed_extreme_fear"] = (sentiment["value"] <= 25.0).astype("float32")
    sentiment["fear_greed_extreme_greed"] = (sentiment["value"] >= 75.0).astype("float32")

    aligned = pd.merge_asof(
        pd.DataFrame({"_candle_time": candle_utc}).sort_values("_candle_time"),
        sentiment[FEAR_GREED_FEATURE_COLUMNS].reset_index().rename(columns={"timestamp": "_sentiment_time"}),
        left_on="_candle_time",
        right_on="_sentiment_time",
        direction="backward",
    )
    aligned.index = result.index
    for column in FEAR_GREED_FEATURE_COLUMNS:
        result[column] = aligned[column].astype("float32")
    return result
