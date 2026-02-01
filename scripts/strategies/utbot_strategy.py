# scripts/strategies/utbot_strategy.py

from scripts.strategies.base_strategy import BaseStrategy
from scripts.compute import (
    get_src,
    get_atr_wilder,
    get_stop_distance,
    get_trailing_stop,
    get_ema,
    get_buy_signals,
    get_sell_signals
)

class UTBotStrategy(BaseStrategy):
    plot_columns = ["trailing_stop"]
    
    def compute_signals(self, df, config):
        df = df.copy()

        df["src"] = get_src(df, config.USE_HEIKIN_ASHI)
        df["atr"] = get_atr_wilder(df, config.ATR_PERIOD)
        df["atr"] = df["atr"].ffill().bfill()

        df["stop_distance"] = get_stop_distance(df["atr"], config.SENSITIVITY)
        df["trailing_stop"] = get_trailing_stop(df)

        df["ema"] = get_ema(df["src"], span=config.EMA_SMOOTHING)

        df["ut_buy_signal"] = get_buy_signals(df["src"], df)
        df["ut_sell_signal"] = get_sell_signals(df["src"], df)

        # SMAs (used by exits / filters)
        for p in (20, 50, 100, 200):
            df[f"sma{p}"] = df["close"].rolling(p).mean().ffill().bfill()

        # Numeric signal (used by volatility targeting)
        df["signal"] = 0
        df.loc[df["ut_buy_signal"], "signal"] = 1
        df.loc[df["ut_sell_signal"], "signal"] = -1

        return df
    
    def check_exit(self, i, row, state, df, config):
        """Handles breakeven stops, smart exits, and stop hits."""
        price = row.close
        timestamp = df.index[i]
        atr = row.atr

        # --- Breakeven trigger ---
        if state.position == 1 and not state.moved_to_breakeven:
            if (price - state.entry_price) >= atr * state.breakeven_trigger:
                state.stop_price = state.entry_price
                state.moved_to_breakeven = True

        if state.position == -1 and not state.moved_to_breakeven:
            if (state.entry_price - price) >= atr * state.breakeven_trigger:
                state.stop_price = state.entry_price
                state.moved_to_breakeven = True

        # === STOP HIT ===
        if state.position == 1 and state.moved_to_breakeven and price <= state.stop_price:
            exit_price = price * (1 - config.EXCHANGE_FEE)
            pnl = (exit_price - state.entry_price) * state.quantity

            state.balance += pnl
            state.trades.append({
                "type": "SELL (B/E)", "time": timestamp,
                "price": price, "pnl": pnl,
                "qty": state.quantity, "equity": state.balance
            })

            # Reset
            state.position = 0
            state.entry_price = None
            state.quantity = 0
            state.stop_price = None
            state.moved_to_breakeven = False
            state.last_exit_bar = i
            return True    # indicate exit happened

        if state.position == -1 and state.moved_to_breakeven and price >= state.stop_price:
            exit_price = price * (1 + config.EXCHANGE_FEE)
            pnl = (state.entry_price - exit_price) * state.quantity

            state.balance += pnl
            state.trades.append({
                "type": "BUY (COVER B/E)", "time": timestamp,
                "price": price, "pnl": pnl,
                "qty": state.quantity, "equity": state.balance
            })

            # Reset
            state.position = 0
            state.entry_price = None
            state.quantity = 0
            state.stop_price = None
            state.moved_to_breakeven = False
            state.last_exit_bar = i
            return True

        # === NORMAL LONG EXIT ===
        if state.position == 1:
            if row.sell_signal and price < row.ema20:
                exit_price = price * (1 - config.EXCHANGE_FEE)
                pnl = (exit_price - state.entry_price) * state.quantity

                state.balance += pnl
                state.trades.append({
                    "type": "SELL", "time": timestamp,
                    "price": price, "pnl": pnl,
                    "qty": state.quantity, "equity": state.balance
                })

                # Reset
                state.position = 0
                state.entry_price = None
                state.quantity = 0
                state.stop_price = None
                state.moved_to_breakeven = False
                state.last_exit_bar = i
                return True

        # === NORMAL SHORT EXIT ===
        if state.position == -1:
            if row.buy_signal and price > row.ema20:
                exit_price = price * (1 + config.EXCHANGE_FEE)
                pnl = (state.entry_price - exit_price) * state.quantity

                state.balance += pnl
                state.trades.append({
                    "type": "BUY (COVER)", "time": timestamp,
                    "price": price, "pnl": pnl,
                    "qty": state.quantity, "equity": state.balance
                })

                # Reset
                state.position = 0
                state.entry_price = None
                state.quantity = 0
                state.stop_price = None
                state.moved_to_breakeven = False
                state.last_exit_bar = i
                return True

        return False
    # END OF EXIT LOGIC


    def check_entry(self, i, row, state, df, config, enable_short=True, should_avoid=None):
        """Handles long/short entries with cooldown and trend filtering."""
        price = row.close
        timestamp = df.index[i]

        # === LONG ENTRY ===
        if (
            state.position == 0
            and row.buy_signal and not df.buy_signal.iloc[i - 1]
            and (i - state.last_exit_bar >= config.COOLDOWN_BARS)
            and row.trend_up
        ):
            if should_avoid and should_avoid(df.iloc[i]):
                state.skipped_trades.append((timestamp, "BUY"))
                return

            entry_price = price * (1 + config.EXCHANGE_FEE)
            capital = state.balance * config.CAPITAL
            qty = capital / entry_price

            state.position = 1
            state.entry_price = entry_price
            state.quantity = qty
            state.stop_price = None
            state.moved_to_breakeven = False

            state.trades.append({
                "type": "BUY",
                "time": timestamp,
                "price": price,
                "qty": qty,
                "equity": state.balance
            })
            return

        # === SHORT ENTRY ===
        if enable_short and (
            state.position == 0
            and row.sell_signal and not df.sell_signal.iloc[i - 1]
            and (i - state.last_exit_bar >= config.COOLDOWN_BARS)
            and row.trend_down
        ):
            if should_avoid and should_avoid(df.iloc[i]):
                state.skipped_trades.append((timestamp, "SELL"))
                return

            entry_price = price * (1 - config.EXCHANGE_FEE)
            capital = state.balance * config.CAPITAL
            qty = capital / entry_price

            state.position = -1
            state.entry_price = entry_price
            state.quantity = qty
            state.stop_price = None
            state.moved_to_breakeven = False

            state.trades.append({
                "type": "SELL (SHORT)",
                "time": timestamp,
                "price": price,
                "qty": qty,
                "equity": state.balance
            })
