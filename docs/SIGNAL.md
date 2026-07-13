# Signal Server and TradrPro.ai Dashboard Guide

This guide explains how the Visualizer project should provide live signal and
chart data to the TradrPro.ai dashboard.

The main idea:

```text
DataSpider PostgreSQL
        ↓
Visualizer signal_server.py
        ↓
HTTP JSON endpoints
        ↓
TradrPro.ai dashboard
```

Visualizer should calculate candles, indicators, and strategy signals.
TradrPro.ai should display the dashboard and decide what to do with the
returned signal data.

## Implementation requirements

This section is the practical contract between Visualizer and TradrPro.ai.

### Visualizer requirements

Visualizer must provide an HTTP service that TradrPro.ai can call.

Required service:

```text
signal_server.py
```

Required existing endpoints:

```text
POST /start
POST /stop
GET  /status
GET  /latest-signal
POST /refresh
```

Required future endpoint for the dashboard chart:

```text
GET /chart-data
```

Visualizer must be responsible for:

```text
Reading OHLCV rows from the DataSpider database
Filtering by pair
Resampling 1-minute candles into the requested timeframe
Computing strategy indicators
Computing BUY / SELL / HOLD signals
Returning JSON payloads to TradrPro.ai
```

Visualizer should not be responsible for:

```text
Rendering the TradrPro.ai dashboard UI
Executing exchange trades
Managing user accounts
Managing exchange API keys
```

### TradrPro.ai requirements

TradrPro.ai must call Visualizer's HTTP endpoints.

TradrPro.ai must be responsible for:

```text
Calling /start when the user starts the bot
Calling /stop when the user stops the bot
Calling /status to show running/stopped state
Calling /latest-signal to get confirmed BUY / SELL / HOLD
Calling /chart-data to update the live chart
Rendering candles and markers in the dashboard
Deduplicating trade signals using signal_id
Deciding whether to execute a trade
```

TradrPro.ai should not copy Visualizer's `plotter_tv.py`.

Instead, TradrPro.ai should consume JSON from Visualizer and render the chart
using its own frontend.

### Data requirements

DataSpider must keep writing 1-minute OHLCV rows into PostgreSQL.

Required OHLCV table:

```text
ohclv
```

Required columns:

```text
pair
open_time
open
high
low
close
volume
```

Visualizer expects this data flow:

```text
DataSpider writes 1-minute candles
        ↓
Visualizer reads those candles
        ↓
Visualizer resamples to 15min / 1h / 4h / 1d
        ↓
Visualizer computes strategy signals
        ↓
TradrPro.ai receives chart and signal JSON
```

### Runtime requirements

Visualizer should run as a local or server-side HTTP service.

Example:

```bash
python signal_server.py --host 127.0.0.1 --port 8002
```

If TradrPro.ai runs on the same machine, local HTTP is enough:

```text
http://127.0.0.1:8002
```

If TradrPro.ai runs on another machine or over the internet, Visualizer should
be exposed through a secure HTTPS layer such as:

```text
Cloudflare Tunnel
Caddy
Nginx
```

Recommended easiest option for local development:

```text
Cloudflare Tunnel
```

### Signal requirements

Confirmed trade signals must use completed candles only.

Requirement:

```python
drop_incomplete=True
```

This applies to:

```text
/latest-signal
```

Allowed signal values:

```text
BUY
SELL
HOLD
```

Signal meaning:

```text
BUY  = long entry signal
SELL = short entry signal
HOLD = no confirmed trade signal
```

Each confirmed signal response must include:

```text
pair
interval
strategy
signal
signal_id
candle_time
price
is_new_signal
```

`signal_id` is required so TradrPro.ai can avoid processing the same signal more
than once.

### Chart requirements

Live chart data may include the unfinished active candle.

Requirement:

```python
drop_incomplete=False
```

This applies to:

```text
/chart-data
```

The chart payload must include:

```text
pair
interval
bot_running
latest_signal
candles
markers
signals
```

Each candle must include:

```text
time
open
high
low
close
volume
completed
```

`time` should be Unix seconds because TradingView Lightweight Charts accepts
that format directly.

The active unfinished candle must be marked:

```json
"completed": false
```

Completed candles must be marked:

```json
"completed": true
```

Trade markers and historical signal records should only be created from
completed candles.

Each historical signal record must include:

```text
signal
signal_id
pair
interval
strategy
time
candle_time
price
buy_signal
sell_signal
```

### Polling requirements

TradrPro.ai can poll Visualizer every 60 seconds.

Recommended polling loop:

```text
Every 60 seconds:
  GET /status
  GET /chart-data?pair=BTCUSDT&interval=4h&limit=300&signal_limit=50&include_live=true
  GET /latest-signal
```

This matches the DataSpider flow because DataSpider stores one new candle per
minute.

### Error-handling requirements

Visualizer responses should clearly report errors.

Examples:

```text
Database unavailable
No OHLCV rows found for pair
Strategy did not produce signal columns
No completed candle available yet
```

TradrPro.ai should display these errors in the dashboard instead of silently
failing.

### Security requirements

For local development:

```text
HTTP on 127.0.0.1 is acceptable.
```

For production or internet access:

```text
Use HTTPS.
Restrict access to trusted clients.
Do not expose database credentials.
Do not expose exchange API keys from Visualizer.
```

If TradrPro.ai will call Visualizer over the internet, add one of these before
production:

```text
Cloudflare Tunnel access rule
API key header
Bearer token
IP allowlist
```

### Minimum viable integration

The simplest useful integration is:

```text
1. Start Visualizer signal server.
2. TradrPro.ai calls POST /start.
3. TradrPro.ai polls GET /chart-data every minute.
4. TradrPro.ai polls GET /latest-signal every minute.
5. TradrPro.ai renders candles and displays BUY / SELL / HOLD.
```

This does not require copying chart files between projects.

## Main objective

The signal server should do two related jobs:

1. Generate confirmed trading signals.
2. Provide live candle data for the dashboard chart.

These should be handled differently.

```text
Confirmed signals:
Use completed timeframe candles only.
Safe for BUY / SELL / HOLD.

Live chart updates:
Can include the unfinished active candle.
Good for showing that the bot is running.
Not safe for final trade signals.
```

## Current signal flow

The current `signal_server.py` is mainly for confirmed signals.

Step by step:

1. Start the server.

   ```bash
   python signal_server.py --host 127.0.0.1 --port 8002
   ```

2. TradrPro.ai calls `/start`.

   ```bash
   curl -X POST http://127.0.0.1:8002/start \
     -H "Content-Type: application/json" \
     -d '{"pair":"BTCUSDT","interval":"4h","strategy":"scripts.strategies.ema_crossover"}'
   ```

3. Visualizer reads OHLCV rows from the DataSpider database.

   It uses the configured database settings:

   ```python
   DATABASE_TYPE
   DATABASE_URL
   TABLE_NAME = "ohclv"
   ```

4. Visualizer filters by the requested pair.

   Example:

   ```text
   BTCUSDT
   ```

5. Visualizer resamples the stored 1-minute candles into the requested
   timeframe.

   Example:

   ```text
   1-minute candles -> 4h candles
   ```

6. Visualizer runs the selected strategy.

   Example:

   ```text
   scripts.strategies.ema_crossover
   ```

7. The strategy produces signal columns.

   Common columns:

   ```text
   buy_signal
   sell_signal
   signal
   ```

8. TradrPro.ai calls `/latest-signal`.

   ```bash
   curl http://127.0.0.1:8002/latest-signal
   ```

9. Visualizer returns:

   ```text
   BUY
   SELL
   HOLD
   ```

Example response:

```json
{
  "running": true,
  "pair": "BTCUSDT",
  "interval": "4h",
  "strategy": "scripts.strategies.ema_crossover",
  "signal": "BUY",
  "signal_id": "BTCUSDT:4h:2026-06-28T08:00:00:BUY",
  "candle_time": "2026-06-28T08:00:00",
  "price": 64250.5,
  "buy_signal": true,
  "sell_signal": false,
  "is_new_signal": true
}
```

## Why completed candles matter for signals

For trade signals, the server should use:

```python
drop_incomplete=True
```

This means the latest unfinished timeframe candle is ignored.

Example with a 4h timeframe:

```text
12:00 candle starts
12:01 still forming
12:02 still forming
...
15:59 still forming
16:00 candle completed
```

The confirmed signal should only be generated after the 4h candle is complete.

This avoids repainting.

Repainting means:

```text
A BUY signal appears while the candle is forming.
Then the candle changes.
The BUY signal disappears before candle close.
```

That is dangerous for automated trading.

## Live chart updates

For the chart, it is okay to include the unfinished active candle.

The chart endpoint should use:

```python
drop_incomplete=False
```

This allows the current candle body to update every minute as DataSpider writes
new 1-minute candles into PostgreSQL.

Example with a 4h chart:

```text
12:00 active 4h candle starts
12:01 chart updates close/high/low/volume
12:02 chart updates again
12:03 chart updates again
...
16:00 candle becomes completed
```

This is good for the dashboard because it shows:

```text
The bot is running.
New market data is arriving.
The current candle is actively changing.
```

But this active candle should not be used for confirmed BUY / SELL signals.

Recommended split:

```text
/latest-signal
Uses completed candles only.
Safe for BUY / SELL / HOLD.

/chart-data or /live-candles
Includes the unfinished candle.
Good for realtime dashboard display.
```

## Should TradrPro.ai copy `plotter_tv.py`?

No.

Do not copy `plotter_tv.py` into TradrPro.ai.

Better design:

```text
Visualizer owns candle and signal calculation.
TradrPro.ai owns dashboard display.
They communicate with JSON.
```

`plotter_tv.py` currently mixes two responsibilities:

```text
1. Convert pandas DataFrame data into Lightweight Charts format.
2. Create a Flask HTML page to display the chart.
```

For TradrPro.ai, we only need the data-formatting idea.

The dashboard should request JSON from Visualizer and render it using its own
frontend.

## Recommended chart-data endpoint

Add an endpoint later:

```text
GET /chart-data?pair=BTCUSDT&interval=4h&limit=300
```

Possible response:

```json
{
  "pair": "BTCUSDT",
  "interval": "4h",
  "bot_running": true,
  "latest_signal": "HOLD",
  "candles": [
    {
      "time": 1719360000,
      "open": 64000,
      "high": 64500,
      "low": 63800,
      "close": 64250,
      "volume": 1234,
      "completed": true
    },
    {
      "time": 1719374400,
      "open": 64250,
      "high": 64320,
      "low": 64180,
      "close": 64290,
      "volume": 245,
      "completed": false
    }
  ],
  "markers": [
    {
      "time": 1719360000,
      "position": "belowBar",
      "color": "lime",
      "shape": "arrowUp",
      "text": "Buy"
    }
  ],
  "signals": [
    {
      "signal": "BUY",
      "signal_id": "BTCUSDT:4h:2026-06-28T08:00:00:BUY",
      "pair": "BTCUSDT",
      "interval": "4h",
      "strategy": "scripts.strategies.ema_crossover",
      "time": 1719360000,
      "candle_time": "2026-06-28T08:00:00",
      "price": 64250.5,
      "buy_signal": true,
      "sell_signal": false
    }
  ]
}
```

The `candles` format matches what TradingView Lightweight Charts expects:

```json
{
  "time": 1719360000,
  "open": 64000,
  "high": 64500,
  "low": 63800,
  "close": 64250
}
```

Volume can be sent separately or included in each candle. The existing
`plotter_tv.py` already includes `volume`.

## Completed flag

The chart data should include:

```json
"completed": true
```

or:

```json
"completed": false
```

This lets the dashboard visually distinguish:

```text
completed candles = confirmed
latest active candle = still forming
```

Recommended display:

```text
Solid candles: completed
Faded last candle: still forming
BUY / SELL markers: completed candles only
```

## Dashboard polling

The easiest integration is polling.

TradrPro.ai can call Visualizer every 60 seconds:

```text
GET /chart-data?pair=BTCUSDT&interval=4h&limit=300
GET /latest-signal
```

This matches the DataSpider update cycle because DataSpider stores 1-minute
candles.

Simple dashboard loop:

```text
Every 60 seconds:
  1. Fetch /chart-data
  2. Update candle chart
  3. Fetch /latest-signal
  4. Update signal panel
```

Later, this can be upgraded to WebSockets or Server-Sent Events, but polling is
the simplest first version.

## Reusing `plotter_tv.py`

The useful part of `plotter_tv.py` is the payload shape:

```python
df[["time", "open", "high", "low", "close", "volume"]].to_dict(orient="records")
```

And the marker shape:

```json
{
  "time": 1719360000,
  "position": "belowBar",
  "color": "lime",
  "shape": "arrowUp",
  "text": "Buy"
}
```

The future improvement would be to move this reusable formatting logic into a
helper file, for example:

```text
visualization/chart_payload.py
```

Then both places can use the same formatter:

```text
plotter_tv.py
signal_server.py
```

That avoids duplicate formatting code.

## Recommended endpoint design

Current endpoints:

```text
POST /start
POST /stop
GET  /status
GET  /latest-signal
POST /refresh
```

Recommended future endpoint:

```text
GET /chart-data
```

Possible parameters:

```text
pair=BTCUSDT
interval=4h
strategy=scripts.strategies.ema_crossover
limit=300
signal_limit=50
include_live=true
```

Example:

```bash
curl "http://127.0.0.1:8002/chart-data?pair=BTCUSDT&interval=4h&limit=300&signal_limit=50&include_live=true"
```

Meaning:

```text
pair: which symbol to load from DataSpider's OHLCV table
interval: chart timeframe
limit: how many resampled candles to return
signal_limit: how many past BUY / SELL records to return
include_live: whether to include the unfinished active candle
```

## Recommended responsibilities

Visualizer:

```text
Read OHLCV from DataSpider database
Resample 1-minute candles
Compute indicators and strategy signals
Return JSON payloads
```

TradrPro.ai:

```text
Call Visualizer HTTP endpoints
Render dashboard chart
Display bot running/stopped status
Display BUY / SELL / HOLD
Handle execution logic
Handle user controls
```

## Summary

Do this:

```text
Keep plotter/chart calculation in Visualizer.
Send JSON to TradrPro.ai.
Let TradrPro.ai render the dashboard.
Use completed candles for signals.
Use live unfinished candles only for chart updates.
```

Do not do this:

```text
Do not copy plotter_tv.py into TradrPro.ai.
Do not generate real trade signals from unfinished candles.
Do not mix backtest equity/trade simulation with realtime signal generation.
```
