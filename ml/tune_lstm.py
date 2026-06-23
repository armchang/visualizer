"""Try multiple LSTM training configurations and rank the results."""

import argparse
import csv
import itertools
import json
import random
import re
from pathlib import Path

from config import config
from ml.train_lstm import train


def _split_values(raw, cast):
    if raw is None:
        return []
    return [cast(value.strip()) for value in str(raw).split(",") if value.strip()]


def _safe_token(value):
    text = str(value).lower()
    text = text.replace(".", "p")
    return re.sub(r"[^a-z0-9_-]+", "_", text).strip("_")


def _rate(report, side, key):
    try:
        value = report[side][key]
    except (KeyError, TypeError):
        return None
    return None if value is None else float(value)


def _average_present(*values):
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _flatten_result(run_number, model_path, params, metadata):
    test_metrics = metadata.get("test_metrics", {})
    neutral = metadata.get("neutral_success_report", {})
    entry = metadata.get("entry_filter_success_report", {})
    neutral_buy = _rate(neutral, "buy_success", "success_rate")
    neutral_sell = _rate(neutral, "sell_success", "success_rate")
    entry_buy = _rate(entry, "buy_success", "success_rate")
    entry_sell = _rate(entry, "sell_success", "success_rate")
    entry_buy_coverage = _rate(entry, "buy_success", "coverage")
    entry_sell_coverage = _rate(entry, "sell_success", "coverage")

    return {
        "status": "ok",
        "run": run_number,
        "model_path": str(model_path),
        "sequence_length": params["sequence_length"],
        "prediction_horizon": params["prediction_horizon"],
        "minimum_return": params["minimum_return"],
        "learning_rate": params["learning_rate"],
        "batch_size": params["batch_size"],
        "epochs": params["epochs"],
        "fear_greed": bool(params.get("fear_greed_csv")),
        "test_auc": float(test_metrics.get("auc", 0.0)),
        "test_accuracy": float(test_metrics.get("accuracy", 0.0)),
        "test_loss": float(test_metrics.get("loss", 0.0)),
        "test_precision": float(test_metrics.get("precision", 0.0)),
        "test_recall": float(test_metrics.get("recall", 0.0)),
        "neutral_buy_success": neutral_buy,
        "neutral_sell_success": neutral_sell,
        "neutral_balanced_success": _average_present(neutral_buy, neutral_sell),
        "entry_buy_success": entry_buy,
        "entry_sell_success": entry_sell,
        "entry_balanced_success": _average_present(entry_buy, entry_sell),
        "entry_buy_coverage": entry_buy_coverage,
        "entry_sell_coverage": entry_sell_coverage,
        "entry_total_coverage": (entry_buy_coverage or 0.0) + (entry_sell_coverage or 0.0),
        "training_samples": metadata.get("training_samples"),
        "validation_samples": metadata.get("validation_samples"),
        "test_samples": metadata.get("test_samples"),
        "error": "",
    }


def _score(row, sort_by):
    value = row.get(sort_by)
    if value is None:
        return -1.0
    return float(value)


def _write_results(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "status",
        "run",
        "model_path",
        "sequence_length",
        "prediction_horizon",
        "minimum_return",
        "learning_rate",
        "batch_size",
        "epochs",
        "fear_greed",
        "test_auc",
        "test_accuracy",
        "test_loss",
        "test_precision",
        "test_recall",
        "neutral_buy_success",
        "neutral_sell_success",
        "neutral_balanced_success",
        "entry_buy_success",
        "entry_sell_success",
        "entry_balanced_success",
        "entry_buy_coverage",
        "entry_sell_coverage",
        "entry_total_coverage",
        "training_samples",
        "validation_samples",
        "test_samples",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _model_path(output_dir, prefix, params):
    parts = [
        prefix,
        f"{params['interval']}",
        f"s{params['sequence_length']}",
        f"h{params['prediction_horizon']}",
        f"r{_safe_token(params['minimum_return'])}",
        f"lr{_safe_token(params['learning_rate'])}",
    ]
    if params.get("fear_greed_csv"):
        parts.append("fng")
    return Path(output_dir) / ("_".join(parts) + ".keras")


def tune(args):
    sequence_lengths = _split_values(args.sequence_lengths, int)
    prediction_horizons = _split_values(args.prediction_horizons, int)
    minimum_returns = _split_values(args.minimum_returns, float)
    learning_rates = _split_values(args.learning_rates, float)
    batch_sizes = _split_values(args.batch_sizes, int)

    combinations = list(
        itertools.product(
            sequence_lengths,
            prediction_horizons,
            minimum_returns,
            learning_rates,
            batch_sizes,
        )
    )
    if args.randomize:
        random.Random(args.seed).shuffle(combinations)
    if args.max_runs:
        combinations = combinations[: args.max_runs]

    pair = args.pair.strip().upper()
    prefix = args.model_prefix or f"{pair.lower()}_lstm_tune"
    rows = []

    print(f"Starting LSTM tuning for {pair} on {args.interval}")
    print(f"Planned runs: {len(combinations)}")
    print(f"Results CSV: {args.results_path}")

    for run_number, combo in enumerate(combinations, start=1):
        sequence_length, prediction_horizon, minimum_return, learning_rate, batch_size = combo
        params = {
            "pair": pair,
            "interval": args.interval,
            "sequence_length": sequence_length,
            "prediction_horizon": prediction_horizon,
            "minimum_return": minimum_return,
            "learning_rate": learning_rate,
            "batch_size": batch_size,
            "epochs": args.epochs,
            "fear_greed_csv": args.fear_greed_csv,
        }
        model_path = _model_path(
            args.output_dir,
            prefix,
            {**params, "interval": args.interval},
        )

        print("")
        print(
            f"Run {run_number}/{len(combinations)}: "
            f"seq={sequence_length}, horizon={prediction_horizon}, "
            f"min_return={minimum_return}, lr={learning_rate}, batch={batch_size}"
        )
        if args.dry_run:
            print(f"  Would save model to: {model_path}")
            continue

        try:
            _, metadata = train(
                pair=pair,
                interval=args.interval,
                model_path=model_path,
                sequence_length=sequence_length,
                prediction_horizon=prediction_horizon,
                minimum_return=minimum_return,
                epochs=args.epochs,
                batch_size=batch_size,
                learning_rate=learning_rate,
                database_type=args.database_type,
                database_url=args.database_url,
                fear_greed_csv=args.fear_greed_csv,
            )
            rows.append(_flatten_result(run_number, model_path, params, metadata))
        except Exception as exc:  # noqa: BLE001 - keep tuning running after one bad config.
            rows.append(
                {
                    "status": "failed",
                    "run": run_number,
                    "model_path": str(model_path),
                    "sequence_length": sequence_length,
                    "prediction_horizon": prediction_horizon,
                    "minimum_return": minimum_return,
                    "learning_rate": learning_rate,
                    "batch_size": batch_size,
                    "epochs": args.epochs,
                    "fear_greed": bool(args.fear_greed_csv),
                    "error": str(exc),
                }
            )
            print(f"  Run failed: {exc}")

        _write_results(args.results_path, rows)

    successful = [row for row in rows if row.get("status") == "ok"]
    successful.sort(key=lambda row: _score(row, args.sort_by), reverse=True)
    summary_path = Path(args.results_path).with_suffix(".summary.json")
    summary_path.write_text(json.dumps(successful[: args.top], indent=2), encoding="utf-8")

    print("")
    print(f"Finished. Successful runs: {len(successful)} / {len(rows)}")
    print(f"Results CSV: {args.results_path}")
    print(f"Top summary JSON: {summary_path}")
    print(f"Top {min(args.top, len(successful))} by {args.sort_by}:")
    for rank, row in enumerate(successful[: args.top], start=1):
        print(
            f"  {rank}. auc={row['test_auc']:.4f}, "
            f"neutral={row.get('neutral_balanced_success')}, "
            f"entry={row.get('entry_balanced_success')}, "
            f"seq={row['sequence_length']}, h={row['prediction_horizon']}, "
            f"min_return={row['minimum_return']}, lr={row['learning_rate']}, "
            f"model={row['model_path']}"
        )


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", default=config.PAIR_NAME)
    parser.add_argument("--interval", default=config.RESAMPLE_INTERVAL)
    parser.add_argument("--output-dir", default="ml/models/tuning")
    parser.add_argument("--results-path", default="logs/lstm_tuning_results.csv")
    parser.add_argument("--model-prefix")
    parser.add_argument("--sequence-lengths", default="48,60,96")
    parser.add_argument("--prediction-horizons", default="1,3,6")
    parser.add_argument("--minimum-returns", default="0.001,0.003,0.005")
    parser.add_argument("--learning-rates", default="0.001,0.0005")
    parser.add_argument("--batch-sizes", default="64")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--max-runs", type=int, default=12)
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--randomize", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--sort-by",
        default="test_auc",
        choices=(
            "test_auc",
            "test_accuracy",
            "neutral_balanced_success",
            "entry_balanced_success",
            "entry_total_coverage",
        ),
    )
    parser.add_argument(
        "--fear-greed-csv",
        default=getattr(config, "LSTM_FEAR_GREED_CSV_PATH", None),
        help="Optional CSV with daily Fear & Greed Index values",
    )
    parser.add_argument(
        "--database-type",
        choices=("postgresql", "sqlite"),
        help="Override the configured database type for this tuning run",
    )
    parser.add_argument(
        "--database-url",
        help="Override the configured database URL for this tuning run",
    )
    return parser.parse_args()


if __name__ == "__main__":
    tune(parse_args())
