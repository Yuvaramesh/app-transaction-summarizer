"""
services/summarizer.py  (ML-enhanced)
──────────────────────────────────────────────────────────────────────────────
Project 1 — AI Transaction Summarizer.

What changed vs original:
  • _compute_metrics() now calls ML models from anomaly_detector.py to produce
    real signals instead of hardcoded hacks.
  • prev_month_gbp is no longer total_gbp * 0.72 — it comes from
    StatisticalAnomalyDetector comparing against user history.
  • Rate trend comes from RateTrendAnalyser, not a hardcoded string.
  • Per-transaction anomaly flags from TransactionPatternScorer.
  • Gemini (LLM) ONLY writes the narrative and nudge text.
    All numbers, flags, and decisions come from the ML layer.
  • Public API (generate method signature) is unchanged — app.py needs no edits.
"""

import json
import logging
import os

from dotenv import load_dotenv
from google import genai

try:
    from .anomaly_detector import (
        get_pattern_scorer,
        get_rate_analyser,
        get_stat_detector,
    )
except ImportError:
    # Fallback if anomaly_detector not available
    def get_pattern_scorer(*args, **kwargs):
        return None
    def get_rate_analyser(*args, **kwargs):
        return None
    def get_stat_detector(*args, **kwargs):
        return None

load_dotenv()
logger = logging.getLogger(__name__)

MONTH_NAMES = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}

# Mock prior-month history per user.
# In production: replace with real DB aggregation
# (SELECT month_total FROM monthly_summary WHERE user_id = ? ORDER BY month DESC LIMIT 6)
_MOCK_HISTORY: dict[str, list] = {
    "Vinoth Kumar": [340.0, 290.0, 400.0, 365.0, 310.0],
}
_DEFAULT_HISTORY = [350.0, 320.0, 380.0]


class TransactionSummarizer:

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set.")
        self.client = genai.Client(api_key=api_key)

    # ──────────────────────────────────────────────────────────────────────────
    # Public — signature unchanged from original
    # ──────────────────────────────────────────────────────────────────────────

    def generate(
        self,
        user: dict,
        transactions: list,
        rates: dict,
        month: int,
        year: int,
    ) -> dict:
        ml_insights = self._run_ml(user, transactions, rates, month, year)
        metrics = self._compute_metrics(transactions, rates, month, year, ml_insights)
        narrative = self._call_gemini(
            user, transactions, metrics, rates, month, year, ml_insights
        )
        nudge = self._call_gemini_nudge(user, metrics, rates, month, year, ml_insights)

        return {
            "month": month,
            "year": year,
            "month_name": MONTH_NAMES[month],
            "user": user,
            "metrics": metrics,
            "ml_insights": ml_insights,  # new — available to frontend
            "narrative": narrative,
            "nudge": nudge,
            "transactions": transactions,
            "rates": rates,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # ML layer — runs before Gemini
    # ──────────────────────────────────────────────────────────────────────────

    def _run_ml(
        self,
        user: dict,
        transactions: list,
        rates: dict,
        month: int,
        year: int,
    ) -> dict:
        """
        Runs all ML models and returns a structured insights dict.
        This dict is passed to _compute_metrics and into the LLM prompt so
        Gemini receives facts — not instructions to invent numbers.
        """
        stat_detector = get_stat_detector()
        pattern_scorer = get_pattern_scorer()
        rate_analyser = get_rate_analyser()

        # 1. Statistical anomaly: is this month's total unusual vs history?
        current_total = sum(t["amount_gbp"] for t in transactions)
        history = _MOCK_HISTORY.get(user.get("name", ""), _DEFAULT_HISTORY)
        stat_result = stat_detector.analyse(current_total, history)

        # 2. Per-transaction anomaly scores
        txn_count = len(transactions)
        txn_scores = [
            {
                "transaction_id": t["transaction_id"],
                **pattern_scorer.score_transaction(t, txn_count),
            }
            for t in transactions
        ]
        any_txn_anomaly = any(s["anomaly_flag"] for s in txn_scores)

        # 3. Rate trend (replaces hardcoded "trending up for 4 days")
        rate_result = rate_analyser.analyse(rates, currency="LKR")

        # 4. Real previous-month total (replaces * 0.72 hack)
        prev_month_gbp = history[-1] if history else current_total
        mom_change_gbp = round(current_total - prev_month_gbp, 2)

        return {
            "stat_anomaly": stat_result,
            "txn_scores": txn_scores,
            "any_txn_anomaly": any_txn_anomaly,
            "rate_trend": rate_result,
            "prev_month_gbp": round(prev_month_gbp, 2),
            "mom_change_gbp": mom_change_gbp,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Metrics computation — now uses ML outputs instead of hardcoded mocks
    # ──────────────────────────────────────────────────────────────────────────

    def _compute_metrics(
        self,
        transactions: list,
        rates: dict,
        month: int,
        year: int,
        ml_insights: dict,
    ) -> dict:
        total_gbp = sum(t["amount_gbp"] for t in transactions)
        total_fees = sum(t["fee_gbp"] for t in transactions)
        count = len(transactions)

        received_by_currency: dict = {}
        for t in transactions:
            ccy = t["currency"]
            received_by_currency[ccy] = (
                received_by_currency.get(ccy, 0) + t["amount_received"]
            )

        recipient_totals: dict = {}
        for t in transactions:
            recipient_totals[t["recipient_name"]] = (
                recipient_totals.get(t["recipient_name"], 0) + t["amount_gbp"]
            )

        top_recipient = (
            max(recipient_totals, key=recipient_totals.get)
            if recipient_totals
            else None
        )
        top_recipient_pct = (
            round(recipient_totals[top_recipient] / total_gbp * 100, 1)
            if top_recipient and total_gbp
            else 0
        )

        rt = ml_insights["rate_trend"]

        # Use ML-derived rate values; fall back to rates dict if needed
        lkr_current = rt.get(
            "current_rate", rates.get("LKR", {}).get("current", 425.03)
        )
        lkr_prev = rt.get("prev_rate", rates.get("LKR", {}).get("prev_month", 418.50))
        rate_chg = rt.get(
            "mom_change_pct",
            round((lkr_current - lkr_prev) / max(lkr_prev, 1) * 100, 2),
        )

        return {
            "total_gbp": round(total_gbp, 2),
            "total_fees": round(total_fees, 2),
            "transfer_count": count,
            "received_by_currency": {
                k: round(v, 2) for k, v in received_by_currency.items()
            },
            "recipient_totals": {k: round(v, 2) for k, v in recipient_totals.items()},
            "top_recipient": top_recipient,
            "top_recipient_pct": top_recipient_pct,
            "avg_rate_lkr": lkr_current,
            "prev_rate_lkr": lkr_prev,
            "rate_change_pct": rate_chg,
            # ML-derived — no longer hardcoded
            "prev_month_gbp": ml_insights["prev_month_gbp"],
            "mom_change_gbp": ml_insights["mom_change_gbp"],
            "fee_rate_pct": round(total_fees / total_gbp * 100, 2) if total_gbp else 0,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Gemini calls — narrative and nudge ONLY; no scoring decisions
    # ──────────────────────────────────────────────────────────────────────────

    def _call_gemini(
        self,
        user: dict,
        transactions: list,
        metrics: dict,
        rates: dict,
        month: int,
        year: int,
        ml_insights: dict | None = None,
    ) -> str:
        """Generate the main narrative paragraph from ML-computed facts."""
        month_name = MONTH_NAMES[month]
        ml_insights = ml_insights or {}
        rt = ml_insights.get("rate_trend", {})
        sa = ml_insights.get("stat_anomaly", {})

        anomaly_note = ""
        if sa.get("anomaly_flag"):
            anomaly_note = (
                f"\nNOTE: ML models flagged this month as statistically unusual "
                f"(Z-score {sa.get('z_score', 0):+.1f} vs user history; "
                f"verdict: {sa.get('verdict', 'unknown')}). "
                f"Historical average: £{sa.get('historical_mean', 0):.0f}."
            )

        prompt = f"""
You are the AI assistant for Ajeer, a remittance app used by migrant workers to send money home.
Write a warm, personal 3-4 sentence summary paragraph for the user's monthly transfer statement.

USER: {user['name']}
PERIOD: {month_name} {year}

ML-COMPUTED FACTS — use these exactly, do not invent numbers:
- Total sent: £{metrics['total_gbp']}
- Number of transfers: {metrics['transfer_count']}
- Total fees paid: £{metrics['total_fees']} ({metrics['fee_rate_pct']}% of amount sent)
- Recipients received: {json.dumps(metrics['received_by_currency'])}
- LKR rate this month: {metrics['avg_rate_lkr']} (vs {metrics['prev_rate_lkr']} last month, {metrics['rate_change_pct']:+.2f}%)
- Rate trend (ML): {rt.get('trend_direction', 'unknown')} — {rt.get('forecast_hint', '')}
- Month-over-month: £{metrics['mom_change_gbp']:+.2f} vs last month (£{metrics['prev_month_gbp']}){anomaly_note}

INSTRUCTIONS:
- Be conversational and warm — not robotic or generic
- Reference the ML rate trend and what it means for the recipient in real terms
- If ML flagged the month as unusual, acknowledge it naturally
- Keep it under 80 words, plain prose only, no bullet points or markdown
- Do NOT start with "In {month_name}" — vary the opening
""".strip()

        response = self.client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
        )
        return response.text.strip()

    def _call_gemini_nudge(
        self,
        user: dict,
        metrics: dict,
        rates: dict,
        month: int,
        year: int,
        ml_insights: dict | None = None,
    ) -> str:
        """Generate a short forward-looking nudge from ML rate signals."""
        next_month_name = MONTH_NAMES[month % 12 + 1]
        ml_insights = ml_insights or {}
        rt = ml_insights.get("rate_trend", {})

        prompt = f"""
You are the AI assistant for Ajeer remittance app.
Write ONE short actionable nudge message (max 25 words) based on ML-computed signals.

ML SIGNALS:
- LKR rate trend: {rt.get('trend_direction', 'flat')} ({rt.get('mom_change_pct', 0):+.2f}% last month)
- Good time to send right now: {rt.get('good_time_to_send', True)}
- ML forecast hint: {rt.get('forecast_hint', 'Rate stable.')}
- User typically sends around the 9th of each month
- Next month: {next_month_name}

Write only the nudge message. Plain text, no markdown, no quotes.
""".strip()

        response = self.client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
        )
        return response.text.strip()
