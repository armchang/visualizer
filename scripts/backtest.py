import pandas as pd
import numpy as np

import pandas as pd
import numpy as np

def run(df, config, should_avoid_trade=None, enable_short=True):
    balance = config.STARTING_BALANCE
    last_exit_bar = -config.COOLDOWN_BARS - 1
    position = 0
    entry_price = None
    equity_curve = []
    trades = []
    skipped_trades = []
    current_day = None
    day_start_equity = balance
    trading_paused = False
    growth_cooloff_until = -1

    breakeven_trigger = 1.0
    stop_price = None
    moved_to_breakeven = False

    df = add_trend_filter(df)

    for i in range(len(df)):
        price = df["close"].iloc[i]
        timestamp = df.index[i]
        date = timestamp.date()

        if current_day != date:
            current_day = date
            day_start_equity = balance if position == 0 else equity
            trading_paused = False

        # === Update equity ===
        if position == 0:
            equity = balance
        elif position == 1:
            equity = balance + ((price - entry_price) * quantity)
        elif position == -1:
            equity = balance + ((entry_price - price) * quantity)

        daily_pnl = (equity - day_start_equity) / day_start_equity
        if daily_pnl <= config.DAILY_LOSS_CAP:
            trading_paused = True

        if trading_paused:
            equity_curve.append({"time": timestamp, "equity": equity})
            continue

        atr = df["atr"].iloc[i]

        if position == 1 and not moved_to_breakeven and (price - entry_price) >= atr * breakeven_trigger:
            stop_price = entry_price
            moved_to_breakeven = True

        if position == -1 and not moved_to_breakeven and (entry_price - price) >= atr * breakeven_trigger:
            stop_price = entry_price
            moved_to_breakeven = True

        if position == 1 and moved_to_breakeven and price <= stop_price:
            exit_price = price * (1 - config.EXCHANGE_FEE)
            pnl = (exit_price - entry_price) * quantity
            balance += pnl
            trades.append({"type": "SELL (BREAKEVEN)", "time": timestamp, "price": price, "pnl": pnl, "qty": quantity, "equity": balance})
            position, entry_price, stop_price, quantity = 0, None, None, 0
            moved_to_breakeven = False
            last_exit_bar = i
            continue

        elif position == -1 and moved_to_breakeven and price >= stop_price:
            exit_price = price * (1 + config.EXCHANGE_FEE)
            pnl = (entry_price - exit_price) * quantity
            balance += pnl
            trades.append({"type": "BUY (COVER B/E)", "time": timestamp, "price": price, "pnl": pnl, "qty": quantity, "equity": balance})
            position, entry_price, stop_price, quantity = 0, None, None, 0
            moved_to_breakeven = False
            last_exit_bar = i
            continue

        # === ENTER LONG ===
        if position == 0 and df["buy_signal"].iloc[i] and not df["buy_signal"].iloc[i - 1]:
            if (i - last_exit_bar >= config.COOLDOWN_BARS) and df["trend_up"].iloc[i]:
                if should_avoid_trade and should_avoid_trade(df.iloc[i]):
                    equity_curve.append({"time": timestamp, "equity": equity})
                    skipped_trades.append((timestamp, "BUY"))
                    continue

                if i <= growth_cooloff_until:
                    equity_curve.append({"time": timestamp, "equity": equity})
                    skipped_trades.append((timestamp, "COOL_OFF (post growth)"))
                    continue

                position = 1
                entry_price = price * (1 + config.EXCHANGE_FEE)
                capital_used = balance * config.CAPITAL
                quantity = capital_used / entry_price
                stop_price = None
                moved_to_breakeven = False
                trades.append({"type": "BUY", "time": timestamp, "price": price, "qty": quantity, "equity": balance})

        elif position == 1 and df["sell_signal"].iloc[i]:
            exit_price = price * (1 - config.EXCHANGE_FEE)
            pnl = (exit_price - entry_price) * quantity
            balance += pnl
            trades.append({"type": "SELL", "time": timestamp, "price": price, "pnl": pnl, "qty": quantity, "equity": balance})
            position, entry_price, stop_price, quantity = 0, None, None, 0
            moved_to_breakeven = False
            last_exit_bar = i

        elif position == 0 and df["sell_signal"].iloc[i] and not df["sell_signal"].iloc[i - 1] and enable_short:
            if (i - last_exit_bar >= config.COOLDOWN_BARS) and df["trend_down"].iloc[i]:
                if should_avoid_trade and should_avoid_trade(df.iloc[i]):
                    equity_curve.append({"time": timestamp, "equity": equity})
                    skipped_trades.append((timestamp, "SELL"))
                    continue

                if i <= growth_cooloff_until:
                    equity_curve.append({"time": timestamp, "equity": equity})
                    skipped_trades.append((timestamp, "COOL_OFF (post growth)"))
                    continue

                position = -1
                entry_price = price * (1 - config.EXCHANGE_FEE)
                capital_used = balance * config.CAPITAL
                quantity = capital_used / entry_price
                stop_price = None
                moved_to_breakeven = False
                trades.append({"type": "SELL (SHORT)", "time": timestamp, "price": price, "qty": quantity, "equity": balance})

        elif position == -1 and df["buy_signal"].iloc[i]:
            exit_price = price * (1 + config.EXCHANGE_FEE)
            pnl = (entry_price - exit_price) * quantity
            balance += pnl
            trades.append({"type": "BUY (COVER)", "time": timestamp, "price": price, "pnl": pnl, "qty": quantity, "equity": balance})
            position, entry_price, stop_price, quantity = 0, None, None, 0
            moved_to_breakeven = False
            last_exit_bar = i

        equity_curve.append({"time": timestamp, "equity": equity})

    return pd.DataFrame(equity_curve).set_index("time"), pd.DataFrame(trades)



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