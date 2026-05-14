"""
services/anomaly_detector.py
──────────────────────────────────────────────────────────────────────────────
ML anomaly detection for Project 1 — Transaction Summarizer.

Replaces two hardcoded hacks in the original summarizer.py:
  1. prev_month_gbp = total_gbp * 0.72   →  StatisticalAnomalyDetector
  2. "trending up for 4 days" (hardcoded) →  RateTrendAnalyser

Two classes:
  StatisticalAnomalyDetector  Z-score + IQR on user's own history.
                               Zero training needed — works immediately.
  RateTrendAnalyser           Computes rate momentum from historical rates dict.
                               Tells the LLM whether it's a good time to send.
  TransactionPatternScorer    Isolation Forest on per-transaction features.
                               Flags individual transactions as unusual.
"""

import logging
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

MODEL_DIR = Path(os.environ.get("MODEL_DIR", "models"))
MODEL_DIR.mkdir(exist_ok=True)
PATTERN_MODEL_PATH = MODEL_DIR / "txn_pattern_iso.joblib"

TXN_FEATURE_COLS = [
    "amount_gbp",
    "fee_rate_pct",
    "exchange_rate",
    "day_of_month",
    "transfer_count_month",
]


# ── synthetic training data ───────────────────────────────────────────────────


def _make_txn_synthetic_data(n: int = 1500) -> pd.DataFrame:
    rng = np.random.default_rng(99)
    n_normal = int(n * 0.85)
    n_anomaly = n - n_normal

    normal = pd.DataFrame(
        {
            "amount_gbp": rng.uniform(100, 500, n_normal),
            "fee_rate_pct": rng.uniform(0.5, 1.5, n_normal),
            "exchange_rate": rng.uniform(400, 435, n_normal),
            "day_of_month": rng.integers(1, 28, n_normal).astype(float),
            "transfer_count_month": rng.integers(1, 4, n_normal).astype(float),
        }
    )
    anomaly = pd.DataFrame(
        {
            "amount_gbp": rng.uniform(800, 3000, n_anomaly),
            "fee_rate_pct": rng.uniform(3.0, 8.0, n_anomaly),
            "exchange_rate": rng.uniform(300, 380, n_anomaly),
            "day_of_month": rng.integers(1, 28, n_anomaly).astype(float),
            "transfer_count_month": rng.integers(5, 12, n_anomaly).astype(float),
        }
    )
    return pd.concat([normal, anomaly], ignore_index=True).sample(
        frac=1, random_state=99
    )


# ── Statistical anomaly detector (no training needed) ────────────────────────


class StatisticalAnomalyDetector:
    """
    Uses Z-score + IQR to detect whether a month's total spend is unusual
    compared to the user's own prior history.
    Replaces the hardcoded 0.72 multiplier in the original summarizer.py.
    """

    def analyse(self, current_total: float, history: list) -> dict:
        """
        current_total : this month's total GBP
        history       : list of prior monthly GBP totals (oldest first)

        Returns dict with anomaly_flag, z_score, pct_change_mom, verdict,
        historical_mean, historical_std.
        """
        if len(history) < 2:
            prev = history[0] if history else current_total
            pct = round((current_total - prev) / max(prev, 1) * 100, 2)
            return {
                "anomaly_flag": False,
                "z_score": 0.0,
                "pct_change_mom": pct,
                "verdict": "insufficient_data",
                "historical_mean": float(prev),
                "historical_std": 0.0,
            }

        arr = np.array(history, dtype=float)
        mean = float(arr.mean())
        std = float(arr.std()) or 1.0
        z = (current_total - mean) / std

        pct_change = round((current_total - history[-1]) / max(history[-1], 1) * 100, 2)

        q1, q3 = np.percentile(arr, [25, 75])
        iqr = q3 - q1
        is_iqr = current_total < (q1 - 1.5 * iqr) or current_total > (q3 + 1.5 * iqr)

        anomaly_flag = abs(z) > 2.0 or is_iqr

        if current_total > mean + std:
            verdict = "high"
        elif current_total < mean - std:
            verdict = "low"
        else:
            verdict = "normal"

        return {
            "anomaly_flag": anomaly_flag,
            "z_score": round(float(z), 2),
            "pct_change_mom": pct_change,
            "verdict": verdict,
            "historical_mean": round(mean, 2),
            "historical_std": round(std, 2),
        }


# ── Transaction pattern scorer ────────────────────────────────────────────────


class TransactionPatternScorer:
    """
    Isolation Forest on per-transaction features.
    Flags individual transactions with unusual amount/fee/rate combinations.
    """

    def __init__(self):
        self.pipeline = None
        self._load_or_train()

    def _load_or_train(self):
        if PATTERN_MODEL_PATH.exists():
            self.pipeline = joblib.load(PATTERN_MODEL_PATH)
            logger.info("TransactionPatternScorer loaded from %s", PATTERN_MODEL_PATH)
        else:
            logger.info("Training TransactionPatternScorer on synthetic data…")
            self.train(_make_txn_synthetic_data())

    def train(self, df: pd.DataFrame):
        X = df[TXN_FEATURE_COLS].values
        self.pipeline = Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "iso",
                    IsolationForest(
                        n_estimators=150, contamination=0.10, random_state=99
                    ),
                ),
            ]
        )
        self.pipeline.fit(X)
        joblib.dump(self.pipeline, PATTERN_MODEL_PATH)
        logger.info("TransactionPatternScorer trained (%d rows)", len(df))

    def score_transaction(self, txn: dict, transfer_count_month: int) -> dict:
        """
        Score a single transaction dict from mock_data / DB.
        Returns: anomaly_flag (bool), anomaly_score (float 0-1).
        """
        try:
            amount = float(txn.get("amount_gbp", 0))
            fee = float(txn.get("fee_gbp", 0))
            fee_rate = (fee / amount * 100) if amount else 1.0
            row = np.array(
                [
                    [
                        amount,
                        fee_rate,
                        float(txn.get("exchange_rate", 420)),
                        float(_extract_day(txn.get("date", ""))),
                        float(transfer_count_month),
                    ]
                ]
            )
            pred = self.pipeline.predict(row)[0]
            raw = self.pipeline.decision_function(row)[0]
            score = float(np.clip(0.5 - raw, 0.0, 1.0))
            return {"anomaly_flag": bool(pred == -1), "anomaly_score": round(score, 3)}
        except Exception:
            return {"anomaly_flag": False, "anomaly_score": 0.0}


def _extract_day(date_str: str) -> int:
    """Extract day integer from strings like 'Apr 9, 2026' or 'Mar 15, 2026'."""
    try:
        parts = date_str.replace(",", "").split()
        return int(parts[1]) if len(parts) >= 2 else 9
    except (IndexError, ValueError):
        return 9


# ── Rate trend analyser ───────────────────────────────────────────────────────


class RateTrendAnalyser:
    """
    Computes exchange rate momentum from the rates dict.
    Replaces the hardcoded 'trending up for 4 days' string in summarizer.py.
    Produces a machine-derived verdict that feeds the LLM prompt as a fact.
    """

    def analyse(self, rates: dict, currency: str = "LKR") -> dict:
        """
        rates    : dict from get_mock_rates() — keys: current, prev_month, two_months_ago
        currency : which currency to analyse (default LKR)

        Returns trend_direction, momentum_pct, mom_change_pct,
                good_time_to_send, forecast_hint, current_rate, prev_rate.
        """
        ccy = rates.get(currency, {})
        current = float(ccy.get("current", 0))
        prev = float(ccy.get("prev_month", 0))
        two_ago = float(ccy.get("two_months_ago", 0))

        if prev == 0:
            return {
                "trend_direction": "flat",
                "momentum_pct": 0.0,
                "mom_change_pct": 0.0,
                "good_time_to_send": False,
                "forecast_hint": "Insufficient rate history.",
                "current_rate": current,
                "prev_rate": prev,
            }

        mom_pct = round((current - prev) / prev * 100, 2)
        two_pct = round((current - two_ago) / two_ago * 100, 2) if two_ago else mom_pct

        if two_pct > 0.5:
            direction = "up"
            good = True
            hint = (
                f"{currency} rate has risen {two_pct:+.2f}% over 2 months "
                f"— favourable time to send."
            )
        elif two_pct < -0.5:
            direction = "down"
            good = False
            hint = (
                f"{currency} rate has fallen {two_pct:.2f}% over 2 months "
                f"— consider waiting for recovery."
            )
        else:
            direction = "flat"
            good = True
            hint = f"{currency} rate is stable — no strong timing signal."

        return {
            "trend_direction": direction,
            "momentum_pct": two_pct,
            "mom_change_pct": mom_pct,
            "good_time_to_send": good,
            "forecast_hint": hint,
            "current_rate": current,
            "prev_rate": prev,
        }


# ── singletons ────────────────────────────────────────────────────────────────

_stat: StatisticalAnomalyDetector | None = None
_pattern: TransactionPatternScorer | None = None
_rate: RateTrendAnalyser | None = None


def get_stat_detector() -> StatisticalAnomalyDetector:
    global _stat
    if _stat is None:
        _stat = StatisticalAnomalyDetector()
    return _stat


def get_pattern_scorer() -> TransactionPatternScorer:
    global _pattern
    if _pattern is None:
        _pattern = TransactionPatternScorer()
    return _pattern


def get_rate_analyser() -> RateTrendAnalyser:
    global _rate
    if _rate is None:
        _rate = RateTrendAnalyser()
    return _rate
