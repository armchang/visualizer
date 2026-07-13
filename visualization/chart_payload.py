"""Build JSON payloads compatible with TradingView Lightweight Charts."""

import pandas as pd


def unix_seconds(index):
    """Return Unix seconds for a datetime-like pandas index."""
    return pd.to_datetime(index).astype("int64") // 10**9


def add_time_column(frame):
    """Return a copy with a Lightweight Charts `time` column."""
    result = frame.copy()
    result.index = pd.to_datetime(result.index)
    result["time"] = unix_seconds(result.index)
    return result


def candle_records(frame, completed=None):
    """Return OHLCV candles in the format expected by Lightweight Charts."""
    data = add_time_column(frame)
    records = []
    completed = completed.reindex(data.index) if completed is not None else None

    for timestamp, row in data.iterrows():
        candle = {
            "time": int(row["time"]),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        }
        if completed is not None:
            candle["completed"] = bool(completed.loc[timestamp])
        records.append(candle)
    return records


def signal_markers(frame, completed=None):
    """Return buy/sell markers in Lightweight Charts marker format."""
    data = add_time_column(frame)
    if completed is not None:
        data = data.loc[completed.reindex(data.index).fillna(False)]

    markers = []
    if "buy_signal" in data.columns:
        for row in data[data["buy_signal"]].itertuples():
            markers.append(
                {
                    "time": int(row.time),
                    "position": "belowBar",
                    "color": "lime",
                    "shape": "arrowUp",
                    "text": "Buy",
                }
            )

    if "sell_signal" in data.columns:
        for row in data[data["sell_signal"]].itertuples():
            markers.append(
                {
                    "time": int(row.time),
                    "position": "aboveBar",
                    "color": "red",
                    "shape": "arrowDown",
                    "text": "Sell",
                }
            )

    return sorted(markers, key=lambda marker: marker["time"])


def signal_records(frame, pair, interval, strategy, completed=None):
    """Return past BUY/SELL signals as data records for TradrPro.ai."""
    data = add_time_column(frame)
    if completed is not None:
        data = data.loc[completed.reindex(data.index).fillna(False)]

    records = []
    for timestamp, row in data.iterrows():
        buy_signal = bool(row.get("buy_signal", False))
        sell_signal = bool(row.get("sell_signal", False))
        numeric_signal = row.get("signal", 0)

        if buy_signal and not sell_signal:
            signal = "BUY"
        elif sell_signal and not buy_signal:
            signal = "SELL"
        elif numeric_signal == 1:
            signal = "BUY"
        elif numeric_signal == -1:
            signal = "SELL"
        else:
            continue

        candle_time = timestamp.isoformat()
        records.append(
            {
                "signal": signal,
                "signal_id": f"{pair}:{interval}:{candle_time}:{signal}",
                "pair": pair,
                "interval": interval,
                "strategy": strategy,
                "time": int(row["time"]),
                "candle_time": candle_time,
                "price": float(row["close"]),
                "buy_signal": buy_signal,
                "sell_signal": sell_signal,
            }
        )

    return records


def line_records(frame, column):
    """Return optional indicator line data if the column exists."""
    if column not in frame.columns:
        return []
    data = add_time_column(frame)
    return (
        data[["time", column]]
        .dropna()
        .rename(columns={column: "value"})
        .to_dict(orient="records")
    )


def build_chart_payload(
    frame,
    pair,
    interval,
    strategy,
    latest_signal=None,
    completed=None,
    limit=300,
    signal_limit=None,
    bot_running=False,
):
    """Return chart data for TradrPro.ai to render."""
    if limit:
        frame = frame.tail(limit)
        if completed is not None:
            completed = completed.reindex(frame.index)

    latest_candle = frame.iloc[-1] if not frame.empty else None
    latest_time = frame.index[-1] if not frame.empty else None

    signals = signal_records(
        frame,
        pair=pair,
        interval=interval,
        strategy=strategy,
        completed=completed,
    )
    if signal_limit:
        signals = signals[-signal_limit:]

    return {
        "pair": pair,
        "interval": interval,
        "strategy": strategy,
        "bot_running": bool(bot_running),
        "latest_signal": latest_signal,
        "latest_candle_time": latest_time.isoformat() if latest_time is not None else None,
        "latest_price": float(latest_candle["close"]) if latest_candle is not None else None,
        "candles": candle_records(frame, completed=completed),
        "markers": signal_markers(frame, completed=completed),
        "signals": signals,
        "lines": {
            "trailing_stop": line_records(frame, "trailing_stop"),
            "sma20": line_records(frame, "sma20"),
            "sma50": line_records(frame, "sma50"),
            "sma100": line_records(frame, "sma100"),
            "sma200": line_records(frame, "sma200"),
        },
    }
