"""Build leak-resistant LSTM features and chronological sequences."""

import numpy as np

from data.fear_greed_loader import FEAR_GREED_FEATURE_COLUMNS
from indicators.indicators import add_lstm_indicators


DEFAULT_FEATURE_COLUMNS = [
    "open_to_prev_close",
    "high_to_prev_close",
    "low_to_prev_close",
    "log_return_1",
    "log_return_3",
    "log_return_12",
    "range_pct",
    "body_pct",
    "upper_wick_pct",
    "lower_wick_pct",
    "ema20_distance",
    "ema50_distance",
    "ema200_distance",
    "ema20_ema50_spread",
    "ema50_ema200_spread",
    "rsi14_scaled",
    "atr14_pct",
    "macd_pct",
    "macd_signal_pct",
    "macd_histogram_pct",
    "volume_log_change",
    "volume_ratio_20",
    "realized_volatility_12",
    "realized_volatility_48",
    "hour_sin",
    "hour_cos",
    "weekday_sin",
    "weekday_cos",
]


def feature_columns_for_training(include_fear_greed=False):
    """Return the ordered LSTM feature list for this training run."""
    columns = list(DEFAULT_FEATURE_COLUMNS)
    if include_fear_greed:
        columns.extend(FEAR_GREED_FEATURE_COLUMNS)
    return columns


def build_feature_frame(frame, feature_columns=None):
    """Return a clean feature frame while preserving its timestamp index."""
    feature_columns = list(feature_columns or DEFAULT_FEATURE_COLUMNS)
    enriched = add_lstm_indicators(frame)
    missing = set(feature_columns).difference(enriched.columns)
    if missing:
        raise ValueError(f"Unknown feature columns: {', '.join(sorted(missing))}")
    return enriched[feature_columns].dropna().astype("float32")


def fit_standardizer(training_values):
    """Fit a simple z-score scaler on training values only."""
    mean = np.asarray(training_values, dtype=np.float64).mean(axis=0)
    scale = np.asarray(training_values, dtype=np.float64).std(axis=0)
    scale[scale < 1e-12] = 1.0
    return mean.astype("float32"), scale.astype("float32")


def standardize(values, mean, scale):
    return ((np.asarray(values, dtype="float32") - mean) / scale).astype("float32")


def build_targets(close, prediction_horizon=1, minimum_return=0.0):
    """Classify whether the future close rises after the prediction horizon."""
    if prediction_horizon < 1:
        raise ValueError("prediction_horizon must be at least 1")
    if prediction_horizon >= len(close):
        raise ValueError("prediction_horizon must be shorter than the price history")
    future_return = close.shift(-prediction_horizon) / close - 1.0
    targets = (future_return > 0.0).astype("float32")
    if minimum_return > 0.0:
        targets = targets.where(future_return.abs() >= minimum_return)
    targets = targets.iloc[:-prediction_horizon]
    return targets


def build_sequences(values, targets, sequence_length):
    """Create (samples, timesteps, features) arrays ending at each target row."""
    values = np.asarray(values, dtype="float32")
    targets = np.asarray(targets, dtype="float32")
    if len(values) != len(targets):
        raise ValueError("Feature and target lengths must match")
    if sequence_length < 2:
        raise ValueError("sequence_length must be at least 2")
    if len(values) < sequence_length:
        return (
            np.empty((0, sequence_length, values.shape[1]), dtype="float32"),
            np.empty((0,), dtype="float32"),
        )

    sequences = np.stack(
        [values[end - sequence_length + 1 : end + 1] for end in range(sequence_length - 1, len(values))]
    )
    return sequences, targets[sequence_length - 1 :]
