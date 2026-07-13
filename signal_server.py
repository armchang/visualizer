"""HTTP signal server for TradrPro.ai.

Run:
    python signal_server.py
    python signal_server.py --port 8001
    python signal_server.py --host 0.0.0.0 --port 8001 --poll-seconds 60

Example calls:

    # Start monitoring BTCUSDT every 60 seconds using EMA Crossover.
    curl -X POST http://127.0.9.1:8000/start \
      -H "Content-Type: application/json" \
      -d '{"pair":"BTCUSDT","interval":"4h","strategy":"scripts.strategies.ema_crossover"}'

    # Check whether the service is running.
    curl http://127.0.9.1:8000/status

    # Get the latest BUY / SELL / HOLD signal.
    curl http://127.0.9.1:8000/latest-signal

    # Get candles and markers for the TradrPro.ai dashboard chart.
    curl "http://127.0.9.1:8000/chart-data?pair=BTCUSDT&interval=4h&limit=300&signal_limit=50&include_live=true"

    # Stop monitoring.
    curl -X POST http://127.0.9.1:8000/stop

Notes:
    - This service only generates signals. It does not execute trades.
    - It does not use LSTM. It uses the selected strategy's compute_signals().
    - The monitor wakes up every minute, reloads candles from the database,
      resamples to the selected interval, and recomputes the latest signal.
    - For intervals like 4h, the server checks every minute but only the latest
      completed 4h candle is used.
    - TradrPro.ai should treat `signal_id` as the deduplication key.
"""

from __future__ import annotations

import argparse
import copy
import importlib
import pkgutil
import threading
import time
import traceback
from datetime import datetime, timezone
from types import SimpleNamespace

from flask import Flask, jsonify, request
import pandas as pd

from config import config
from data.market_data_loader import normalize_interval, resample_ohlcv
from scripts import fetch
import scripts.strategies as strategy_package
from scripts.engine import load_strategy
from visualization.chart_payload import build_chart_payload


DEFAULT_HOST = "127.0.9.1"
DEFAULT_PORT = 8000
DEFAULT_POLL_SECONDS = 60
poll_seconds = DEFAULT_POLL_SECONDS

app = Flask(__name__)

state_lock = threading.Lock()
stop_event = threading.Event()
monitor_thread = None
runtime_state = {
    "running": False,
    "settings": None,
    "latest_signal": None,
    "last_error": None,
    "last_checked_at": None,
    "delivered_signal_ids": set(),
}


@app.after_request
def add_cors_headers(response):
    """Allow TradrPro.ai dashboard pages to read JSON from this service."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _normalize_strategy_path(strategy_path):
    strategy_path = strategy_path or config.STRATEGY
    if "." not in strategy_path:
        return f"scripts.strategies.{strategy_path}"
    return strategy_path


def _available_strategies():
    """Return importable strategy modules exposed by scripts/strategies."""
    strategies = []
    for module_info in pkgutil.iter_modules(strategy_package.__path__):
        name = module_info.name
        if name.startswith("_") or name in {"base_strategy"}:
            continue
        module_path = f"scripts.strategies.{name}"
        try:
            module = importlib.import_module(module_path)
        except Exception:
            continue
        if hasattr(module, "Strategy"):
            strategies.append({"name": name, "path": module_path})
    return sorted(strategies, key=lambda item: item["name"])


def _strategy_names():
    strategies = _available_strategies()
    names = {item["name"] for item in strategies}
    names.update(item["path"] for item in strategies)
    return names


def _validate_strategy_path(strategy_path):
    """Raise a user-friendly error before DB work if the strategy is unknown."""
    normalized = _normalize_strategy_path(strategy_path)
    if normalized in _strategy_names():
        return normalized

    requested_name = normalized.rsplit(".", 1)[-1]
    available = _available_strategies()
    available_names = ", ".join(item["name"] for item in available)
    raise ValueError(
        f"Unsupported strategy {requested_name!r}. "
        f"Available strategies: {available_names or 'none'}."
    )


def _runtime_config(settings):
    """Create a lightweight config object without mutating config/config.py."""
    values = {
        key: copy.deepcopy(value)
        for key, value in vars(config).items()
        if key.isupper()
    }
    values["PAIR_NAME"] = settings["pair"]
    values["RESAMPLE_INTERVAL"] = settings["interval"]
    values["STRATEGY"] = settings["strategy"]
    return SimpleNamespace(**values)


def _settings_from_request(default_settings=None):
    """Resolve pair/interval/strategy from query/body/default config."""
    default_settings = default_settings or {}
    payload = request.get_json(silent=True) or {}

    pair = (
        request.args.get("pair")
        or payload.get("pair")
        or default_settings.get("pair")
        or config.PAIR_NAME
    )
    interval = (
        request.args.get("interval")
        or payload.get("interval")
        or default_settings.get("interval")
        or config.RESAMPLE_INTERVAL
    )
    strategy = (
        request.args.get("strategy")
        or payload.get("strategy")
        or default_settings.get("strategy")
        or config.STRATEGY
    )

    return {
        "pair": str(pair).strip().upper(),
        "interval": normalize_interval(interval),
        "strategy": _validate_strategy_path(strategy),
    }


def _signal_from_row(row):
    buy_signal = bool(row.get("buy_signal", False))
    sell_signal = bool(row.get("sell_signal", False))

    if buy_signal and not sell_signal:
        return "BUY"
    if sell_signal and not buy_signal:
        return "SELL"

    numeric_signal = row.get("signal", 0)
    if numeric_signal == 1:
        return "BUY"
    if numeric_signal == -1:
        return "SELL"

    return "HOLD"


def _timestamp_iso(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _truthy(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _positive_int(value, default):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _load_raw_ohlcv(runtime_config):
    return fetch.get_ohlcv_data(
        runtime_config.DATABASE_TYPE,
        runtime_config.DATABASE_URL,
        runtime_config.TABLE_NAME,
        runtime_config.PAIR_NAME,
    )


def _completion_flags(raw_frame, resampled_frame, interval):
    """Return True for resampled candles containing a complete set of 1m rows."""
    interval = normalize_interval(interval)
    target_duration = pd.Timedelta(interval)
    source_duration = pd.Timedelta("1min")
    if target_duration % source_duration:
        raise ValueError("interval must be an exact multiple of 1-minute source candles")

    expected_rows = int(target_duration / source_duration)
    rows_per_candle = raw_frame["close"].resample(interval).count()
    return rows_per_candle.reindex(resampled_frame.index).fillna(0).astype(int) >= expected_rows


def _compute_strategy_frame(settings, include_live=False):
    """Build a strategy-enriched frame and completion flags."""
    runtime_config = _runtime_config(settings)
    raw_frame = _load_raw_ohlcv(runtime_config)
    frame = resample_ohlcv(
        raw_frame,
        runtime_config.RESAMPLE_INTERVAL,
        source_interval="1min",
        drop_incomplete=not include_live,
    )
    if frame.empty:
        raise ValueError("No candles were available after resampling")

    completed = _completion_flags(raw_frame, frame, runtime_config.RESAMPLE_INTERVAL)
    if not include_live:
        completed = completed.reindex(frame.index).fillna(True)

    strategy = load_strategy(runtime_config.STRATEGY)
    frame = strategy.compute_signals(frame, runtime_config)
    if "signal" not in frame.columns and not {"buy_signal", "sell_signal"}.issubset(frame.columns):
        raise RuntimeError("Strategy did not create signal, buy_signal, or sell_signal columns")

    return runtime_config, frame, completed.reindex(frame.index).fillna(False)


def generate_latest_signal(settings):
    """Load current candles, recompute the strategy, and return one signal."""
    runtime_config, frame, _completed = _compute_strategy_frame(settings, include_live=False)
    latest = frame.iloc[-1]
    candle_time = latest.name
    signal = _signal_from_row(latest)
    price = float(latest["close"])
    signal_id = (
        f"{runtime_config.PAIR_NAME}:"
        f"{runtime_config.RESAMPLE_INTERVAL}:"
        f"{_timestamp_iso(candle_time)}:"
        f"{signal}"
    )

    return {
        "running": True,
        "pair": runtime_config.PAIR_NAME,
        "interval": runtime_config.RESAMPLE_INTERVAL,
        "strategy": runtime_config.STRATEGY,
        "signal": signal,
        "signal_id": signal_id,
        "candle_time": _timestamp_iso(candle_time),
        "price": price,
        "buy_signal": bool(latest.get("buy_signal", False)),
        "sell_signal": bool(latest.get("sell_signal", False)),
        "checked_at": _utc_now_iso(),
    }


def _compute_once():
    with state_lock:
        settings = copy.deepcopy(runtime_state["settings"])

    if not settings:
        return

    try:
        latest_signal = generate_latest_signal(settings)
        with state_lock:
            runtime_state["latest_signal"] = latest_signal
            runtime_state["last_error"] = None
            runtime_state["last_checked_at"] = latest_signal["checked_at"]
    except Exception as exc:  # noqa: BLE001 - keep monitor alive after one bad poll.
        with state_lock:
            runtime_state["last_error"] = {
                "message": str(exc),
                "traceback": traceback.format_exc(),
                "checked_at": _utc_now_iso(),
            }
            runtime_state["last_checked_at"] = runtime_state["last_error"]["checked_at"]


def _monitor_loop():
    while not stop_event.is_set():
        with state_lock:
            running = runtime_state["running"]

        if running:
            _compute_once()

        stop_event.wait(poll_seconds)


def _ensure_monitor_thread():
    global monitor_thread
    if monitor_thread and monitor_thread.is_alive():
        return
    stop_event.clear()
    monitor_thread = threading.Thread(target=_monitor_loop, name="signal-monitor", daemon=True)
    monitor_thread.start()


def _public_state():
    with state_lock:
        latest_signal = copy.deepcopy(runtime_state["latest_signal"])
        settings = copy.deepcopy(runtime_state["settings"])
        last_error = copy.deepcopy(runtime_state["last_error"])
        return {
            "running": runtime_state["running"],
            "settings": settings,
            "latest_signal": latest_signal,
            "last_error": last_error,
            "last_checked_at": runtime_state["last_checked_at"],
            "poll_seconds": poll_seconds,
        }


@app.post("/start")
def start():
    try:
        settings = _settings_from_request()
    except ValueError as exc:
        return jsonify({"error": str(exc), "available_strategies": _available_strategies()}), 400

    with state_lock:
        runtime_state["running"] = True
        runtime_state["settings"] = settings
        runtime_state["latest_signal"] = None
        runtime_state["last_error"] = None
        runtime_state["last_checked_at"] = None
        runtime_state["delivered_signal_ids"] = set()

    _ensure_monitor_thread()
    _compute_once()

    return jsonify(_public_state())


@app.post("/stop")
def stop():
    with state_lock:
        runtime_state["running"] = False
    return jsonify(_public_state())


@app.get("/status")
def status():
    return jsonify(_public_state())


@app.get("/strategies")
def strategies():
    """Return strategy names TradrPro.ai may pass to /start or /chart-data."""
    return jsonify({"strategies": _available_strategies()})


@app.get("/latest-signal")
def latest_signal():
    with state_lock:
        signal = copy.deepcopy(runtime_state["latest_signal"])
        if signal is None:
            return jsonify(
                {
                    "running": runtime_state["running"],
                    "signal": "HOLD",
                    "is_new_signal": False,
                    "message": "No signal has been computed yet. Call POST /start first.",
                }
            )

        signal_id = signal["signal_id"]
        already_delivered = signal_id in runtime_state["delivered_signal_ids"]
        is_trade_signal = signal["signal"] in {"BUY", "SELL"}
        signal["is_new_signal"] = is_trade_signal and not already_delivered
        if is_trade_signal:
            runtime_state["delivered_signal_ids"].add(signal_id)
        signal["running"] = runtime_state["running"]

    return jsonify(signal)


@app.get("/chart-data")
def chart_data():
    """Return live chart candles and completed-candle markers for TradrPro.ai."""
    with state_lock:
        default_settings = copy.deepcopy(runtime_state["settings"]) or {}
        bot_running = runtime_state["running"]
        stored_latest_signal = copy.deepcopy(runtime_state["latest_signal"])

    try:
        settings = _settings_from_request(default_settings)
    except ValueError as exc:
        return jsonify({"error": str(exc), "available_strategies": _available_strategies()}), 400
    include_live = _truthy(request.args.get("include_live"), default=True)
    limit = _positive_int(request.args.get("limit"), 300)
    signal_limit = _positive_int(request.args.get("signal_limit"), 100)

    try:
        runtime_config, frame, completed = _compute_strategy_frame(settings, include_live=include_live)
        latest_signal_value = None
        if stored_latest_signal and stored_latest_signal.get("pair") == runtime_config.PAIR_NAME:
            if stored_latest_signal.get("interval") == runtime_config.RESAMPLE_INTERVAL:
                if stored_latest_signal.get("strategy") == runtime_config.STRATEGY:
                    latest_signal_value = stored_latest_signal.get("signal")
        if latest_signal_value is None:
            latest_signal_value = generate_latest_signal(settings)["signal"]

        payload = build_chart_payload(
            frame,
            pair=runtime_config.PAIR_NAME,
            interval=runtime_config.RESAMPLE_INTERVAL,
            strategy=runtime_config.STRATEGY,
            latest_signal=latest_signal_value,
            completed=completed,
            limit=limit,
            signal_limit=signal_limit,
            bot_running=bot_running,
        )
        payload["include_live"] = include_live
        payload["signal_limit"] = signal_limit
        payload["checked_at"] = _utc_now_iso()
        return jsonify(payload)
    except Exception as exc:  # noqa: BLE001 - return useful dashboard errors.
        return (
            jsonify(
                {
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                    "pair": settings["pair"],
                    "interval": settings["interval"],
                    "strategy": settings["strategy"],
                    "checked_at": _utc_now_iso(),
                }
            ),
            500,
        )


@app.post("/refresh")
def refresh():
    """Force one immediate recompute without waiting for the next minute."""
    with state_lock:
        if not runtime_state["running"]:
            return jsonify({"running": False, "message": "Signal server is stopped."}), 409
    _compute_once()
    return jsonify(_public_state())


def parse_args():
    parser = argparse.ArgumentParser(description="Run the Visualizer signal HTTP server.")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Host to bind. Default: {DEFAULT_HOST}")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port to bind. Default: {DEFAULT_PORT}")
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=DEFAULT_POLL_SECONDS,
        help=f"Seconds between automatic signal checks. Default: {DEFAULT_POLL_SECONDS}",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.poll_seconds < 1:
        raise ValueError("--poll-seconds must be at least 1")
    poll_seconds = args.poll_seconds
    app.run(host=args.host, port=args.port)
