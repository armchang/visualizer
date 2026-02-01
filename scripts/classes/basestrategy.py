from scripts.classes.strategystate import StrategyState

class BaseStrategy:
    """Base class all strategies must inherit from."""

    def prepare(self, df, config):
        """Add indicators/signals to df."""
        raise NotImplementedError

    def init_state(self, config):
        return StrategyState(config)

    def should_skip(self, i, row, state, config):
        """Return True to skip this bar (e.g. cooldown, paused trading)."""
        return False

    def check_entry(self, i, row, df, config):
        raise NotImplementedError

    def check_exit(self, i, row, state, config):
        raise NotImplementedError

    def check_stop(self, i, row, state, config):
        raise NotImplementedError