import pandas as pd

def add_trend_filter(df):
    df["ema50"] = df["close"].ewm(span=50).mean()
    df["ema200"] = df["close"].ewm(span=200).mean()
    df["trend_up"] = df["ema50"] > df["ema200"]
    df["trend_down"] = df["ema50"] < df["ema200"]
    return df


def add_atr(df, period=14):
    high = df["high"]
    low = df["low"]
    close = df["close"]
    
    hl = high - low
    hc = (high - close.shift()).abs()
    lc = (low - close.shift()).abs()

    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df["atr"] = tr.rolling(period).mean()

    return df

def is_short_trap_candle(df, i):
    if i < 2:
        return False  # not enough candles to compare with previous low

    open_ = df["open"].iloc[i]
    close = df["close"].iloc[i]
    low = df["low"].iloc[i]
    high = df["high"].iloc[i]
    prev_low = df["low"].iloc[i - 1]

    body = abs(close - open_)
    lower_wick = min(open_, close) - low
    upper_wick = high - max(open_, close)
    candle_range = high - low

    return (
        close < open_ and            # bullish close
        lower_wick > 2 * body and    # stricter: long lower wick
        low < prev_low and           # makes new low
        body > 0.1 * candle_range    # avoid doji and >= 30% of range is a decent body
    )


def should_avoid_trade(row):
    """
    Rule-based trade filter from pattern analysis.
    Returns True if trade should be skipped.
    """
    try:
        return (
            abs(row["dist_from_ema50_pct"]) < 0.005 or
            60 <= row["rsi14"] < 70 or
            row.get("bbw20_bin") in {"Q3", "Q4"} or
            row.get("chop14_bin") in {"Q3", "Q4"} or
            row.get("atr_pct_bin") in {"<=10%", "20-50%"} or
            row.get("adx14_bin") in {"20-40", ">=40"} or
            40 <= row["rsi14"] <= 60 or
            row.get("hour_bin") in {"8-12", "12-16"} or
            row.get("dow") in {4, 6} or
            row["is_sideways"] == 0
        )
    except Exception as e:
        print(f"[should_avoid_trade] Error: {e}")
        return False
    
def add_emas(df, spans=[20, 50, 200]):
    for span in spans:
        df[f"ema{span}"] = df["close"].ewm(span=span).mean()
    return df

def fix_entered_trades(trades_df, df):
        # === Protect against empty trades_df ===
    if trades_df.empty or "time" not in trades_df.columns:
        trades_df = pd.DataFrame(columns=["type", "time", "price", "pnl", "leverage"])
    else:
        trades_df = trades_df.sort_values("time")
        trades_df["time"] = pd.to_datetime(trades_df["time"])

        # ✅ Merge candle stats into trades
        trades_df = pd.merge_asof(
            trades_df,
            df[["candle_size", "candle_body", "total_wick"]],
            left_on="time",
            right_index=True,
            direction="backward"
        )
        
    return trades_df