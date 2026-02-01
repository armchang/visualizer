# scripts/backtest_new.py

import pandas as pd
from scripts.state import BacktestState
import scripts.util.backtest_util as bu


def run(df, config, strategy, should_avoid_trade=None, enable_short=True):

    # Add strategy
    state = BacktestState(config)
    df = strategy.prepare(df, config)

    df = bu.add_trend_filter(df)
    df = bu.add_emas(df, [20, 50, 200])

    for i in range(len(df)):
        row = df.iloc[i]
        price = row.close
        timestamp = df.index[i]
        date = timestamp.date()
        
        # Reset daily stats
        if state.current_day != date:
            state.current_day = date
            state.day_start_equity = state.balance if state.position == 0 else state.equity
            state.trading_paused = False

        # Update equity
        if state.position == 0:
            state.equity = state.balance
        elif state.position == 1:
            state.equity = state.balance + ((price - state.entry_price) * state.quantity)
        else:
            state.equity = state.balance + ((state.entry_price - price) * state.quantity)

        # Daily loss cap
        daily_pnl = (state.equity - state.day_start_equity) / state.day_start_equity
        if daily_pnl <= config.DAILY_LOSS_CAP:
            state.trading_paused = True

        if state.trading_paused:
            state.equity_curve.append({"time": timestamp, "equity": state.equity})
            continue

        # --- EXIT LOGIC ---
        exit_done = strategy.check_exit(i, row, state, df, config)
        if exit_done:
            state.equity_curve.append({"time": timestamp, "equity": state.equity})
            continue

        # --- ENTRY LOGIC ---
        strategy.check_entry(i, row, state, df, config, enable_short, should_avoid_trade)

        state.equity_curve.append({"time": timestamp, "equity": state.equity})

    return (
        pd.DataFrame(state.equity_curve).set_index("time"),
        pd.DataFrame(state.trades)
    )
