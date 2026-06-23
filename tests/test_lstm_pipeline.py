import unittest
from types import SimpleNamespace

import numpy as np
import pandas as pd

from data.fear_greed_loader import FEAR_GREED_FEATURE_COLUMNS, add_fear_greed_features
from ml.feature_builder import DEFAULT_FEATURE_COLUMNS, build_feature_frame
from ml.predict_lstm import LSTMPredictor
from scripts.strategies.lstm_filter_strategy import LSTMFilterStrategy


def sample_ohlcv(rows=320):
    random = np.random.default_rng(42)
    index = pd.date_range("2024-01-01", periods=rows, freq="h")
    close = 40_000 * np.exp(np.cumsum(random.normal(0, 0.002, rows)))
    open_price = close * (1 + random.normal(0, 0.0005, rows))
    high = np.maximum(open_price, close) * (1 + random.uniform(0.0001, 0.004, rows))
    low = np.minimum(open_price, close) * (1 - random.uniform(0.0001, 0.004, rows))
    return pd.DataFrame(
        {
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": random.lognormal(8, 0.5, rows),
        },
        index=index,
    )


class ConstantModel:
    def __init__(self, probability):
        self.probability = probability

    def predict(self, values, batch_size=None, verbose=0):
        return np.full((len(values), 1), self.probability, dtype="float32")


class LSTMPipelineTests(unittest.TestCase):
    def test_features_are_finite_and_predictor_aligns_timestamps(self):
        frame = sample_ohlcv()
        features = build_feature_frame(frame)
        metadata = {
            "pair": "BTCUSDT",
            "interval": "1h",
            "sequence_length": 60,
            "feature_columns": DEFAULT_FEATURE_COLUMNS,
            "feature_mean": [0.0] * len(DEFAULT_FEATURE_COLUMNS),
            "feature_scale": [1.0] * len(DEFAULT_FEATURE_COLUMNS),
        }
        predictor = LSTMPredictor(
            "unused.keras",
            model=ConstantModel(0.75),
            metadata=metadata,
        )
        prediction = predictor.predict_frame(frame, batch_size=32)

        self.assertTrue(np.isfinite(features.to_numpy()).all())
        self.assertEqual(prediction.notna().sum(), len(features) - 59)
        self.assertTrue((prediction.dropna() == np.float32(0.75)).all())
        predictor.validate_context("BTCUSDT", "1h")

    def test_fear_greed_features_can_be_added_to_lstm_inputs(self):
        frame = sample_ohlcv()
        fear_greed = pd.DataFrame(
            {"value": [20, 35, 80, 55]},
            index=pd.to_datetime(
                ["2024-01-01", "2024-01-03", "2024-01-06", "2024-01-10"],
                utc=True,
            ),
        )
        enriched = add_fear_greed_features(frame, fear_greed)
        features = build_feature_frame(
            enriched,
            DEFAULT_FEATURE_COLUMNS + FEAR_GREED_FEATURE_COLUMNS,
        )

        self.assertTrue(set(FEAR_GREED_FEATURE_COLUMNS).issubset(enriched.columns))
        self.assertTrue(np.isfinite(features.to_numpy()).all())

    def test_filter_only_confirms_entries(self):
        frame = sample_ohlcv(5)
        frame["buy_signal"] = [True, True, False, False, False]
        frame["sell_signal"] = [False, False, True, True, False]
        frame["signal"] = [1, 1, -1, -1, 0]

        class BaseStrategy:
            @staticmethod
            def compute_signals(values, config):
                return values.copy()

        class Predictor:
            @staticmethod
            def predict_frame(values, batch_size=2048, out_of_sample_only=False):
                return pd.Series([0.7, 0.5, 0.3, 0.5, np.nan], index=values.index)

        strategy = LSTMFilterStrategy()
        strategy.base_strategy = BaseStrategy()
        strategy.predictor = Predictor()
        config = SimpleNamespace(
            LSTM_BUY_THRESHOLD=0.6,
            LSTM_SELL_THRESHOLD=0.4,
            LSTM_PREDICTION_BATCH_SIZE=32,
        )
        result = strategy.compute_signals(frame, config)

        self.assertEqual(result["buy_signal"].tolist(), [True, False, False, False, False])
        self.assertEqual(result["sell_signal"].tolist(), [False, False, True, False, False])
        self.assertEqual(result["signal"].tolist(), [1, 0, -1, 0, 0])


if __name__ == "__main__":
    unittest.main()
