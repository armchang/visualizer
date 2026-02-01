from config import config
import scripts.engine as engine
import scripts.tracing.screen_output as so
import scripts.util.clear_console as clear
import scripts.plotters.plotter_tv as tv
import scripts.util.logger as logger
import scripts.tracing.excel_output as excel
import scripts.util.countdown as countdown
import scripts.search_optimal_settings as sos

if __name__ == "__main__":
    clear.run()

    config.PAIR_NAME = "BTCUSDT"
    choice = input("Do you want to search for optimal settings? (y/n): ").strip().lower()

    if choice == "y":
        # Run full search
        best_config, best_result, df, equity_df, trades_df, metrics = sos.search_optimal_settings(config.PAIR_NAME, 'scripts.strategies.trendline_break_retest')

        # Apply best configuration
        config.RESAMPLE_INTERVAL            = best_config.get("interval", "4h")
        config.COOLDOWN_BARS                = best_config.get("cooldown", 20)
        config.DAILY_LOSS_CAP               = best_config.get("daily_loss_cap", -0.2)
        config.ATR_PERIOD                   = best_config.get("atr", 21)
        config.COOL_OFF_BARS_AFTER_GROWTH   = best_config.get("cooloff_bars", 20)
        config.SENSITIVITY                  = best_config.get("sensitivity", 2.0)
        config.GROWTH_THRESHOLD             = best_config.get("growth", 30)
        config.HARD_STOP_ATR                = best_config.get("hard_stop_atr", 1.5)
        config.MAX_BARS_IN_TRADE            = best_config.get("max_bars", 20)
        config.TRAIL_ATR                    = best_config.get("trail_atr", 2.0)
        
        # Store to log
        logger.log(best_config, best_result)
    else:
        # Use defaults from config.py
        print("\n⚡ Using default config.py settings...")
        try:
            best_config = logger.load_best_config_from_log(f"logs/best_configs_{config.PAIR_NAME}.log")
        except Exception as e:
            print(f"⚠️ Failed to load best config from log: {e}")
            print("➡️ Falling back to default config.py settings...")
            best_config = {
                "interval": config.RESAMPLE_INTERVAL,
                "cooldown": config.COOLDOWN_BARS,
                "daily_loss_cap": config.DAILY_LOSS_CAP,
                "atr": config.ATR_PERIOD,
                "pair": config.PAIR_NAME,
                "cooloff_bars": config.COOL_OFF_BARS_AFTER_GROWTH,
                "sensitivity": config.SENSITIVITY,
                "growth": config.GROWTH_THRESHOLD,
                "hard_stop_atr" : config.HARD_STOP_ATR,
                "max_bars" : config.MAX_BARS_IN_TRADE,
                "trail_atr" : config.TRAIL_ATR
            }

        # Apply best configuration
        config.RESAMPLE_INTERVAL            = best_config.get("interval", "4h")
        config.COOLDOWN_BARS                = best_config.get("cooldown", 20)
        config.DAILY_LOSS_CAP               = best_config.get("daily_loss_cap", -0.2)
        config.ATR_PERIOD                   = best_config.get("atr", 21)
        config.COOL_OFF_BARS_AFTER_GROWTH   = best_config.get("cooloff_bars", 10)
        config.SENSITIVITY                  = best_config.get("sensitivity", 2.0)
        config.GROWTH_THRESHOLD             = best_config.get("growth", 30)
        config.HARD_STOP_ATR                = best_config.get("hard_stop_atr", 1.5)
        config.MAX_BARS_IN_TRADE            = best_config.get("max_bars", 20)
        config.TRAIL_ATR                    = best_config.get("trail_atr", 2.0)

        print("✅ Loaded best config from log:", best_config)
        df, equity_df, trades_df, metrics = engine.run(config)

    want_export_trades = countdown.countdown_input("Do you want to save trades to Excel file? \n", timeout=5, default="n")
    if want_export_trades == "y":
        excel.export(trades_df, True, "trades_entered")
        excel.export(df, True, "ohclv_data")

    # Run charting in both cases
    tv.run(df, equity_df, trades_df, metrics, True)
