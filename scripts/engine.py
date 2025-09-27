
import numpy as np
import pandas as pd
from scripts import compute, backtest, fetch, metric
from scripts.risk_controls import volatility
from scripts.risk_controls import pattern_engineering
from scripts.util import rule_logger

def run(config):
    df = fetch.get_ohlcv_data(config.DATABASE_PATH, config.TABLE_NAME, config.PAIR_NAME)

    if df.empty:
        raise ValueError("No data found.")
    df = fetch.resample_ohlcv(df, config.RESAMPLE_INTERVAL)
    df = compute.get_signals(df, config.ATR_PERIOD, config.SENSITIVITY, config.USE_HEIKIN_ASHI)                         # ATR + EMA(1) based signals
    df = volatility.add(df, config.TARGET_VOL, config.RESAMPLE_INTERVAL, config.HORIZON_DAYS, config.MAX_LEVERAGE)      # Add volatility targeting
    # Crop here after all calculations have finished
    df = fetch.crop_date_range(df, config.YEARS_BACKTRACK)
    df = pattern_engineering.build_regime_features(df)
    df = compute.add_candle_stats(df)
    


    rules = rule_logger.load_pattern_rules(config.PAIR_NAME, config.RESAMPLE_INTERVAL)
    # 🛠 Compile should_avoid_trade function dynamically
    should_avoid_trade = rule_logger.compile_rule_filter(rules)
    equity_df, trades_df = backtest.run(df, config, None, True)
    df = df.sort_index()
    trades_df = trades_df.sort_values("time")
    trades_df["time"] = pd.to_datetime(trades_df["time"])
    # Merge stats into trades
    trades_with_context = pd.merge_asof(
        trades_df,
        df[["candle_size", "candle_body", "total_wick"]],
        left_on="time",
        right_index=True,
        direction="backward"
    )
    # Filter only losing trades
    losing_trades = trades_with_context[trades_with_context["pnl"] < 0]

    #print("❌ Losing Trades with Candle Info:")
    #print(losing_trades[["time", "type", "price", "pnl", "candle_size", "candle_body", "total_wick"]].head())
    
    #if rules is None:
    #    print("[engine] No saved rules found — computing from scratch. Filter will be applied next time bot is loaded.")
    #    df_features = pattern_engineering.build_regime_features(df)
    #    trades_ctx = pattern_engineering.attach_trade_context(df_features, trades_df, entry_col='time')
    #    pattern_table = pattern_engineering.pattern_report(trades_ctx)
    #    rules = pattern_engineering.propose_filters(pattern_table, min_trades=20, top_k_per_feature=2, loss_rate_floor=0.30)
    #    rule_logger.save_pattern_rules(config.PAIR_NAME, config.RESAMPLE_INTERVAL, rules)

    #print("trades_df.columns:", trades_df.columns.tolist())
    #print("trades_df.head():\n", trades_df.head())
    #print("Total trades recorded:", len(trades_df))

    metrics = metric.compute_metrics(equity_df, trades_df, config.RESAMPLE_INTERVAL)

    # Remove timezone from index
    df.index = df.index.tz_localize(None)

    return df, equity_df, trades_df, metrics

