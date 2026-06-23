# LSTM Learning Guide

This document explains what the Visualizer LSTM learns, which filters and
features it uses, how training data is prepared, and how to read the results.

The LSTM is not the complete trading strategy. EMA Crossover proposes entries
and exits; the LSTM only decides whether a proposed entry has enough directional
confidence to be accepted.

## Quick feature glossary

This is the most important part to understand first: the LSTM does not receive
raw chart screenshots. It receives numbers made from OHLCV candles and
technical indicators. Each row is one completed candle on the selected
timeframe, for example one 4-hour candle when `--interval 4h` is used.

The model normally uses 28 input features per candle. If you train with
`--fear-greed-csv`, it adds 5 more sentiment features, for a total of 33
features.

### 1. Candle price movement

These features tell the model what happened inside the candle compared with the
previous candle.

- `open_to_prev_close`: current open compared with the previous close. This
  helps detect gaps or sudden open-price shifts.
- `high_to_prev_close`: current high compared with the previous close. This
  shows how far price pushed upward during the candle.
- `low_to_prev_close`: current low compared with the previous close. This shows
  how far price pushed downward during the candle.
- `log_return_1`: one-candle return using logarithmic return. This is the most
  basic recent price movement.
- `log_return_3`: return over the last 3 candles. This gives short momentum.
- `log_return_12`: return over the last 12 candles. This gives a slightly
  broader momentum view.

Plain meaning: this group answers, "Did price just move up, down, strongly, or
quietly?"

### 2. Candle shape

These features describe the body and wicks of the candle.

- `range_pct`: candle high-low range divided by close. Large values mean the
  candle had a wider trading range.
- `body_pct`: candle close-open body divided by open. Positive means the candle
  closed above its open; negative means it closed below its open.
- `upper_wick_pct`: upper wick size divided by close. A large upper wick can
  mean price rejected higher levels.
- `lower_wick_pct`: lower wick size divided by close. A large lower wick can
  mean price rejected lower levels.

Plain meaning: this group answers, "Was the candle decisive, choppy, rejected
from the top, or rejected from the bottom?"

### 3. EMA trend indicators

EMA means Exponential Moving Average. It is a moving average that reacts more to
recent candles than older candles.

The LSTM uses these EMA periods:

- `EMA20`: short-term trend.
- `EMA50`: medium-term trend.
- `EMA200`: long-term trend.

The model does not directly use the raw EMA price values. It uses normalized
distances and spreads instead:

- `ema20_distance`: close compared with EMA20.
- `ema50_distance`: close compared with EMA50.
- `ema200_distance`: close compared with EMA200.
- `ema20_ema50_spread`: EMA20 compared with EMA50.
- `ema50_ema200_spread`: EMA50 compared with EMA200.

Plain meaning: this group answers, "Is price above or below the short, medium,
and long trend? Are the moving averages stacked bullishly or bearishly?"

### 4. RSI momentum indicator

RSI means Relative Strength Index. It measures whether recent candles have been
more upward or downward.

- `rsi14_scaled`: RSI14 transformed from the normal `0` to `100` scale into a
  centered scale where:
  - near `+1` means very strong upward momentum,
  - near `0` means neutral,
  - near `-1` means very strong downward momentum.

Plain meaning: RSI helps the model see whether the market is stretched upward,
stretched downward, or balanced.

### 5. ATR volatility indicator

ATR means Average True Range. It measures how much price usually moves per
candle, including gaps from the previous close.

- `atr14_pct`: ATR14 divided by close, so volatility is expressed as a
  percentage of price.

Plain meaning: ATR helps the model know whether the market is calm or moving
wildly.

### 6. MACD momentum/trend indicator

MACD means Moving Average Convergence Divergence. It compares a faster EMA with
a slower EMA to measure trend momentum.

The LSTM uses the standard MACD setup:

- Fast EMA: `12`
- Slow EMA: `26`
- Signal EMA: `9`

The saved features are:

- `macd_pct`: MACD value divided by close.
- `macd_signal_pct`: MACD signal line divided by close.
- `macd_histogram_pct`: MACD minus signal line, divided by close.

Plain meaning: MACD helps the model see whether momentum is improving,
weakening, or crossing into a different direction.

### 7. Volume behavior

Volume tells the model whether the move happened with unusual activity.

- `volume_log_change`: change in logarithmic volume from the previous candle.
- `volume_ratio_20`: current volume compared with the 20-candle average volume.

Plain meaning: this group answers, "Is this candle happening with normal volume
or unusual participation?"

### 8. Realized volatility

Realized volatility is calculated from recent returns.

- `realized_volatility_12`: volatility over the last 12 candles.
- `realized_volatility_48`: volatility over the last 48 candles.

Plain meaning: this helps the model distinguish quiet trends from chaotic moves.

### 9. Time features

Crypto trades 24/7, but market behavior can still change depending on time of
day and day of week.

- `hour_sin` and `hour_cos`: represent hour of day.
- `weekday_sin` and `weekday_cos`: represent day of week.

Plain meaning: this lets the model learn if certain hours or days behave
differently without treating time as a simple increasing number.

### 10. Optional Fear & Greed sentiment features

Fear & Greed is a market-sentiment index from `0` to `100`.

- Low values mean fear.
- Middle values mean neutral sentiment.
- High values mean greed.

The project can include it in the LSTM if you provide a CSV file with daily
values. The CSV must have:

- a date column named `date`, `timestamp`, or `time`;
- a numeric `value` column from `0` to `100`.

Example:

```csv
date,value
2024-01-01,65
2024-01-02,71
2024-01-03,58
```

The LSTM adds these optional features:

- `fear_greed_scaled`: Fear & Greed centered around zero. `-1` means extreme
  fear, `0` means neutral, and `+1` means extreme greed.
- `fear_greed_change_1`: one-day change in the index.
- `fear_greed_change_7`: seven-day change in the index.
- `fear_greed_extreme_fear`: `1` when the value is `25` or below, otherwise
  `0`.
- `fear_greed_extreme_greed`: `1` when the value is `75` or above, otherwise
  `0`.

Plain meaning: this tells the model whether the wider crypto market mood is
fearful, greedy, or changing quickly.

Important: Fear & Greed is usually daily data, while your BTCUSDT candles may
be 1h or 4h. The project aligns each candle with the latest available Fear &
Greed value before that candle. This avoids using future sentiment values by
accident.

The authoritative ordered base list is `DEFAULT_FEATURE_COLUMNS` in
`ml/feature_builder.py`. Optional Fear & Greed feature names are in
`data/fear_greed_loader.py`. The exact ordered list used by a trained model is
saved in that model's metadata file.

## Training flow

```text
One-minute OHLCV database rows
              |
              v
Completed target candles (for example, 4h)
              |
              v
28 or 33 normalized features
              |
              v
Sequences of the previous 60 candles
              |
              v
LSTM predicts probability of an upward move
              |
              v
EMA entry accepted or rejected
```

## Resampling filter

The database stores one-minute candles. `--interval` selects the timeframe used
for training.

For `--interval 4h`, one completed candle requires 240 one-minute rows:

- Open: first one-minute open.
- High: highest one-minute high.
- Low: lowest one-minute low.
- Close: last one-minute close.
- Volume: sum of all one-minute volumes.

Incomplete target candles are removed during training. This prevents a partial
4-hour candle from being treated as a completed candle.

## Why features are normalized

Normalized values are used instead of absolute BTC prices so the model can
learn patterns that remain meaningful as the price level changes. For example,
being 2% above EMA20 is more reusable than saying BTC is exactly `$65,000`.

## Warm-up filter

EMA200 and rolling-volatility features require historical candles before their
first valid value exists. Rows containing incomplete feature values are removed
before sequences are created.

## Sequence window

The default sequence length is 60 candles:

```text
4h model: 60 x 4 hours = 10 days of context
1h model: 60 x 1 hour  = 60 hours of context
```

Each training example therefore has this shape without Fear & Greed:

```text
60 timesteps x 28 features
```

With Fear & Greed enabled, the shape becomes:

```text
60 timesteps x 33 features
```

Change it with `--sequence-length`, but retrain the model afterward.

## Learning target

The default model predicts whether the close will be higher one target candle
later:

```text
future close higher -> label 1 (up)
future close lower  -> label 0 (down)
```

`--prediction-horizon` controls how many target candles ahead are examined.
For a 4-hour model:

```text
--prediction-horizon 1 -> 4 hours ahead
--prediction-horizon 3 -> 12 hours ahead
```

## Minimum-movement filter

The default `--minimum-return 0.001` removes training examples whose future
absolute move is below 0.1%. Small changes are treated as market noise rather
than useful up/down labels.

Examples:

```text
+0.30% future move -> label 1
-0.25% future move -> label 0
+0.04% future move -> excluded
```

Increasing this threshold produces clearer labels but fewer training samples.

## Scaling filter

Every feature is standardized:

```text
scaled value = (value - training mean) / training standard deviation
```

The mean and standard deviation are fitted using training data only. Validation
and test candles never influence the scaler. These values are stored in the
model's `.metadata.json` file and reused during prediction.

## Chronological split

Data is never randomly shuffled. The default split is:

```text
First 70% -> training
Next 15%  -> validation
Last 15%  -> testing
```

This order better represents learning from the past and evaluating on later,
unseen candles.

`LSTM_OUT_OF_SAMPLE_ONLY = True` also prevents the backtest filter from trading
on the model's training and validation periods. Only timestamps at or after the
saved `test_start` are eligible.

## Class-balance filter

If the training data contains different numbers of up and down labels, class
weights give the smaller class more importance during training. This reduces the
temptation for the model to predict only the majority direction.

## LSTM architecture

The model contains:

```text
Input: 60 x 28
LSTM: 64 units, returns a sequence
Dropout: 25%
LSTM: 32 units
Dropout: 25%
Dense: 16 ReLU units
Output: one sigmoid probability
```

Dropout randomly disables part of the network during training to reduce
overfitting. The sigmoid output is interpreted as the probability of an upward
move.

If Fear & Greed is enabled, the input becomes `60 x 33` instead of `60 x 28`.

## Entry-confidence filter

The defaults in `config/config.py` are:

```python
LSTM_BUY_THRESHOLD = 0.60
LSTM_SELL_THRESHOLD = 0.40
LSTM_OUT_OF_SAMPLE_ONLY = True
```

They are applied as follows:

```text
EMA buy  + probability >= 0.60 -> allow long entry
EMA short + probability <= 0.40 -> allow short entry
probability between 0.40 and 0.60 -> skip entry
```

The original EMA signals remain responsible for exits. The LSTM does not hold a
position open merely because its prediction changes.

## Saved learning files

Training creates:

```text
ml/models/btcusdt_4h_lstm.keras
ml/models/btcusdt_4h_lstm.metadata.json
```

The `.keras` file stores the network structure and learned weights. The metadata
stores:

- Pair and timeframe.
- Sequence length and prediction horizon.
- Minimum-return threshold.
- Ordered feature names.
- Training-only scaling values.
- Training, validation, and test sample counts.
- Chronological split timestamps.
- Held-out test metrics.

## Reading the metrics

- `accuracy`: proportion of correct up/down predictions.
- `auc`: ranking quality across all possible probability thresholds. `0.50` is
  approximately random and `1.00` is perfect.
- `loss`: binary cross-entropy error. Lower is better; approximately `0.693` is
  typical of uninformative 50/50 predictions.
- `precision`: when the model predicts up, how often it is correct.
- `recall`: how many actual upward moves the model detects.
- `val_*`: the same measurement on chronological validation data during
  training.

A saved model is not automatically a good model. Compare test AUC against
`0.50`, inspect precision and recall together, and then compare the EMA-only
backtest with the EMA + LSTM Filter after fees.

## Why your current result can be bad

If your test AUC is close to `0.50`, the model is not finding a reliable edge.
That does not always mean the code is broken. It can mean:

- the next-candle direction is too noisy;
- the prediction horizon is too short;
- the minimum movement threshold is too small;
- the features are not enough;
- the market regime changed between training and testing;
- the LSTM is overfitting training data but not generalizing;
- fees/slippage destroy a small statistical edge.

For trading, a model that is only slightly better than random may still be bad
after exchange fees. The real question is not only "is accuracy above 50%?"
The better question is: "Does EMA + LSTM improve the final backtest compared
with EMA alone on out-of-sample data?"

## How deep learning works here

The LSTM learns by seeing many examples like this:

```text
last 60 candles of features -> future move was up or down
```

At first, the model guesses almost randomly. During training, it compares its
guess with the correct label. If the guess is wrong, the optimizer slightly
changes the model weights. After thousands of examples, the LSTM may learn
patterns such as:

- price above EMA200 plus rising volume often continues;
- extreme volatility after a big move often reverses;
- RSI strength behaves differently in an uptrend than in a downtrend;
- fear/greed sentiment sometimes helps or hurts continuation setups.

But the LSTM does not know trading rules by itself. It only learns statistical
patterns from the features and labels you give it.

## Can the LSTM find the best way by itself?

Partly, but not completely.

The LSTM can learn hidden patterns inside the feature history. That is the deep
learning part. But it does not automatically know:

- which pair is best;
- which timeframe is best;
- which prediction horizon is best;
- which minimum-return threshold is best;
- whether fees make the strategy profitable;
- whether the model is overfitting.

You still control the experiment design. Think of the LSTM as a smart pattern
finder, not a complete trader or scientist.

To make it search more by itself, you would add a separate tuning script that
trains many models with different settings and compares their out-of-sample
backtests. That is called hyperparameter tuning.

This project includes a tuner at `ml/tune_lstm.py`.

## Practical improvement checklist

Start simple. Change one thing at a time and compare test results plus backtest
results.

Recommended experiments:

1. Try a longer prediction horizon.

   ```bash
   --prediction-horizon 3
   ```

   For a 4h model, this asks the model to predict roughly 12 hours ahead instead
   of 4 hours ahead. This can reduce candle-to-candle noise.

2. Try a stronger minimum move.

   ```bash
   --minimum-return 0.003
   ```

   This ignores tiny future moves below 0.3%. The labels become cleaner, but
   you get fewer training samples.

3. Compare 1h and 4h models.

   ```bash
   --interval 1h
   --interval 4h
   ```

   The 1h model has more samples but more noise. The 4h model has fewer samples
   but cleaner candles.

4. Try different sequence lengths.

   ```bash
   --sequence-length 48
   --sequence-length 120
   ```

   For 4h candles, `60` means 10 days of memory. `120` means 20 days.

5. Add Fear & Greed sentiment.

   ```bash
   --fear-greed-csv data/fear_greed.csv
   ```

   This gives the model market mood, not just price behavior.

6. Compare the final strategy, not only the model metric.

   A model with slightly lower accuracy can still be better if it avoids the
   worst EMA trades. The final test should be:

   ```text
   EMA-only backtest
   versus
   EMA + LSTM filter backtest
   ```

## Training command

Example using BTCUSDT one-minute data stored in PostgreSQL and resampled to 4
hours:

```bash
python -m ml.train_lstm \
  --pair BTCUSDT \
  --interval 4h \
  --model-path ml/models/btcusdt_4h_lstm.keras \
  --database-type postgresql \
  --database-url postgresql://user:password@localhost:5432/dataspider
```

If PostgreSQL is already selected in `config/local_config.py`, the two database
arguments can be omitted:

```bash
python -m ml.train_lstm \
  --pair BTCUSDT \
  --interval 4h \
  --model-path ml/models/btcusdt_4h_lstm.keras
```

Example with Fear & Greed enabled:

```bash
python -m ml.train_lstm \
  --pair BTCUSDT \
  --interval 4h \
  --model-path ml/models/btcusdt_4h_lstm_fng.keras \
  --fear-greed-csv data/fear_greed.csv
```

You can also set the CSV path in `config/config.py` or, preferably, your ignored
`config/local_config.py`:

```python
LSTM_FEAR_GREED_CSV_PATH = "data/fear_greed.csv"
```

If a model was trained with Fear & Greed, prediction/backtesting must use the
same CSV path or the model will not have all required features.

Useful experiments include increasing the historical period, comparing 1-hour
and 4-hour models, changing the prediction horizon, and changing the minimum
movement threshold. Change one major assumption at a time and compare held-out
results rather than training accuracy.

## Tuning command

Tuning means: train many models with different settings, then rank the results.
This lets the project search for a better configuration instead of you changing
one command by hand each time.

Basic tuning run:

```bash
python -m ml.tune_lstm \
  --pair BTCUSDT \
  --interval 4h \
  --max-runs 12
```

That tries combinations from these default lists:

```text
sequence lengths:     48, 60, 96
prediction horizons:  1, 3, 6
minimum returns:      0.001, 0.003, 0.005
learning rates:       0.001, 0.0005
batch sizes:          64
```

Because the full grid is bigger than 12 runs, `--max-runs 12` keeps it from
running forever. You can increase it when you have time.

Tuning with Fear & Greed:

```bash
python -m ml.tune_lstm \
  --pair BTCUSDT \
  --interval 4h \
  --max-runs 12 \
  --fear-greed-csv data/fear_greed.csv
```

Randomized tuning:

```bash
python -m ml.tune_lstm \
  --pair BTCUSDT \
  --interval 4h \
  --max-runs 12 \
  --randomize
```

Custom tuning grid:

```bash
python -m ml.tune_lstm \
  --pair BTCUSDT \
  --interval 4h \
  --sequence-lengths 48,60,120 \
  --prediction-horizons 3,6 \
  --minimum-returns 0.003,0.005 \
  --learning-rates 0.001,0.0005 \
  --max-runs 8
```

The tuner saves models in:

```text
ml/models/tuning/
```

It saves ranked results in:

```text
logs/lstm_tuning_results.csv
logs/lstm_tuning_results.summary.json
```

When choosing the winner, do not look only at training performance. Prefer:

- higher `test_auc`;
- higher `neutral_balanced_success`;
- useful `entry_balanced_success`;
- enough `entry_total_coverage` so the model is not skipping almost everything;
- better EMA + LSTM backtest than EMA-only.

If the best model has high success but tiny coverage, it may not be useful. For
example, 70% success on only 3 signals is not enough evidence.
