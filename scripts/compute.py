import pandas as pd
import numpy as np
from config import config

def get_src(df, use_heikin_ashi):
    if use_heikin_ashi:
        return (df["open"] + df["high"] + df["low"] + df["close"]) / 4          # Heikin-Ashi source calculation    
    return df["close"]                                                          # Standard close price as source     

def get_atr(df, period):
    high_low = df["high"] - df["low"]
    high_close = np.abs(df["high"] - df["close"].shift())                       # Absolute difference between current high and previous close
    low_close = np.abs(df["low"] - df["close"].shift())                         # Absolute difference between current low and previous close
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)       # True Range (TR) calculation across high, low, and previous close prices
    return tr.rolling(period).mean()                                            # Calculate ATR using rolling mean of True Range (TR) based on the specified period

def get_atr_wilder(df, period=14):
    high_low = df["high"] - df["low"]
    high_close = np.abs(df["high"] - df["close"].shift())
    low_close = np.abs(df["low"] - df["close"].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    return atr

def get_stop_distance(atr, sensitivity):
    stop_distance = sensitivity * atr                                           # Calculate stop distance based on ATR and sensitivity
    first_valid = stop_distance.first_valid_index()                             # Get the first non-NaN value
    if (first_valid is not None):
        first_value = stop_distance.loc[first_valid]
        stop_distance = stop_distance.fillna(first_value)                       # Fill NaN values with the first valid value to avoid NaNs
    return stop_distance

def get_trailing_stop(df):  
    src = df["src"]
    trailing_stop = [np.nan]
    for i in range(1, len(df)):
        if not np.isnan(trailing_stop[-1]):                                     # If the last trailing stop is not NaN, use it
            prev_stop = trailing_stop[-1]
        else:
            prev_stop = src.iloc[i] - df["stop_distance"].iloc[i]               # Initialize previous stop if NaN
        if src.iloc[i] > prev_stop and src.iloc[i - 1] > prev_stop:             # Price remains above previous trailing stop
            trailing_stop.append(max(prev_stop, src.iloc[i] - df["stop_distance"].iloc[i]))
        elif src.iloc[i] < prev_stop and src.iloc[i - 1] < prev_stop:           # Price remains below previous trailing stop
            trailing_stop.append(min(prev_stop, src.iloc[i] + df["stop_distance"].iloc[i]))
        elif src.iloc[i] > prev_stop:
            trailing_stop.append(src.iloc[i] - df["stop_distance"].iloc[i])           # New trailing stop when price crosses above previous stop
        else:
            trailing_stop.append(src.iloc[i] + df["stop_distance"].iloc[i])           # New trailing stop when price crosses below previous stop
    return trailing_stop

def get_ema(src, span):
    return src.ewm(span=span).mean()                                            # Calculate Exponential Moving Average (EMA) based on the specified span

def get_buy_signals(src, df):
    cross_up = (df["ema"] > df["trailing_stop"]) & (df["ema"].shift() <= df["trailing_stop"].shift())
    return (src > df["trailing_stop"]) & cross_up                               # Buy signal when price crosses above trailing stop

def get_sell_signals(src, df): 
    cross_dn = (df["ema"] < df["trailing_stop"]) & (df["ema"].shift() >= df["trailing_stop"].shift())
    return (src < df["trailing_stop"]) & cross_dn                               # Sell signal when price crosses below trailing stop

def get_signals(df, atr_period, sensitivity, use_heikin_ashi):
    df["src"] = get_src(df, use_heikin_ashi)
    df["atr"] = get_atr_wilder(df, atr_period)
    df["atr"] = df["atr"].ffill().bfill()
    df["stop_distance"] = get_stop_distance(df["atr"], sensitivity)
    df["trailing_stop"] = get_trailing_stop(df)
    df["ema"] = get_ema(df["src"], span=config.EMA_SMOOTHING)
    df["buy_signal"] = get_buy_signals(df["src"], df)
    df["sell_signal"] = get_sell_signals(df["src"], df)
    df["sma20"] = df["close"].rolling(20).mean().ffill().bfill()
    df["sma50"] = df["close"].rolling(50).mean().ffill().bfill()
    df["sma100"] = df["close"].rolling(100).mean().ffill().bfill()
    df["sma200"] = df["close"].rolling(200).mean().ffill().bfill()

    # Combine into numeric signal for volatility targeting
    df["signal"] = 0
    df.loc[df["buy_signal"], "signal"] = 1
    df.loc[df["sell_signal"], "signal"] = -1

    return df


def add_candle_stats(df):
    df["candle_size"] = df["high"] - df["low"]
    df["candle_body"] = (df["close"] - df["open"]).abs()
    df["total_wick"] = df["candle_size"] - df["candle_body"]
    return df