import pandas as pd

class StrategyState:
    def __init__(self, config):
        self.balance = config.STARTING_BALANCE
        self.last_exit_bar = -config.COOLDOWN_BARS - 1
        self.position = 0
        self.entry_price = None
        self.equity_curve = []
        self.trades = []
        self.current_day = None
        self.day_start_equity = self.balance
        self.trading_paused = False
        self.growth_cooloff_until = -1
        self.breakeven_trigger = 1.0
        self.stop_price = None
        self.quantity = 0
        self.moved_to_breakeven = False
        
        self.current_equity = self.balance
        self.last_entry_bar = -1
        self.last_entry_signal = None
        self.date = None

    def update_context(self, i, row, df):
        timestamp = df.index[i]
        self.date = timestamp.date()
        if self.current_day != self.date:
            self.current_day = self.date
            self.day_start_equity = self.balance if self.position == 0 else self.equity
            self.trading_paused = False
        
        price = row["close"]

        # === Update equity ===
        if self.position == 0:
            self.equity = self.balance
        elif self.position == 1:
            self.equity = self.balance + ((price - self.entry_price) * self.quantity)
        elif self.position == -1:
            self.equity = self.balance + ((self.entry_price - price) * self.quantity)

        if self.position == 0:
            self.current_equity = self.balance
        else:
            self.pnl = (price - self.entry_price) * self.quantity * self.position
            self.current_equity = self.balance + self.pnl

    def record_equity(self, timestamp):
        self.equity_curve.append({"time": timestamp, "equity": self.current_equity})

    def to_equity_df(self):
        return pd.DataFrame(self.equity_curve).set_index("time")
    
    def to_trades_df(self):
        return pd.DataFrame(self.trades)