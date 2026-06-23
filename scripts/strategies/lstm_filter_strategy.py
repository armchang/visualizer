"""Use a trained LSTM to approve EMA entries without controlling exits."""

from pathlib import Path

from ml.predict_lstm import LSTMPredictor
from scripts.strategies.ema_crossover import EMACrossover


class LSTMFilterStrategy:
    """Decorator strategy: EMA proposes trades and the LSTM filters entries."""

    plot_columns = ["lstm_probability_up"]

    def __init__(self):
        self.base_strategy = EMACrossover()
        self.predictor = None

    @staticmethod
    def _model_path(config):
        configured_path = getattr(config, "LSTM_MODEL_PATH", None)
        if configured_path:
            return Path(configured_path).expanduser()
        project_root = Path(__file__).resolve().parents[1]
        filename = f"{config.PAIR_NAME.lower()}_{config.RESAMPLE_INTERVAL}_lstm.keras"
        return project_root / "ml" / "models" / filename

    def _get_predictor(self, config):
        if self.predictor is None:
            self.predictor = LSTMPredictor(
                self._model_path(config),
                fear_greed_csv=getattr(config, "LSTM_FEAR_GREED_CSV_PATH", None),
            )
            self.predictor.validate_context(config.PAIR_NAME, config.RESAMPLE_INTERVAL)
        return self.predictor

    def compute_signals(self, df, config):
        result = self.base_strategy.compute_signals(df, config)
        result["raw_buy_signal"] = result["buy_signal"].astype(bool)
        result["raw_sell_signal"] = result["sell_signal"].astype(bool)

        probability_up = self._get_predictor(config).predict_frame(
            result,
            batch_size=getattr(config, "LSTM_PREDICTION_BATCH_SIZE", 2048),
            out_of_sample_only=getattr(config, "LSTM_OUT_OF_SAMPLE_ONLY", True),
        )
        result["lstm_probability_up"] = probability_up
        result["buy_signal"] = result["raw_buy_signal"] & (
            probability_up >= config.LSTM_BUY_THRESHOLD
        )
        result["sell_signal"] = result["raw_sell_signal"] & (
            probability_up <= config.LSTM_SELL_THRESHOLD
        )
        result["signal"] = 0
        result.loc[result["buy_signal"], "signal"] = 1
        result.loc[result["sell_signal"], "signal"] = -1
        return result

    def prepare(self, df, config):
        return self.base_strategy.prepare(df, config)

    def should_skip(self, i, row, state, config):
        return self.base_strategy.should_skip(i, row, state, config)

    def check_entry(self, i, row, state, df, config, enable_short=True, should_avoid=None):
        return self.base_strategy.check_entry(
            i,
            row,
            state,
            df,
            config,
            enable_short,
            should_avoid,
        )

    def check_exit(self, i, row, state, df, config):
        # The LSTM only filters entries. EMA exit signals remain untouched.
        exit_row = row.copy()
        exit_row["buy_signal"] = bool(row.get("raw_buy_signal", row["buy_signal"]))
        exit_row["sell_signal"] = bool(row.get("raw_sell_signal", row["sell_signal"]))
        return self.base_strategy.check_exit(i, exit_row, state, df, config)

    def check_stop(self, i, row, state, config):
        return self.base_strategy.check_stop(i, row, state, config)


Strategy = LSTMFilterStrategy
