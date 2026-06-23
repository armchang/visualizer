"""Train an LSTM direction classifier from the configured OHLCV database."""

import argparse
import json
from pathlib import Path

import numpy as np

from config import config
from data.fear_greed_loader import add_fear_greed_features
from data.market_data_loader import load_ohlcv_from_db, resample_ohlcv
from ml.feature_builder import (
    build_feature_frame,
    build_sequences,
    build_targets,
    feature_columns_for_training,
    fit_standardizer,
    standardize,
)


def _load_keras():
    try:
        from tensorflow import keras
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "TensorFlow is required for LSTM training. Install requirements-ml.txt."
        ) from exc
    return keras


def build_model(sequence_length, feature_count, learning_rate=0.001):
    """Build a compact two-layer LSTM binary classifier."""
    keras = _load_keras()
    model = keras.Sequential(
        [
            keras.layers.Input(shape=(sequence_length, feature_count)),
            keras.layers.LSTM(64, return_sequences=True),
            keras.layers.Dropout(0.25),
            keras.layers.LSTM(32),
            keras.layers.Dropout(0.25),
            keras.layers.Dense(16, activation="relu"),
            keras.layers.Dense(1, activation="sigmoid"),
        ]
    )
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=learning_rate),
        loss="binary_crossentropy",
        metrics=[
            keras.metrics.BinaryAccuracy(name="accuracy"),
            keras.metrics.AUC(name="auc"),
            keras.metrics.Precision(name="precision"),
            keras.metrics.Recall(name="recall"),
        ],
    )
    return model


def _class_weights(targets):
    counts = np.bincount(targets.astype(int), minlength=2)
    if np.any(counts == 0):
        return None
    total = counts.sum()
    return {0: total / (2.0 * counts[0]), 1: total / (2.0 * counts[1])}


def _success_rate_report(probabilities, targets, buy_threshold=0.5, sell_threshold=0.5):
    """Return user-friendly up/down success rates from model probabilities."""
    probabilities = np.asarray(probabilities, dtype="float32").reshape(-1)
    targets = np.asarray(targets, dtype="float32").reshape(-1)

    buy_mask = probabilities >= buy_threshold
    sell_mask = probabilities <= sell_threshold
    total = len(targets)

    def summarize(mask, winning_target):
        signal_count = int(mask.sum())
        if signal_count == 0:
            return {
                "signals": 0,
                "success_rate": None,
                "wins": 0,
                "losses": 0,
                "coverage": 0.0,
            }
        wins = int((targets[mask] == winning_target).sum())
        losses = signal_count - wins
        return {
            "signals": signal_count,
            "success_rate": wins / signal_count,
            "wins": wins,
            "losses": losses,
            "coverage": signal_count / total if total else 0.0,
        }

    up_count = int((targets == 1).sum())
    down_count = int((targets == 0).sum())
    return {
        "buy_threshold": float(buy_threshold),
        "sell_threshold": float(sell_threshold),
        "test_samples": int(total),
        "actual_up_samples": up_count,
        "actual_down_samples": down_count,
        "actual_up_rate": up_count / total if total else 0.0,
        "actual_down_rate": down_count / total if total else 0.0,
        "buy_success": summarize(buy_mask, 1.0),
        "sell_success": summarize(sell_mask, 0.0),
    }


def _format_rate(value):
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"


def _print_success_report(title, report):
    """Print a plain-English summary of test-set up/down success rates."""
    buy = report["buy_success"]
    sell = report["sell_success"]
    print(title)
    print(
        "  Test labels: "
        f"{report['actual_up_samples']} up ({_format_rate(report['actual_up_rate'])}), "
        f"{report['actual_down_samples']} down ({_format_rate(report['actual_down_rate'])})"
    )
    print(
        "  Buy/up calls: "
        f"{buy['signals']} signals, {buy['wins']} wins, {buy['losses']} losses, "
        f"success {_format_rate(buy['success_rate'])}, coverage {_format_rate(buy['coverage'])}"
    )
    print(
        "  Sell/down calls: "
        f"{sell['signals']} signals, {sell['wins']} wins, {sell['losses']} losses, "
        f"success {_format_rate(sell['success_rate'])}, coverage {_format_rate(sell['coverage'])}"
    )


def train(
    pair,
    interval,
    model_path,
    sequence_length=60,
    prediction_horizon=1,
    minimum_return=0.001,
    train_fraction=0.70,
    validation_fraction=0.15,
    epochs=50,
    batch_size=64,
    learning_rate=0.001,
    database_type=None,
    database_url=None,
    fear_greed_csv=None,
):
    """Train chronologically and save the model plus preprocessing metadata."""
    if train_fraction <= 0 or validation_fraction <= 0:
        raise ValueError("Training and validation fractions must be positive")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("Training plus validation fractions must be below 1")

    pair = pair.strip().upper()
    # RESAMPLING CHANGE 1: Load the raw 1-minute candles without aggregating them.
    frame_1m = load_ohlcv_from_db(
        pair=pair,
        database_type=database_type,
        database_url=database_url,
    )
    print(f"Loaded 1-minute candles: {len(frame_1m):,} rows")

    # RESAMPLING CHANGE 2: Build completed target-timeframe candles before features.
    # A 4h candle uses: first open, maximum high, minimum low, last close, and
    # summed volume from exactly 240 one-minute rows.
    frame = resample_ohlcv(
        frame_1m,
        interval,
        source_interval="1min",
        drop_incomplete=True,
    )
    print(f"Resampled {interval} candles: {len(frame):,} rows")
    print(f"Resampled range: {frame.index.min()} -> {frame.index.max()}")

    if frame.empty:
        raise ValueError(f"No complete {interval} candles were produced from the 1-minute data")

    include_fear_greed = bool(fear_greed_csv)
    if include_fear_greed:
        frame = add_fear_greed_features(frame, fear_greed_csv)
        print(f"Added Fear & Greed features from: {fear_greed_csv}")

    feature_columns = feature_columns_for_training(include_fear_greed)

    # RESAMPLING CHANGE 3: Indicators and LSTM sequences now use resampled data.
    features = build_feature_frame(frame, feature_columns)
    close = frame["close"].reindex(features.index).astype(float)
    targets = build_targets(close, prediction_horizon, minimum_return).reindex(features.index)

    sample_count = len(features) - sequence_length + 1
    if sample_count < 100:
        raise ValueError("Not enough clean candles to train the LSTM")

    train_row_end = int(len(features) * train_fraction)
    validation_row_end = int(len(features) * (train_fraction + validation_fraction))
    mean, scale = fit_standardizer(features.iloc[:train_row_end].to_numpy())
    scaled_values = standardize(features.to_numpy(), mean, scale)
    sequences, sequence_targets = build_sequences(
        scaled_values,
        targets.to_numpy(dtype="float32"),
        sequence_length,
    )

    endpoint_positions = np.arange(sequence_length - 1, len(features))
    valid_target = ~np.isnan(sequence_targets)
    train_mask = valid_target & (endpoint_positions < train_row_end)
    validation_mask = valid_target & (endpoint_positions >= train_row_end) & (
        endpoint_positions < validation_row_end
    )
    test_mask = valid_target & (endpoint_positions >= validation_row_end)

    x_train, y_train = sequences[train_mask], sequence_targets[train_mask]
    x_validation, y_validation = sequences[validation_mask], sequence_targets[validation_mask]
    x_test, y_test = sequences[test_mask], sequence_targets[test_mask]
    if min(len(x_train), len(x_validation), len(x_test)) == 0:
        raise ValueError("A chronological data split is empty; provide more candles")

    keras = _load_keras()
    keras.utils.set_random_seed(42)
    model = build_model(sequence_length, len(feature_columns), learning_rate)
    callbacks = [
        keras.callbacks.EarlyStopping(
            monitor="val_auc",
            mode="max",
            patience=8,
            restore_best_weights=True,
        ),
        keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.5,
            patience=4,
            min_lr=1e-5,
        ),
    ]
    model.fit(
        x_train,
        y_train,
        validation_data=(x_validation, y_validation),
        epochs=epochs,
        batch_size=batch_size,
        callbacks=callbacks,
        class_weight=_class_weights(y_train),
        shuffle=False,
        verbose=1,
    )

    test_values = model.evaluate(x_test, y_test, verbose=0, return_dict=True)
    test_probabilities = np.asarray(model.predict(x_test, batch_size=batch_size, verbose=0)).reshape(-1)
    neutral_success_report = _success_rate_report(
        test_probabilities,
        y_test,
        buy_threshold=0.5,
        sell_threshold=0.5,
    )
    entry_filter_success_report = _success_rate_report(
        test_probabilities,
        y_test,
        buy_threshold=getattr(config, "LSTM_BUY_THRESHOLD", 0.60),
        sell_threshold=getattr(config, "LSTM_SELL_THRESHOLD", 0.40),
    )
    model_path = Path(model_path).expanduser()
    if model_path.suffix != ".keras":
        raise ValueError("model_path must end with .keras")
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model.save(model_path)

    metadata = {
        "format_version": 1,
        "pair": pair,
        "interval": interval,
        "sequence_length": sequence_length,
        "prediction_horizon": prediction_horizon,
        "minimum_return": minimum_return,
        "feature_columns": feature_columns,
        "fear_greed_csv": str(fear_greed_csv) if fear_greed_csv else None,
        "feature_mean": mean.tolist(),
        "feature_scale": scale.tolist(),
        "train_fraction": train_fraction,
        "validation_fraction": validation_fraction,
        "training_samples": int(len(x_train)),
        "validation_samples": int(len(x_validation)),
        "test_samples": int(len(x_test)),
        "training_end": features.index[train_row_end - 1].isoformat(),
        "validation_end": features.index[validation_row_end - 1].isoformat(),
        "test_start": features.index[validation_row_end].isoformat(),
        "test_metrics": {key: float(value) for key, value in test_values.items()},
        "neutral_success_report": neutral_success_report,
        "entry_filter_success_report": entry_filter_success_report,
    }
    metadata_path = model_path.with_suffix(".metadata.json")
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"Saved model: {model_path}")
    print(f"Saved metadata: {metadata_path}")
    print(f"Test metrics: {metadata['test_metrics']}")
    _print_success_report("Friendly test summary at 50/50 threshold:", neutral_success_report)
    _print_success_report("Friendly entry-filter summary using config thresholds:", entry_filter_success_report)
    return model, metadata


def parse_args():
    default_model = Path("ml/models") / f"{config.PAIR_NAME.lower()}_{config.RESAMPLE_INTERVAL}_lstm.keras"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", default=config.PAIR_NAME)
    parser.add_argument("--interval", default=config.RESAMPLE_INTERVAL)
    parser.add_argument("--model-path", default=str(default_model))
    parser.add_argument("--sequence-length", type=int, default=60)
    parser.add_argument("--prediction-horizon", type=int, default=1)
    parser.add_argument("--minimum-return", type=float, default=0.001)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=0.001)
    parser.add_argument(
        "--fear-greed-csv",
        default=getattr(config, "LSTM_FEAR_GREED_CSV_PATH", None),
        help="Optional CSV with daily Fear & Greed Index values to add as LSTM features",
    )
    parser.add_argument(
        "--database-type",
        choices=("postgresql", "sqlite"),
        help="Override the configured database type for this training run",
    )
    parser.add_argument(
        "--database-url",
        help="Override the configured database URL for this training run",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    train(
        pair=arguments.pair,
        interval=arguments.interval,
        model_path=arguments.model_path,
        sequence_length=arguments.sequence_length,
        prediction_horizon=arguments.prediction_horizon,
        minimum_return=arguments.minimum_return,
        epochs=arguments.epochs,
        batch_size=arguments.batch_size,
        learning_rate=arguments.learning_rate,
        database_type=arguments.database_type,
        database_url=arguments.database_url,
        fear_greed_csv=arguments.fear_greed_csv,
    )
