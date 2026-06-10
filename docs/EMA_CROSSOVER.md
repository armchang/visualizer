# EMA Crossover Strategy

`EMACrossover` is a signal-following strategy that enters long and short
positions from ATR trailing-stop crossover signals. Despite the strategy name,
the final buy/sell signals are produced by `get_signals()` in
`scripts.compute`; the strategy itself prepares EMA/trend columns and handles
position lifecycle, fees, cooldowns, and breakeven exits.

## Source

- Strategy class: `scripts/strategies/ema_crossover.py`
- Signal helpers: `scripts/compute.py`
- Indicator helpers: `scripts/util/backtest_util.py`

## Search Criteria

The file exposes this optimization/search grid:

| Parameter | Values |
| --- | --- |
| `interval` | `4h` |
| `cooldowns` | `10`, `15` |
| `daily_loss_cap` | `-0.1`, `-0.2` |
| `atr_periods` | `7`, `14`, `21`, `28` |
| `cooloff_bars` | `14`, `21`, `28` |
| `sensitivity` | `2.5` |
| `growth` | `30` |
| `hard_stop_atr` | `1.5` |
| `max_bars` | `40` |
| `trail_atr` | `2.0` |

## Data Preparation

Before signals are calculated, `prepare()` adds:

- `ema50` and `ema200`
- `trend_up`: `ema50 > ema200`
- `trend_down`: `ema50 < ema200`
- `ema20` and `ema50`

The `ema50` column is created by both `add_trend_filter()` and `add_emas()`;
the later `add_emas()` calculation overwrites it with the same span.

## Signal Calculation

`compute_signals()` copies the input dataframe, runs `prepare()`, then calls:

```python
get_signals(df, config.ATR_PERIOD, config.SENSITIVITY, config.USE_HEIKIN_ASHI)
```

`get_signals()` adds the following columns:

| Column | Description |
| --- | --- |
| `src` | Signal source. Uses close price unless `USE_HEIKIN_ASHI` is enabled, in which case it uses `(open + high + low + close) / 4`. |
| `atr` | Wilder ATR using `config.ATR_PERIOD`, then forward/back filled. |
| `stop_distance` | `atr * config.SENSITIVITY`. |
| `trailing_stop` | ATR-based trailing stop derived from `src` and `stop_distance`. |
| `ema` | EMA of `src` using `config.EMA_SMOOTHING`. |
| `buy_signal` | True when `ema` crosses above `trailing_stop` and `src` is above `trailing_stop`. |
| `sell_signal` | True when `ema` crosses below `trailing_stop` and `src` is below `trailing_stop`. |
| `sma20`, `sma50`, `sma100`, `sma200` | Simple moving averages, forward/back filled. |
| `signal` | Numeric signal: `1` for buy, `-1` for sell, `0` otherwise. |

## Entry Rules

The strategy only opens a new position when `state.position == 0`.

### Long Entry

When `buy_signal` is true:

1. Entry price is adjusted upward for fees:
   `close * (1 + config.EXCHANGE_FEE)`.
2. Capital allocated is `state.balance * config.CAPITAL`.
3. Quantity is calculated as `capital_used / entry_price`.
4. Position is set to `1`.
5. A `BUY` trade is appended with zero realized PnL.

### Short Entry

When `sell_signal` is true and `config.ENABLE_SHORT` is true:

1. Entry price is adjusted downward for fees:
   `close * (1 - config.EXCHANGE_FEE)`.
2. Capital allocated is `state.balance * config.CAPITAL`.
3. Quantity is calculated as `capital_used / entry_price`.
4. Position is set to `-1`.
5. A `SELL (SHORT)` trade is appended with zero realized PnL.

Shorts are enabled by default if `ENABLE_SHORT` is missing from the config,
because the code uses `getattr(config, "ENABLE_SHORT", True)`.

## Exit Rules

Positions close when the opposite signal appears.

### Long Exit

When currently long and `sell_signal` is true:

- Exit price is `close * (1 - config.EXCHANGE_FEE)`.
- PnL is `(exit_price - state.entry_price) * state.quantity`.
- Balance is increased by PnL.
- A `SELL` trade is appended.
- Position state is reset.

### Short Exit

When currently short and `buy_signal` is true:

- Exit price is `close * (1 + config.EXCHANGE_FEE)`.
- PnL is `(state.entry_price - exit_price) * state.quantity`.
- Balance is increased by PnL.
- A `BUY (COVER)` trade is appended.
- Position state is reset.

## Breakeven Stop Logic

`check_stop()` uses the current row's `atr` value. If ATR is missing, no stop
logic runs for that bar.

### Moving Stop to Breakeven

For a long position, once:

```text
close - entry_price >= atr
```

the stop is moved to `entry_price` and `moved_to_breakeven` is set to true.

For a short position, once:

```text
entry_price - close >= atr
```

the stop is moved to `entry_price` and `moved_to_breakeven` is set to true.

### Breakeven Exit

After the breakeven stop has been activated:

- A long exits when `close <= stop_price`.
- A short exits when `close >= stop_price`.

The exit still accounts for exchange fees, so the realized PnL may be slightly
negative even though the stop level is set to the original fee-adjusted entry.

## Skip Rules

`should_skip()` blocks new processing when either condition is true:

- The current bar is still inside the cooldown window:
  `i - state.last_exit_bar < config.COOLDOWN_BARS`.
- The current date is listed in `state.trading_disabled_dates`.

If `config.DEBUG` is true, the strategy prints a message when a date is skipped
because the daily loss cap has been reached.

## Position Reset

Whenever a position is closed, `reset_position()` sets:

- `position = 0`
- `entry_price = None`
- `stop_price = None`
- `quantity = 0`
- `moved_to_breakeven = False`
- `last_exit_bar = i`

Updating `last_exit_bar` is what enforces the cooldown rule on later bars.

## Config Attributes Used

The strategy and signal helpers read these config fields:

- `ATR_PERIOD`
- `SENSITIVITY`
- `USE_HEIKIN_ASHI`
- `EMA_SMOOTHING`
- `EXCHANGE_FEE`
- `CAPITAL`
- `COOLDOWN_BARS`
- `ENABLE_SHORT`
- `DEBUG`

## Trade Types Emitted

| Trade type | Meaning |
| --- | --- |
| `BUY` | Open long position. |
| `SELL` | Close long position on sell signal. |
| `SELL (SHORT)` | Open short position. |
| `BUY (COVER)` | Close short position on buy signal. |
| `SELL (BREAKEVEN)` | Close long position through breakeven stop. |
| `BUY (COVER B/E)` | Close short position through breakeven stop. |

## Notes

- The `enable_short` and `should_avoid` arguments on `check_entry()` are not
  used by the current implementation.
- The imported `get_atr` and `numpy` aliases in `ema_crossover.py` are not used
  directly in this file.
- The prepared `trend_up` and `trend_down` columns are added but not referenced
  by the entry or exit logic in this strategy.
