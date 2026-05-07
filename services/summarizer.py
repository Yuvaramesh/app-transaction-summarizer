import os
import json
import calendar
from google import genai
from google.genai import types
from typing import Any
from dotenv import load_dotenv

load_dotenv()

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


class TransactionSummarizer:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set.")
        self.client = genai.Client(api_key=api_key)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def generate(
        self,
        user: dict,
        transactions: list[dict],
        rates: dict,
        month: int,
        year: int,
    ) -> dict:
        """Return a fully structured summary dict (metrics + AI narrative)."""
        metrics = self._compute_metrics(transactions, rates, month, year)
        narrative = self._call_gemini(user, transactions, metrics, rates, month, year)
        nudge = self._call_gemini_nudge(user, metrics, rates, month, year)

        return {
            "month": month,
            "year": year,
            "month_name": MONTH_NAMES[month],
            "user": user,
            "metrics": metrics,
            "narrative": narrative,
            "nudge": nudge,
            "transactions": transactions,
            "rates": rates,
        }

    # ------------------------------------------------------------------
    # Metrics computation (pure Python — no LLM needed)
    # ------------------------------------------------------------------

    def _compute_metrics(
        self, transactions: list[dict], rates: dict, month: int, year: int
    ) -> dict:
        total_gbp = sum(t["amount_gbp"] for t in transactions)
        total_fees = sum(t["fee_gbp"] for t in transactions)
        count = len(transactions)

        # Group by currency to compute received totals
        received_by_currency: dict[str, float] = {}
        for t in transactions:
            ccy = t["currency"]
            received_by_currency[ccy] = (
                received_by_currency.get(ccy, 0) + t["amount_received"]
            )

        # Recipient breakdown
        recipient_totals: dict[str, float] = {}
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

        # Simple month-over-month comparison (mock delta values)
        prev_month_gbp = total_gbp * 0.72  # simulated prior month

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
            "avg_rate_lkr": rates.get("LKR", {}).get("current", 425.03),
            "prev_rate_lkr": rates.get("LKR", {}).get("prev_month", 418.50),
            "rate_change_pct": round(
                (
                    rates.get("LKR", {}).get("current", 425.03)
                    - rates.get("LKR", {}).get("prev_month", 418.50)
                )
                / rates.get("LKR", {}).get("prev_month", 418.50)
                * 100,
                2,
            ),
            "prev_month_gbp": round(prev_month_gbp, 2),
            "mom_change_gbp": round(total_gbp - prev_month_gbp, 2),
            "fee_rate_pct": round(total_fees / total_gbp * 100, 2) if total_gbp else 0,
        }

    # ------------------------------------------------------------------
    # Gemini calls
    # ------------------------------------------------------------------

    def _call_gemini(
        self,
        user: dict,
        transactions: list[dict],
        metrics: dict,
        rates: dict,
        month: int,
        year: int,
    ) -> str:
        """Generate the main narrative paragraph."""
        month_name = MONTH_NAMES[month]

        prompt = f"""
You are the AI assistant for Ajeer, a remittance app used by migrant workers to send money home.
Write a warm, personal 3–4 sentence summary paragraph for the user's monthly transfer statement.

USER: {user['name']}
PERIOD: {month_name} {year}

TRANSACTION DATA:
- Total sent: £{metrics['total_gbp']}
- Number of transfers: {metrics['transfer_count']}
- Total fees paid: £{metrics['total_fees']} ({metrics['fee_rate_pct']}% of amount sent)
- Recipients: {json.dumps(metrics['recipient_totals'])}
- Currencies received: {json.dumps(metrics['received_by_currency'])}
- LKR rate this month: {metrics['avg_rate_lkr']} (vs {metrics['prev_rate_lkr']} last month, {metrics['rate_change_pct']:+.2f}%)

INSTRUCTIONS:
- Be conversational and human — not robotic or generic
- Highlight the rate improvement and what it means for the recipient in real terms
- Mention the fee efficiency if it was good
- Keep it under 80 words
- Do NOT use bullet points, markdown, or headers — plain prose only
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
    ) -> str:
        """Generate a short forward-looking nudge message."""
        next_month = month % 12 + 1
        next_month_name = MONTH_NAMES[next_month]

        prompt = f"""
You are the AI assistant for Ajeer remittance app.
Write ONE short, actionable nudge message (max 25 words) for the user based on their transfer patterns.

USER: {user['name']}
- They usually send around the 9th of each month
- Current LKR rate: {metrics['avg_rate_lkr']} (trending up for 4 days)
- Top recipient is in Sri Lanka
- Next month: {next_month_name}

Write only the nudge message. Plain text, no markdown, no quotes.
""".strip()

        response = self.client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
        )
        return response.text.strip()
