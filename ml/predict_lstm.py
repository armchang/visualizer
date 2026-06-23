"""Load a trained LSTM and produce timestamp-aligned direction probabilities."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from data.fear_greed_loader import FEAR_GREED_FEATURE_COLUMNS, add_fear_greed_features
from ml.feature_builder import build_feature_frame, standardize


class LSTMPredictor:
    """Reusable model and scaler for batch prediction during a backtest."""

    def __init__(self, model_path, model=None, metadata=None, fear_greed_csv=None):
        self.model_path = Path(model_path).expanduser()
        if metadata is None:
            metadata_path = self.model_path.with_suffix(".metadata.json")
            if not metadata_path.exists():
                raise FileNotFoundError(f"LSTM metadata not found: {metadata_path}")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.metadata = metadata

        if model is None:
            if not self.model_path.exists():
                raise FileNotFoundError(
                    f"LSTM model not found: {self.model_path}. Train it with ml/train_lstm.py first."
                )
            try:
                from tensorflow import keras
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "TensorFlow is required for LSTM prediction. Install requirements-ml.txt."
                ) from exc
            model = keras.models.load_model(self.model_path, compile=False)
        self.model = model

        self.feature_columns = self.metadata["feature_columns"]
        self.fear_greed_csv = fear_greed_csv or self.metadata.get("fear_greed_csv")
        self.requires_fear_greed = any(
            column in self.feature_columns for column in FEAR_GREED_FEATURE_COLUMNS
        )
        self.sequence_length = int(self.metadata["sequence_length"])
        self.mean = np.asarray(self.metadata["feature_mean"], dtype="float32")
        self.scale = np.asarray(self.metadata["feature_scale"], dtype="float32")
        if len(self.mean) != len(self.feature_columns) or len(self.scale) != len(
            self.feature_columns
        ):
            raise ValueError("LSTM metadata feature/scaler lengths do not match")
        if self.sequence_length < 2:
            raise ValueError("LSTM metadata sequence_length must be at least 2")

    def validate_context(self, pair, interval):
        trained_pair = str(self.metadata.get("pair", "")).upper()
        trained_interval = str(self.metadata.get("interval", ""))
        if trained_pair and trained_pair != pair.upper():
            raise ValueError(f"Model was trained for {trained_pair}, not {pair.upper()}")
        if trained_interval and trained_interval != interval:
            raise ValueError(f"Model was trained for {trained_interval}, not {interval}")

    def predict_frame(self, frame, batch_size=2048, out_of_sample_only=False):
        """Return probability of an upward move for every predictable candle."""
        if self.requires_fear_greed:
            if not self.fear_greed_csv:
                raise ValueError("This LSTM model requires Fear & Greed data, but no CSV path was provided")
            frame = add_fear_greed_features(frame, self.fear_greed_csv)
        features = build_feature_frame(frame, self.feature_columns)
        probabilities = pd.Series(np.nan, index=frame.index, name="lstm_probability_up")
        if len(features) < self.sequence_length:
            return probabilities

        scaled = standardize(features.to_numpy(), self.mean, self.scale)
        endpoints = np.arange(self.sequence_length - 1, len(features))
        for start in range(0, len(endpoints), batch_size):
            batch_endpoints = endpoints[start : start + batch_size]
            sequences = np.stack(
                [scaled[end - self.sequence_length + 1 : end + 1] for end in batch_endpoints]
            )
            batch_predictions = np.asarray(
                self.model.predict(sequences, batch_size=batch_size, verbose=0)
            ).reshape(-1)
            probabilities.loc[features.index[batch_endpoints]] = batch_predictions

        if out_of_sample_only:
            test_start = self.metadata.get("test_start")
            if not test_start:
                raise ValueError("LSTM metadata has no test_start for out-of-sample filtering")
            timestamp_index = pd.to_datetime(probabilities.index, utc=True)
            probabilities.loc[timestamp_index < pd.to_datetime(test_start, utc=True)] = np.nan
        return probabilities


def predict(model_path, frame, pair=None, interval=None, fear_greed_csv=None):
    """Convenience API for one-off prediction."""
    predictor = LSTMPredictor(model_path, fear_greed_csv=fear_greed_csv)
    if pair and interval:
        predictor.validate_context(pair, interval)
    return predictor.predict_frame(frame)
