# backtest/state.py
class BacktestState:
    def __init__(self, config):
        self.balance = config.STARTING_BALANCE
        self.last_exit_bar = -config.COOLDOWN_BARS - 1

        self.position = 0           # 1 = long, -1 = short, 0 = flat
        self.entry_price = None
        self.quantity = 0
        self.stop_price = None
        self.entry_bar = None

        self.equity = self.balance
        self.equity_curve = []
        self.trades = []
        self.skipped_trades = []

        # Daily controls
        self.current_day = None
        self.day_start_equity = self.balance
        self.trading_paused = False

        # Advanced controls
        self.growth_cooloff_until = -1
        self.breakeven_trigger = 1.0
        self.moved_to_breakeven = False
