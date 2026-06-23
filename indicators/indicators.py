"""Past-only technical indicators for the LSTM input pipeline."""

import numpy as np
import pandas as pd


def _wilder_rsi(close, period=14):
    change = close.diff()
    gain = change.clip(lower=0.0)
    loss = -change.clip(upper=0.0)
    average_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    average_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    relative_strength = average_gain / average_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + relative_strength))
    rsi = rsi.mask(average_loss.eq(0.0) & average_gain.gt(0.0), 100.0)
    return rsi.mask(average_loss.eq(0.0) & average_gain.eq(0.0), 50.0)


def _wilder_atr(frame, period=14):
    previous_close = frame["close"].shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False).mean()


def add_lstm_indicators(frame):
    """Add normalized trend, momentum, volatility, volume, and time features."""
    required = {"open", "high", "low", "close", "volume"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing OHLCV columns: {', '.join(sorted(missing))}")

    result = frame.copy()
    close = result["close"].astype(float)
    previous_close = close.shift(1)
    safe_close = close.replace(0.0, np.nan)
    safe_previous_close = previous_close.replace(0.0, np.nan)
    safe_open = result["open"].astype(float).replace(0.0, np.nan)

    for period in (20, 50, 200):
        result[f"ema{period}"] = close.ewm(span=period, adjust=False).mean()

    result["rsi14"] = _wilder_rsi(close, 14)
    result["atr14"] = _wilder_atr(result, 14)

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    result["macd"] = ema12 - ema26
    result["macd_signal"] = result["macd"].ewm(span=9, adjust=False).mean()
    result["macd_histogram"] = result["macd"] - result["macd_signal"]

    # Normalized OHLC information is more stable across changing price levels
    # than feeding absolute BTC prices directly into the network.
    result["open_to_prev_close"] = result["open"] / safe_previous_close - 1.0
    result["high_to_prev_close"] = result["high"] / safe_previous_close - 1.0
    result["low_to_prev_close"] = result["low"] / safe_previous_close - 1.0
    result["log_return_1"] = np.log(close / safe_previous_close)
    result["log_return_3"] = np.log(close / close.shift(3).replace(0.0, np.nan))
    result["log_return_12"] = np.log(close / close.shift(12).replace(0.0, np.nan))

    result["range_pct"] = (result["high"] - result["low"]) / safe_close
    result["body_pct"] = (result["close"] - result["open"]) / safe_open
    candle_top = result[["open", "close"]].max(axis=1)
    candle_bottom = result[["open", "close"]].min(axis=1)
    result["upper_wick_pct"] = (result["high"] - candle_top) / safe_close
    result["lower_wick_pct"] = (candle_bottom - result["low"]) / safe_close

    result["ema20_distance"] = close / result["ema20"] - 1.0
    result["ema50_distance"] = close / result["ema50"] - 1.0
    result["ema200_distance"] = close / result["ema200"] - 1.0
    result["ema20_ema50_spread"] = result["ema20"] / result["ema50"] - 1.0
    result["ema50_ema200_spread"] = result["ema50"] / result["ema200"] - 1.0

    result["rsi14_scaled"] = (result["rsi14"] - 50.0) / 50.0
    result["atr14_pct"] = result["atr14"] / safe_close
    result["macd_pct"] = result["macd"] / safe_close
    result["macd_signal_pct"] = result["macd_signal"] / safe_close
    result["macd_histogram_pct"] = result["macd_histogram"] / safe_close

    volume = result["volume"].astype(float).clip(lower=0.0)
    result["volume_log_change"] = np.log1p(volume).diff()
    result["volume_ratio_20"] = volume / volume.rolling(20).mean().replace(0.0, np.nan)
    result["realized_volatility_12"] = result["log_return_1"].rolling(12).std()
    result["realized_volatility_48"] = result["log_return_1"].rolling(48).std()

    timestamps = pd.DatetimeIndex(result.index)
    result["hour_sin"] = np.sin(2.0 * np.pi * timestamps.hour / 24.0)
    result["hour_cos"] = np.cos(2.0 * np.pi * timestamps.hour / 24.0)
    result["weekday_sin"] = np.sin(2.0 * np.pi * timestamps.dayofweek / 7.0)
    result["weekday_cos"] = np.cos(2.0 * np.pi * timestamps.dayofweek / 7.0)

    return result.replace([np.inf, -np.inf], np.nan)
