"""
services/risk_model.py
──────────────────────────────────────────────────────────────────────────────
Real ML risk engine for Project 2 — Recipient Risk Verification.

Replaces: Gemini making tier/score decisions in /api/assess
Now:      XGBoost scores 0-100, Isolation Forest flags outliers,
          Gemini ONLY writes the plain-text explanation of the ML verdict.

Feature vector (8 features — order must never change after first training):
  amount_gbp | amount_to_typical_ratio | days_since_added |
  flag_count_48h | past_transfer_count | monthly_spent_ratio |
  account_age_days | kyc_verified
"""

import logging
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:
    import xgboost as xgb

    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False
    logging.warning("xgboost not installed — using GradientBoostingClassifier fallback")

logger = logging.getLogger(__name__)

MODEL_DIR = Path(os.environ.get("MODEL_DIR", "models"))
MODEL_DIR.mkdir(exist_ok=True)
XGB_PATH = MODEL_DIR / "risk_xgb.joblib"
ISO_PATH = MODEL_DIR / "risk_iso.joblib"

FEATURE_COLS = [
    "amount_gbp",
    "amount_to_typical_ratio",
    "days_since_added",
    "flag_count_48h",
    "past_transfer_count",
    "monthly_spent_ratio",
    "account_age_days",
    "kyc_verified",
]

GREEN_MAX = 30
AMBER_MAX = 65


def score_to_tier(score: float) -> str:
    if score <= GREEN_MAX:
        return "green"
    if score <= AMBER_MAX:
        return "amber"
    return "red"


# ── synthetic cold-start training data ───────────────────────────────────────


def _make_synthetic_training_data(n: int = 2000) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    n_clean = int(n * 0.75)
    n_risky = n - n_clean

    clean = pd.DataFrame(
        {
            "amount_gbp": rng.uniform(50, 600, n_clean),
            "amount_to_typical_ratio": rng.uniform(0.5, 1.8, n_clean),
            "days_since_added": rng.integers(30, 730, n_clean).astype(float),
            "flag_count_48h": rng.choice([0, 0, 0, 1], n_clean).astype(float),
            "past_transfer_count": rng.integers(2, 30, n_clean).astype(float),
            "monthly_spent_ratio": rng.uniform(0.1, 0.7, n_clean),
            "account_age_days": rng.integers(90, 1500, n_clean).astype(float),
            "kyc_verified": rng.choice([1, 1, 1, 0], n_clean).astype(float),
            "label": 0,
        }
    )
    risky = pd.DataFrame(
        {
            "amount_gbp": rng.uniform(300, 2000, n_risky),
            "amount_to_typical_ratio": rng.uniform(2.0, 8.0, n_risky),
            "days_since_added": rng.integers(0, 14, n_risky).astype(float),
            "flag_count_48h": rng.integers(1, 6, n_risky).astype(float),
            "past_transfer_count": rng.integers(0, 4, n_risky).astype(float),
            "monthly_spent_ratio": rng.uniform(0.7, 1.2, n_risky),
            "account_age_days": rng.integers(1, 60, n_risky).astype(float),
            "kyc_verified": rng.choice([0, 0, 1], n_risky).astype(float),
            "label": 1,
        }
    )
    return pd.concat([clean, risky], ignore_index=True).sample(frac=1, random_state=42)


# ── XGBoost risk scorer ───────────────────────────────────────────────────────


class XGBoostRiskScorer:
    def __init__(self):
        self.model = None
        self._load_or_train()

    def _build(self):
        if XGB_AVAILABLE:
            return xgb.XGBClassifier(
                n_estimators=200,
                max_depth=4,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                eval_metric="logloss",
                random_state=42,
            )
        return GradientBoostingClassifier(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            random_state=42,
        )

    def _load_or_train(self):
        if XGB_PATH.exists():
            self.model = joblib.load(XGB_PATH)
            logger.info("XGBoost model loaded from %s", XGB_PATH)
        else:
            logger.info("No saved XGBoost model — training on synthetic data…")
            self.train(_make_synthetic_training_data())

    def train(self, df: pd.DataFrame):
        """Pass real historical transfers with a 'label' col (0=clean,1=risky)."""
        X, y = df[FEATURE_COLS].values, df["label"].values
        self.model = self._build()
        self.model.fit(X, y)
        joblib.dump(self.model, XGB_PATH)
        logger.info("XGBoost trained and saved (%d rows)", len(df))

    def predict(self, features: dict) -> float:
        """Returns float 0–100 risk score."""
        row = np.array([[features[f] for f in FEATURE_COLS]], dtype=float)
        return round(float(self.model.predict_proba(row)[0][1]) * 100, 1)


# ── Isolation Forest outlier detector ────────────────────────────────────────


class IsolationForestDetector:
    def __init__(self):
        self.pipeline = None
        self._load_or_train()

    def _load_or_train(self):
        if ISO_PATH.exists():
            self.pipeline = joblib.load(ISO_PATH)
            logger.info("Isolation Forest loaded from %s", ISO_PATH)
        else:
            logger.info("No saved Isolation Forest — training on synthetic data…")
            self.train(_make_synthetic_training_data())

    def train(self, df: pd.DataFrame):
        X = df[FEATURE_COLS].values
        self.pipeline = Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "iso",
                    IsolationForest(
                        n_estimators=200,
                        contamination=0.12,
                        random_state=42,
                    ),
                ),
            ]
        )
        self.pipeline.fit(X)
        joblib.dump(self.pipeline, ISO_PATH)
        logger.info("Isolation Forest trained and saved (%d rows)", len(df))

    def is_outlier(self, features: dict) -> bool:
        row = np.array([[features[f] for f in FEATURE_COLS]], dtype=float)
        return bool(self.pipeline.predict(row)[0] == -1)

    def anomaly_score(self, features: dict) -> float:
        """Returns 0.0–1.0; higher = more anomalous."""
        row = np.array([[features[f] for f in FEATURE_COLS]], dtype=float)
        raw = self.pipeline.decision_function(row)[0]
        return round(float(np.clip(0.5 - raw, 0.0, 1.0)), 3)


# ── Unified risk engine ───────────────────────────────────────────────────────


class RiskEngine:
    """
    Final score = 0.70 × xgb_score + 0.30 × (iso_anomaly × 100)
    XGBoost = primary decision; Isolation Forest = unsupervised lift.
    Gemini called AFTER this — writes explanation text only.
    """

    def __init__(self):
        self.xgb = XGBoostRiskScorer()
        self.iso = IsolationForestDetector()

    def build_features(
        self,
        amount: float,
        sender: dict,
        recipient: dict,
        flag_count: int,
        past_transfer_count: int,
        monthly_sent: float,
    ) -> dict:
        typical = float(sender.get("typical_transfer_amount", 1) or 1)
        monthly_limit = float(sender.get("monthly_limit_gbp", 2000) or 2000)
        age_label = sender.get("account_age_label", "")
        try:
            if "year" in age_label:
                account_age_days = float(age_label.split()[0]) * 365
            elif "month" in age_label:
                account_age_days = float(age_label.split()[0]) * 30
            else:
                account_age_days = float(age_label.split()[0])
        except (ValueError, IndexError):
            account_age_days = 30.0

        return {
            "amount_gbp": float(amount),
            "amount_to_typical_ratio": float(amount) / typical,
            "days_since_added": float(recipient.get("days_since_added", 0)),
            "flag_count_48h": float(flag_count),
            "past_transfer_count": float(past_transfer_count),
            "monthly_spent_ratio": float(monthly_sent) / monthly_limit,
            "account_age_days": account_age_days,
            "kyc_verified": 1.0 if sender.get("kyc_status") == "verified" else 0.0,
        }

    def assess(
        self,
        amount: float,
        sender: dict,
        recipient: dict,
        flag_count: int,
        past_transfer_count: int,
        monthly_sent: float,
    ) -> dict:
        features = self.build_features(
            amount,
            sender,
            recipient,
            flag_count,
            past_transfer_count,
            monthly_sent,
        )
        xgb_score = self.xgb.predict(features)
        iso_score = self.iso.anomaly_score(features)
        is_outlier = self.iso.is_outlier(features)
        final = min(round(0.70 * xgb_score + 0.30 * (iso_score * 100), 1), 100.0)

        return {
            "risk_score": int(round(final)),
            "tier": score_to_tier(final),
            "xgb_score": round(xgb_score, 1),
            "iso_score": round(iso_score * 100, 1),
            "is_outlier": is_outlier,
            "features": features,
        }

    def build_signals(
        self,
        assessment: dict,
        sender: dict,
        recipient: dict,
        amount: float,
        monthly_sent: float,
    ) -> list:
        """
        Rule-based signals derived from ML scores + raw values.
        Gemini does NOT generate these — they are deterministic.
        """
        f = assessment["features"]
        signals = []

        # positive
        if f["past_transfer_count"] >= 3:
            signals.append(
                {
                    "status": "ok",
                    "text": f"{int(f['past_transfer_count'])} previous successful transfers to this recipient",
                }
            )
        if f["days_since_added"] >= 30:
            signals.append(
                {
                    "status": "ok",
                    "text": f"Recipient added {int(f['days_since_added'])} days ago — established relationship",
                }
            )
        if f["kyc_verified"] == 1.0:
            signals.append({"status": "ok", "text": "Sender KYC fully verified"})
        if f["account_age_days"] >= 365:
            signals.append(
                {
                    "status": "ok",
                    "text": f"Sender account {int(f['account_age_days'] // 365)} year(s) old — established",
                }
            )
        if f["monthly_spent_ratio"] < 0.5:
            remaining = sender.get("monthly_limit_gbp", 2000) - monthly_sent
            signals.append(
                {
                    "status": "ok",
                    "text": f"£{remaining:.0f} remaining in monthly limit — well within bounds",
                }
            )

        # warnings
        if f["amount_to_typical_ratio"] > 2.0:
            signals.append(
                {
                    "status": "warn",
                    "text": (
                        f"Transfer £{amount:.0f} is {f['amount_to_typical_ratio']:.1f}×"
                        f" sender's typical £{sender.get('typical_transfer_amount', 0)}"
                    ),
                }
            )
        if 0 < f["days_since_added"] < 7:
            signals.append(
                {
                    "status": "warn",
                    "text": f"Recipient added only {int(f['days_since_added'])} day(s) ago — new relationship",
                }
            )
        if f["monthly_spent_ratio"] > 0.8:
            signals.append(
                {
                    "status": "warn",
                    "text": (
                        f"Monthly spend at {f['monthly_spent_ratio']*100:.0f}%"
                        f" of £{sender.get('monthly_limit_gbp', 2000)} limit"
                    ),
                }
            )
        if assessment["is_outlier"] and assessment["iso_score"] > 50:
            signals.append(
                {
                    "status": "warn",
                    "text": f"ML anomaly detector: unusual pattern (score {assessment['iso_score']:.0f}/100)",
                }
            )

        # flags
        if f["flag_count_48h"] > 1:
            signals.append(
                {
                    "status": "flag",
                    "text": f"Recipient flagged {int(f['flag_count_48h'])} times by other senders in past 48 h",
                }
            )
        if f["kyc_verified"] == 0.0:
            signals.append(
                {
                    "status": "flag",
                    "text": "Sender KYC pending — identity not fully verified",
                }
            )
        if f["account_age_days"] < 30:
            signals.append(
                {
                    "status": "flag",
                    "text": f"Sender account only {int(f['account_age_days'])} days old — new account risk",
                }
            )
        if f["monthly_spent_ratio"] > 1.0:
            signals.append(
                {
                    "status": "flag",
                    "text": f"Transfer would exceed monthly limit of £{sender.get('monthly_limit_gbp', 2000)}",
                }
            )

        signals.sort(key=lambda s: {"flag": 0, "warn": 1, "ok": 2}[s["status"]])
        return signals[:5]


_engine: RiskEngine | None = None


def get_risk_engine() -> RiskEngine:
    global _engine
    if _engine is None:
        _engine = RiskEngine()
    return _engine
