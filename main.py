import itertools
from tqdm import tqdm
from config import config 
import scripts.engine as engine
import scripts.tracing.screen_output as so
import scripts.util.clear_console as cc
import scripts.plotters.plotter_tv as tv
import scripts.util.logger as logger
import scripts.tracing.excel_output as excel
import scripts.util.countdown as countdown

def search_optimal_settings(pair):
    # Define parameter grid
    intervals       = ["15min", "30min", "1h", "2h"]                # 1h, 2h, 4h, 1d
    cooldowns       = [10, 20]          # Increment by 5
    loss_caps       = [-0.1, 0.125]         # Incremented by 0.05
    atr_periods     = [14, 21]
    cooloff_bars    = [25, 30]
    sensitivity     = [1.5, 2]
    growth          = [50, 100]

    # Prepare combinations
    param_grid = list(itertools.product(intervals, cooldowns, loss_caps, atr_periods, cooloff_bars, sensitivity, growth))

    best_result = None
    best_config = None
    best_df = best_equity_df = best_trades_df = best_metrics = None

    with tqdm(param_grid, desc="Running backtests", unit="combo") as pbar:
        for interval, cooldown, loss_cap, atr, cooloff_bars, sensitivity, growth in pbar:
            # Apply config
            config.RESAMPLE_INTERVAL            = interval
            config.COOLDOWN_BARS                = cooldown
            config.DAILY_LOSS_CAP               = loss_cap
            config.ATR_PERIOD                   = atr
            config.PAIR_NAME                    = pair
            config.COOL_OFF_BARS_AFTER_GROWTH   = cooloff_bars 
            config.SENSITIVITY                  = sensitivity
            config.GROWTH_THRESHOLD             = growth

            df, equity_df, trades_df, metrics = engine.run(config)
            final_balance = equity_df["equity"].iloc[-1]

            # Track best result
            if best_result is None or final_balance > best_result:
                best_result = final_balance
                best_config = {
                    "interval": interval,
                    "cooldown": cooldown,
                    "loss_cap": loss_cap,
                    "atr": atr,
                    "cooloff_bars": cooloff_bars,
                    "sensitivity": sensitivity,
                    "growth": growth,
                    "pair": config.PAIR_NAME
                }
                best_df = df
                best_equity_df = equity_df
                best_trades_df = trades_df
                best_metrics = metrics

            # ✅ Update description with best status
            pbar.set_description(
                f"Best={best_result:.2f} ({best_config['interval']}, cd={best_config['cooldown']}, loss_cap={best_config['loss_cap']}, atr={best_config['atr']}, cooloff_bars={best_config['cooloff_bars']}, sensitivity={best_config['sensitivity']}, growth={best_config['growth']})"
            )

    print("\n=== Final Best Configuration ===")
    print(f"Final Balance: {best_result:.2f}")
    print(best_config)
    return best_config, best_result, best_df, best_equity_df, best_trades_df, best_metrics


if __name__ == "__main__":
    cc.run()

    config.PAIR_NAME = "BTCUSDT"
   
    choice = input("Do you want to search for optimal settings? (y/n): ").strip().lower()

    if choice == "y":
        # Run full search
        best_config, best_result, df, equity_df, trades_df, metrics = search_optimal_settings(config.PAIR_NAME)

        # Apply best configuration
        config.RESAMPLE_INTERVAL            = best_config["interval"]
        config.COOLDOWN_BARS                = best_config["cooldown"]
        config.DAILY_LOSS_CAP               = best_config["loss_cap"]
        config.ATR_PERIOD                   = best_config["atr"]
        config.COOL_OFF_BARS_AFTER_GROWTH   = best_config["cooloff_bars"]
        config.SENSITIVITY                  = best_config["sensitivity"]
        config.GROWTH_THRESHOLD             = best_config["growth"]

        # Store to log
        logger.log(best_config, best_result)
    else:
        # Use defaults from config.py
        print("\n⚡ Using default config.py settings...")
        try:
            best_config = logger.load_best_config_from_log(f"logs/best_configs_{config.PAIR_NAME}.log")
            print("✅ Loaded best config from log:", best_config)
        except Exception as e:
            print(f"⚠️ Failed to load best config from log: {e}")
            print("➡️ Falling back to default config.py settings...")
            best_config = {
                "interval": config.RESAMPLE_INTERVAL,
                "cooldown": config.COOLDOWN_BARS,
                "loss_cap": config.DAILY_LOSS_CAP,
                "atr": config.ATR_PERIOD,
                "pair": config.PAIR_NAME,
                "cooloff_bars": config.COOL_OFF_BARS_AFTER_GROWTH,
                "sensitivity": config.SENSITIVITY,
                "growth": config.GROWTH_THRESHOLD
            }

        # Apply best configuration
        config.RESAMPLE_INTERVAL            = best_config["interval"]
        config.COOLDOWN_BARS                = best_config["cooldown"]
        config.DAILY_LOSS_CAP               = best_config["loss_cap"]
        config.ATR_PERIOD                   = best_config["atr"]
        config.COOL_OFF_BARS_AFTER_GROWTH   = best_config["cooloff_bars"]
        config.SENSITIVITY                  = best_config["sensitivity"]
        config.GROWTH_THRESHOLD             = best_config["growth"]


        print("Best Config Loaded:", best_config)
        df, equity_df, trades_df, metrics = engine.run(config)

    want_export_trades = countdown.countdown_input("Do you want to save trades to Excel file? \n", timeout=5, default="n")
    if want_export_trades == "y":
        excel.export(trades_df, True, "trades_entered")
        excel.export(df, True, "ohclv_data")

    # Run charting in both cases
    tv.run(df, equity_df, trades_df, metrics, True)
