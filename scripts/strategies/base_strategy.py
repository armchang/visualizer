
# scripts/strategies/base_strategy.py

class BaseStrategy:
    """Base class for plug-and-play strategy modules."""
    plot_columns = []
    
    def compute_signals(self, df, config):
        """
        Strategy-specific indicator & signal computation.
        Must return df.
        """
        return df
    
    def prepare(self, df, config):
        return df

    def check_entry(self, i, row, state, df, config):
        pass

    def check_exit(self, i, row, state, df, config):
        pass
