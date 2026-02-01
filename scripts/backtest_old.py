import pandas as pd
import numpy as np
import scripts.util.backtest_util as bu

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

    df = bu.add_trend_filter(df)
    df = bu.add_emas(df, [20, 50, 200])

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

        # === Daily loss cap checking ====
        daily_pnl = (equity - day_start_equity) / day_start_equity
        if daily_pnl <= config.DAILY_LOSS_CAP:
            trading_paused = True

        if trading_paused:
            equity_curve.append({"time": timestamp, "equity": equity})
            continue

        atr = df["atr"].iloc[i]

        # === Breakeven trigger ===
        if position == 1 and not moved_to_breakeven and (price - entry_price) >= atr * breakeven_trigger:
            stop_price = entry_price
            moved_to_breakeven = True
        if position == -1 and not moved_to_breakeven and (entry_price - price) >= atr * breakeven_trigger:
            stop_price = entry_price
            moved_to_breakeven = True

        # === Stop hit ===
        if position == 1 and moved_to_breakeven and price <= stop_price:
            exit_price = price * (1 - config.EXCHANGE_FEE)
            pnl = (exit_price - entry_price) * quantity
            balance += pnl
            trades.append({"type": "SELL (BREAKEVEN)", "time": timestamp, "price": price, "pnl": pnl, "qty": quantity, "equity": balance})
            position, entry_price, stop_price, quantity = 0, None, None, 0
            moved_to_breakeven = False
            last_exit_bar = i
            continue

        if position == -1 and moved_to_breakeven and price >= stop_price:
            exit_price = price * (1 + config.EXCHANGE_FEE)
            pnl = (entry_price - exit_price) * quantity
            balance += pnl
            trades.append({"type": "BUY (COVER B/E)", "time": timestamp, "price": price, "pnl": pnl, "qty": quantity, "equity": balance})
            position, entry_price, stop_price, quantity = 0, None, None, 0
            moved_to_breakeven = False
            last_exit_bar = i
            continue

        # === Smarter Long Exit ===
        if position == 1:
            if df["sell_signal"].iloc[i] and price < df["ema20"].iloc[i]:
                exit_price = price * (1 - config.EXCHANGE_FEE)
                pnl = (exit_price - entry_price) * quantity
                balance += pnl
                trades.append({"type": "SELL", "time": timestamp, "price": price, "pnl": pnl, "qty": quantity, "equity": balance})
                position, entry_price, stop_price, quantity = 0, None, None, 0
                moved_to_breakeven = False
                last_exit_bar = i

        # === Smarter Short Exit ===
        elif position == -1:
            if df["buy_signal"].iloc[i] and price > df["ema20"].iloc[i]:
                exit_price = price * (1 + config.EXCHANGE_FEE)
                pnl = (entry_price - exit_price) * quantity
                balance += pnl
                trades.append({"type": "BUY (COVER)", "time": timestamp, "price": price, "pnl": pnl, "qty": quantity, "equity": balance})
                position, entry_price, stop_price, quantity = 0, None, None, 0
                moved_to_breakeven = False
                last_exit_bar = i

        # === Enter Long ===
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

        # === Enter Short ===
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

        equity_curve.append({"time": timestamp, "equity": equity})

    return pd.DataFrame(equity_curve).set_index("time"), pd.DataFrame(trades)