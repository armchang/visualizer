
def show_metrics(metrics):
    print("\n=== Bot Engine Backtest Results (based on UT logic) ===")
    for key, value in metrics.items():
        if isinstance(value, float):
            print(f"{key}: {value:.4f}")  
        else:
            print(f"{key}: {value}")

def show_best(best_result, best_config, final_balance, interval, cooldown, loss_cap, atr, metrics):
    # Track best
    if best_result is None or final_balance > best_result:
        best_result = final_balance
        best_config = {
            "interval": interval,
            "cooldown": cooldown,
            "loss_cap": loss_cap,
            "atr": atr
        }

    return best_result, best_config