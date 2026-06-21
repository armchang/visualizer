# Trading Bot Project

This project is a Python-based crypto trading backtest and strategy research system.

Main goals:
- Backtest BTCUSDT and TAOUSDT strategies.
- Use 4H candles mainly.
- Test trend-following and pullback strategies.
- Track entries, exits, stop loss, take profit, equity, and skipped trades.
- Compare performance across different rules.

Main files:
- `_main.py`: interactive application entry point
- backtest.py: core backtest engine
- indicators.py: indicator calculations
- strategy.py: entry and exit logic
- analysis.py: trade performance analysis
- config.py: parameters and settings

Database configuration:

- `DATABASE_TYPE` defaults to `postgresql`.
- `DATABASE_URL` defaults to `postgresql://postgres:postgres@localhost:5432/dataspider`.
- Set both environment variables to the same values used by DataSpider, or put
  machine-specific overrides in the gitignored `config/local_config.py`.

For SQLite, use:

```text
DATABASE_TYPE=sqlite
DATABASE_URL=sqlite:///datas/dataspider.db
```
