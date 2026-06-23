# ✅ UPDATED: `ema_crossover.py`

import scripts.util.backtest_util as bu
from scripts.classes.basestrategy import BaseStrategy
from scripts.compute import get_atr, get_signals
import numpy as np
import pandas as pd

search_criteria = {
    "interval": ["15min", "1h", "4h", "1d"],
    "cooldowns": [10, 15],
    "daily_loss_cap": [-0.1, -0.2],
    "atr_periods": [7, 14, 21, 28],
    "cooloff_bars": [14, 21, 28],
    "sensitivity": [2.5],
    "growth": [30],
    "hard_stop_atr" : [1.5],
    "max_bars" : [40],
    "trail_atr" : [2.0]
}


class EMACrossover(BaseStrategy):

    def prepare(self, df, config):
        df = bu.add_trend_filter(df)
        df = bu.add_emas(df, [20, 50])
        return df

    def should_skip(self, i, row, state, config):
        current_date = row.name.date()
        if i - state.last_exit_bar < config.COOLDOWN_BARS:
            return True
        if hasattr(state, "trading_disabled_dates") and current_date in state.trading_disabled_dates:
            if getattr(config, "DEBUG", False):
                print(f"Daily loss cap reached for {current_date}.")
            return True
        return False

    def reset_position(self, state, i):
        state.position = 0
        state.entry_price = None
        state.stop_price = None
        state.quantity = 0
        state.moved_to_breakeven = False
        state.last_exit_bar = i
        
    def check_entry(self, i, row, state, df, config, enable_short=True, should_avoid=None):
        price = row["close"]
        time = row.name

        if state.position != 0:
            return  # Avoid re-entering while in a position

        # LONG
        if bool(row["buy_signal"]):
            entry_price = price * (1 + config.EXCHANGE_FEE)
            capital_used = state.balance * config.CAPITAL
            state.quantity = capital_used / entry_price
            state.position = 1
            state.entry_price = entry_price
            state.stop_price = None
            state.moved_to_breakeven = False
            state.trades.append({
                "type": "BUY", 
                "time": time, 
                "price": price,
                "qty": state.quantity, 
                "equity": state.balance, 
                "pnl": 0.0
            })

        # SHORT
        elif bool(row["sell_signal"]) and getattr(config, "ENABLE_SHORT", True):
            entry_price = price * (1 - config.EXCHANGE_FEE)
            capital_used = state.balance * config.CAPITAL
            state.quantity = capital_used / entry_price
            state.position = -1
            state.entry_price = entry_price
            state.stop_price = None
            state.moved_to_breakeven = False
            state.trades.append({
                "type": "SELL (SHORT)", 
                "time": time, 
                "price": price,
                "qty": state.quantity, 
                "equity": state.balance,
                "pnl": 0.0
            })

    def check_exit(self, i, row, state, df, config):
        price = row["close"]
        time = row.name

        if state.position == 1 and bool(row["sell_signal"]):
            exit_price = price * (1 - config.EXCHANGE_FEE)
            pnl = (exit_price - state.entry_price) * state.quantity
            state.balance += pnl
            state.trades.append({
                "type": "SELL", 
                "time": time, 
                "price": price,
                "pnl": pnl, 
                "qty": state.quantity, 
                "equity": state.balance
            })
            self.reset_position(state, i)

        elif state.position == -1 and bool(row["buy_signal"]):
            exit_price = price * (1 + config.EXCHANGE_FEE)
            pnl = (state.entry_price - exit_price) * state.quantity
            state.balance += pnl
            state.trades.append({
                "type": "BUY (COVER)", 
                "time": time, 
                "price": price,
                "pnl": pnl, 
                "qty": state.quantity, 
                "equity": state.balance
            })
            self.reset_position(state, i)

    def check_stop(self, i, row, state, config):
        price = row["close"]
        time = row.name
        atr = row.get("atr", None)

        if pd.isna(atr):
            return

        if state.position == 1 and not state.moved_to_breakeven and (price - state.entry_price) >= atr:
            state.stop_price = state.entry_price
            state.moved_to_breakeven = True

        elif state.position == -1 and not state.moved_to_breakeven and (state.entry_price - price) >= atr:
            state.stop_price = state.entry_price
            state.moved_to_breakeven = True

        elif state.position == 1 and state.moved_to_breakeven and price <= state.stop_price:
            pnl = (price * (1 - config.EXCHANGE_FEE) - state.entry_price) * state.quantity
            state.balance += pnl
            state.trades.append({
                "type": "SELL (BREAKEVEN)", 
                "time": time,
                "price": price, 
                "pnl": pnl, 
                "qty": state.quantity, 
                "equity": state.balance
            })
            self.reset_position(state, i)

        elif state.position == -1 and state.moved_to_breakeven and price >= state.stop_price:
            pnl = (state.entry_price - price * (1 + config.EXCHANGE_FEE)) * state.quantity
            state.balance += pnl
            state.trades.append({
                "type": "BUY (COVER B/E)", 
                "time": time,
                "price": price, 
                "pnl": pnl, 
                "qty": state.quantity, 
                "equity": state.balance
            })
            self.reset_position(state, i)

    # ==========================================================
    # COMPUTE SIGNALS
    # ==========================================================
    def compute_signals(self, df, config):
        df = df.copy()

        # Preparations
        df = self.prepare(df, config)

        # 🔥 Core logic
        df = get_signals(df, config.ATR_PERIOD, config.SENSITIVITY, config.USE_HEIKIN_ASHI)

        return df


Strategy = EMACrossover
