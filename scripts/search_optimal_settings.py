import itertools
from tqdm import tqdm
from config import config 
import scripts.engine as engine
from scripts.util.param_grid_builder import build_param_grid, iter_param_dicts
from scripts.util.param_grid_builder import load_strategy_module
import shutil

def search_optimal_settings(pair, strategy_path):
        
    # 2) Import the module (trendline_break_retest.py).
    strategy_mod = load_strategy_module(strategy_path)

    # 3) Read the search_criteria dict from the strategy module.
    search_criteria = strategy_mod.search_criteria

    # 4) Build dynamic param_grid (list of tuples) + keys order.
    keys, param_grid = build_param_grid(search_criteria)

    best_result = None
    best_config = None
    best_df = best_equity_df = best_trades_df = best_metrics = None

    with tqdm(param_grid, desc="Running backtests", unit="combo") as pbar:
        for interval, cooldown, daily_loss_cap, atr, cooloff_bars, sensitivity, growth, hard_stop_atr, max_bars, trail_atr in pbar:
            # Apply config
            config.RESAMPLE_INTERVAL            = interval
            config.COOLDOWN_BARS                = cooldown
            config.DAILY_LOSS_CAP               = daily_loss_cap
            config.ATR_PERIOD                   = atr
            config.PAIR_NAME                    = pair
            config.COOL_OFF_BARS_AFTER_GROWTH   = cooloff_bars 
            config.SENSITIVITY                  = sensitivity
            config.GROWTH_THRESHOLD             = growth
            config.HARD_STOP_ATR                = hard_stop_atr
            config.MAX_BARS_IN_TRADE            = max_bars
            config.TRAIL_ATR                    = trail_atr

            df, equity_df, trades_df, metrics = engine.run(config)
            final_balance = equity_df["equity"].iloc[-1]

            # Track best result
            if best_result is None or final_balance > best_result:
                best_result = final_balance
                best_config = {
                    "interval": interval,
                    "cooldown": cooldown,
                    "daily_loss_cap": daily_loss_cap,
                    "atr": atr,
                    "cooloff_bars": cooloff_bars,
                    "sensitivity": sensitivity,
                    "growth": growth,
                    "pair": config.PAIR_NAME,
                    "hard_stop_atr" : hard_stop_atr,
                    "max_bar" : max_bars,
                    "trail_atr" : trail_atr,
                    # add these:
                    "strategy_path": strategy_path,
                    "strategy": strategy_path.rsplit(".", 1)[-1]
                }
                best_df = df
                best_equity_df = equity_df
                best_trades_df = trades_df
                best_metrics = metrics

            # ✅ Update description with best status
            # Build a readable "k=v" list from whatever keys actually exist in best_config
            pretty_params = ", ".join(f"{k}={v}" for k, v in best_config.items())

            # Update tqdm's progress bar description without hardcoding keys
            desc = f"Best={best_result:.2f} ({pretty_params})"
            pbar.set_postfix(gain=final_balance, interval=interval, atr=atr, sens=sensitivity, pair=pair, refresh=False)
            pbar.update(1)
            #pbar.set_description(trim_to_terminal(desc))


    print("\n=== Final Best Configuration ===")
    print(f"Final Balance: {best_result:.2f}")
    print(best_config)
    return best_config, best_result, best_df, best_equity_df, best_trades_df, best_metrics


def trim_to_terminal(text, padding=10):
    width = shutil.get_terminal_size(fallback=(100, 20)).columns
    max_len = max(10, width - padding)
    return text if len(text) <= max_len else text[:max_len - 1] + "…"