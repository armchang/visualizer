import numpy as np

def compute_metrics(equity_df, trades_df, interval="4h"):
    periods_map = {
        "1d": 365,
        "1h": 24 * 365,
        "2h": 12 * 365,
        "4h": 6 * 365,
        "30min": 48 * 365,
        "1w": 52,
    }

    interval = interval.lower()
    periods_per_year = periods_map.get(interval, 365)

    returns = equity_df["equity"].pct_change(fill_method=None).dropna()
    start_equity = equity_df["equity"].iloc[0]
    end_equity   = equity_df["equity"].iloc[-1]
    total_return = end_equity / start_equity - 1

    # Safe CAGR calculation
    n_years = len(equity_df) / periods_per_year
    if n_years > 0 and start_equity > 0 and end_equity > 0:
        annual_return = (end_equity / start_equity) ** (1 / n_years) - 1
    else:
        annual_return = np.nan

    volatility = returns.std() * np.sqrt(periods_per_year)
    sharpe = annual_return / volatility if volatility > 0 else np.nan

    #equity_df["cummax"] = equity_df["equity"].cummax()
    #equity_df["drawdown"] = equity_df["equity"] / equity_df["cummax"] - 1
    peak = equity_df["equity"].iloc[0]
    drawdowns = []

    for eq in equity_df["equity"]:
        if eq > peak:
            peak = eq
        drawdown = (eq / peak) - 1
        drawdowns.append(drawdown)

    equity_df["drawdown"] = drawdowns

    max_drawdown = equity_df["drawdown"].min()
    win_rate = (trades_df["pnl"] > 0).mean() if "pnl" in trades_df else np.nan

    if trades_df.empty or "type" not in trades_df.columns:
        print("[Metrics] No trades recorded.")
        return {
            "Total Trades": 0,
            "Win Rate": 0.0,
            "Avg Win": 0.0,
            "Avg Loss": 0.0,
            "Profit Factor": 0.0,
            "Sharpe Ratio": 0.0,
        }
    else:
        return {
            "Annual Return": round(annual_return, 3) if not np.isnan(annual_return) else None,
            "Volatility": round(volatility, 3) if not np.isnan(volatility) else None,
            "Sharpe Ratio": round(sharpe, 3) if not np.isnan(sharpe) else None,
            "Max Drawdown": round(max_drawdown, 3) if not np.isnan(max_drawdown) else None,
            "Win Rate": round(win_rate, 3) if not np.isnan(win_rate) else None,
            "Total Trades": trades_df[trades_df["type"] == "SELL"].shape[0]
        }
