import numpy as np
import pandas as pd
import scripts.util.backtest_util as bu
from scripts.strategies.base_strategy import BaseStrategy
from scripts.compute import get_atr_wilder

search_criteria = {
    "interval": ["15min"],
    "cooldowns": [10, 20, 30],
    "daily_loss_cap": [-0.1, -0.15],
    "atr_periods": [21, 50],
    "cooloff_bars": [14],
    "sensitivity": [1.5, 2.5],
    "growth": [100],
    "hard_stop_atr" : [2.0],
    "max_bars" : [50],
    "trail_atr" : [2.5]
}

class TrendlineBreakRetestStrategy(BaseStrategy):
    plot_columns = []  # no trailing stop

    """
    Trendline Break + Retest + Candle Confirmation Strategy

    LONG:
    - Break above resistance trendline
    - Retest forms HAMMER
    - Confirmation via BULLISH ENGULFING

    SHORT:
    - Break below support trendline
    - Retest forms SHOOTING STAR
    - Confirmation via BEARISH ENGULFING
    """

    # ==========================================================
    # PREPARE
    # ==========================================================
    def prepare(self, df, config):
        df = df.copy()
        #df = bu.add_trend_filter(df)
        #df = bu.add_emas(df, [20, 50])

        # SMA's 
        df["sma20"] = df["close"].rolling(20).mean()
        df["sma50"] = df["close"].rolling(50).mean()
        df["sma100"] = df["close"].rolling(100).mean()
        df["sma200"] = df["close"].rolling(200).mean()

        df["swing_high"] = self._swing_high(df)
        df["swing_low"] = self._swing_low(df)

        df["hammer"] = self._hammer(df)
        df["shooting_star"] = self._shooting_star(df)

        df["bull_engulf"] = self._bullish_engulfing(df)
        df["bear_engulf"] = self._bearish_engulfing(df)

        n = len(df)
        # Preallocate results (MUCH faster than df.loc in loop)
        break_res = np.zeros(n, dtype=bool)
        break_sup = np.zeros(n, dtype=bool)

        start = 10
        for i in range(start, n):
            break_res[i] = self._breaks_resistance(i, df)
            break_sup[i] = self._breaks_support(i, df)
        # Assign once
        df["break_resistance"] = break_res
        df["break_support"] = break_sup

        return df

    # ==========================================================
    # ENTRY
    # ==========================================================
    def check_entry(self, i, row, state, df, config, enable_short=True, should_avoid=None):
        price = row.close
        timestamp = df.index[i]

        if i < 2 or state.position != 0:
            return

        # === LONG ENTRY ===
        if (
            row.break_resistance
            and df.iloc[i - 1].hammer
            and row.bull_engulf
            and (i - state.last_exit_bar >= config.COOLDOWN_BARS)
        ):
            if should_avoid and should_avoid(row):
                state.skipped_trades.append((timestamp, "BUY"))
                return

            entry_price = price * (1 + config.EXCHANGE_FEE)
            capital = state.balance * config.CAPITAL
            qty = capital / entry_price

            state.position = 1
            state.entry_price = entry_price
            state.quantity = qty
            state.moved_to_breakeven = False
            state.stop_price = None
            state.entry_bar = i

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
            row.break_support
            and df.iloc[i - 1].shooting_star
            and row.bear_engulf
            and (i - state.last_exit_bar >= config.COOLDOWN_BARS)
        ):
            if should_avoid and should_avoid(row):
                state.skipped_trades.append((timestamp, "SELL"))
                return

            entry_price = price * (1 - config.EXCHANGE_FEE)
            capital = state.balance * config.CAPITAL
            qty = capital / entry_price

            state.position = -1
            state.entry_price = entry_price
            state.quantity = qty
            state.moved_to_breakeven = False
            state.stop_price = None
            state.entry_bar = i

            state.trades.append({
                "type": "SELL (SHORT)",
                "time": timestamp,
                "price": price,
                "qty": qty,
                "equity": state.balance
            })

    # ==========================================================
    # EXIT (USE UTBOT EXIT STRATEGY)
    # ==========================================================
    def check_exit(self, i, row, state, df, config):
        """
        Trendline Breakout exit logic (Option A compliant).
        Exits are recorded via trades_df only.
        """

        if state.position == 0:
            return False

        price = row.close
        timestamp = df.index[i]
        atr = row.atr

        HARD_STOP_ATR = config.HARD_STOP_ATR
        TRAIL_ATR = config.TRAIL_ATR
        MAX_BARS_IN_TRADE = config.MAX_BARS_IN_TRADE
        FEE_BUFFER = 2 * config.EXCHANGE_FEE * state.entry_price

        # --------------------------------------------------
        # Initial hard stop (set once)
        # --------------------------------------------------
        if state.stop_price is None:
            if state.position == 1:
                state.stop_price = state.entry_price - atr * HARD_STOP_ATR
            else:
                state.stop_price = state.entry_price + atr * HARD_STOP_ATR

        # -------------------------------------------
        # ATR trailing stop
        # -------------------------------------------
        
        # -------------------------------------------
        # Compute unrealized profit
        # -------------------------------------------
        if state.position == 1:
            unrealized = price - state.entry_price
        else:
            unrealized = state.entry_price - price

        # -------------------------------------------
        # TRAILING ONLY AFTER REAL PROFIT
        # -------------------------------------------
        min_profit_to_trail = atr * 1.0 + FEE_BUFFER

        if unrealized >= min_profit_to_trail:
            if state.position == 1:
                new_trail = price - atr * TRAIL_ATR
                state.stop_price = max(state.stop_price, new_trail)

                if price <= state.stop_price:
                    return self._exit_trade(
                        state, price, timestamp, i, config, reason="TRAIL STOP"
                    )
            else:
                new_trail = price + atr * TRAIL_ATR
                state.stop_price = min(state.stop_price, new_trail)

                if price >= state.stop_price:
                    return self._exit_trade(
                        state, price, timestamp, i, config, reason="TRAIL STOP"
                    )

        # --------------------------------------------------
        # Time-based exit
        # --------------------------------------------------
        bars_in_trade = i - state.entry_bar

        if bars_in_trade >= MAX_BARS_IN_TRADE:
            return self._exit_trade(
                state, price, timestamp, i, config, reason="TIME EXIT"
            )

        return False

    # ==========================================================
    # TRENDLINE LOGIC
    # ==========================================================
    def _breaks_resistance(self, i, df):
        highs = df.iloc[i - 8:i].swing_high.dropna()
        if len(highs) < 2:
            return False

        x = np.arange(len(highs))
        y = highs.values
        slope, intercept = np.polyfit(x, y, 1)

        trend_price = slope * len(highs) + intercept
        return df.iloc[i].close > trend_price

    def _breaks_support(self, i, df):
        lows = df.iloc[i - 8:i].swing_low.dropna()
        if len(lows) < 2:
            return False

        x = np.arange(len(lows))
        y = lows.values
        slope, intercept = np.polyfit(x, y, 1)

        trend_price = slope * len(lows) + intercept
        return df.iloc[i].close < trend_price

    # ==========================================================
    # CANDLE PATTERNS
    # ==========================================================
    def _hammer(self, df):
        body = abs(df.close - df.open)
        lower = df[["open", "close"]].min(axis=1) - df.low
        upper = df.high - df[["open", "close"]].max(axis=1)
        return (lower > body * 2) & (upper < body)

    def _shooting_star(self, df):
        body = abs(df.close - df.open)
        upper = df.high - df[["open", "close"]].max(axis=1)
        lower = df[["open", "close"]].min(axis=1) - df.low
        return (upper > body * 2) & (lower < body)

    def _bullish_engulfing(self, df):
        prev = df.shift(1)
        return (
            (df.close > df.open)
            & (prev.close < prev.open)
            & (df.open < prev.close)
            & (df.close > prev.open)
        )

    def _bearish_engulfing(self, df):
        prev = df.shift(1)
        return (
            (df.close < df.open)
            & (prev.close > prev.open)
            & (df.open > prev.close)
            & (df.close < prev.open)
        )

    # ==========================================================
    # SWINGS
    # ==========================================================
    def _swing_high(self, df, window=2):
        return df.high.where(
            df.high == df.high.rolling(window * 2 + 1, center=True).max()
        )

    def _swing_low(self, df, window=2):
        return df.low.where(
            df.low == df.low.rolling(window * 2 + 1, center=True).min()
        )

    # ==========================================================
    # COMPUTE SIGNALS
    # ==========================================================
    def compute_signals(self, df, config):
        df = df.copy()

        # Reuse your prepare logic
        df = self.prepare(df, config)

        # 🔥 ADD THIS
        df["atr"] = get_atr_wilder(df, config.ATR_PERIOD)
        df["atr"] = df["atr"].ffill().bfill()

        # REQUIRED: numeric signal for volatility targeting
        df["signal"] = 0
        df.loc[df["break_resistance"] & df["bull_engulf"], "signal"] = 1
        df.loc[df["break_support"] & df["bear_engulf"], "signal"] = -1

        # ==========================
        # Plotter-compatible signals
        # ==========================
        df["buy_signal"] = df["signal"] == 1
        df["sell_signal"] = df["signal"] == -1

        return df


    #
    def _exit_trade(self, state, price, timestamp, i, config, reason):
        """
        Records exits in trades_df using plotter-compatible trade types.
        This enables Option A: exit markers via trades_df (no df mutation).
        """

        # Normalize exit reason → plotter_tv compatible labels
        if reason == "TRAIL STOP":
            label = "STOP"
        elif reason == "TIME EXIT":
            label = "TIME"
        else:
            label = "STOP"

        if state.position == 1:
            exit_price = price * (1 - config.EXCHANGE_FEE)
            pnl = (exit_price - state.entry_price) * state.quantity
            trade_type = f"SELL ({label})"
        else:
            exit_price = price * (1 + config.EXCHANGE_FEE)
            pnl = (state.entry_price - exit_price) * state.quantity
            trade_type = f"BUY (COVER)"

        state.balance += pnl
        state.trades.append({
            "type": trade_type,
            "time": timestamp,
            "price": price,
            "pnl": pnl,
            "qty": state.quantity,
            "equity": state.balance
        })

        # Reset position state
        state.position = 0
        state.entry_price = None
        state.quantity = 0
        state.stop_price = None
        state.moved_to_breakeven = False
        state.last_exit_bar = i
        state.entry_bar = None

        return True