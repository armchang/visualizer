
import numpy as np
import pandas as pd
from scripts import backtest, compute, fetch, metric
from scripts.risk_controls import volatility
from scripts.risk_controls import pattern_engineering
from scripts.util import rule_logger, backtest_util
from scripts.util.param_grid_builder import load_strategy_module


def load_strategy(strategy_path):
    if "." not in strategy_path:
        strategy_path = f"scripts.strategies.{strategy_path}"

    strategy_mod = load_strategy_module(strategy_path)

    if not hasattr(strategy_mod, "Strategy"):
        raise RuntimeError(f"{strategy_path} does not expose a Strategy class")

    return strategy_mod.Strategy()


def run(config):
    strategy = load_strategy(config.STRATEGY)

    df = fetch.get_ohlcv_data(config.DATABASE_PATH, config.TABLE_NAME, config.PAIR_NAME)                                # Fetch all data based on config.PAIR_NAME         
    df = fetch.resample_ohlcv(df, config.RESAMPLE_INTERVAL)                                                             # Recompute data based on timeframe
    df = strategy.compute_signals(df, config)

    if "signal" not in df.columns:
        raise RuntimeError("Strategy did not create df['signal']")
    
    df = volatility.add(df, config.TARGET_VOL, config.RESAMPLE_INTERVAL, config.HORIZON_DAYS, config.MAX_LEVERAGE)      # Add volatility targeting
    df = fetch.crop_date_range(df, config.YEARS_BACKTRACK)                                                              # Crop data with number of years
    df = pattern_engineering.build_regime_features(df)                                                                  # Add more signals = EMA(50, 100), ADX, etc.
    df = compute.add_candle_stats(df)                                                                                   # Add candle body, size, total wick

    #rules = rule_logger.load_pattern_rules(config.PAIR_NAME, config.RESAMPLE_INTERVAL)                                  # Implements additional rules aside from main signals 
    #should_avoid_trade = rule_logger.compile_rule_filter(rules)

    # Backtesting starts here
    equity_df, trades_df = backtest.run(df, config, strategy=strategy, should_avoid_trade=None, enable_short=True)

    # Print
    trades_df = backtest_util.fix_entered_trades(trades_df, df)                                                         # Fixing empty trades here
    metrics = metric.compute_metrics(equity_df, trades_df, config.RESAMPLE_INTERVAL)                                    # Retrieves equity, returns, averages, etc.

    return df, equity_df, trades_df, metrics
