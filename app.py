"""
app.py — Ajeer Unified Dashboard  (ML-enhanced)
──────────────────────────────────────────────────────────────────────────────
Changes vs original GitHub version:

Project 1 — Summarizer
  • summarizer.py now runs ML models (StatisticalAnomalyDetector,
    TransactionPatternScorer, RateTrendAnalyser) before calling Gemini.
  • /api/summary response now includes ml_insights alongside metrics.

Project 2 — Risk Verification
  • /api/assess no longer sends the full prompt to Gemini and trusts it to
    decide tier/score/signals.
  • Instead: RiskEngine (XGBoost + Isolation Forest) scores the transfer,
    builds rule-based signals, then Gemini only writes a 1-2 sentence
    plain-text explanation of the ML verdict.
  • All other routes, MongoDB logic, and auth are unchanged.
"""

import io
import json
import os
import re
from datetime import datetime, timedelta, timezone

import certifi
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_file
from google import genai
from google.genai import types
from pymongo import MongoClient

load_dotenv()

app = Flask(__name__)

# ── Gemini ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# ── MongoDB ───────────────────────────────────────────────────────────────────
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
mongo_client = MongoClient(
    MONGO_URI,
    tlsCAFile=certifi.where(),
    serverSelectionTimeoutMS=30000,
)
_db_name = MONGO_URI.split("/")[-1].split("?")[0] or "ajeer"
db = mongo_client[_db_name]
senders_col = db["senders"]
recipients_col = db["recipients"]
transfers_col = db["transfers"]
flags_col = db["recipient_flags"]

# ── Services ──────────────────────────────────────────────────────────────────
from data.mock_data import get_mock_rates, get_mock_transactions, get_mock_user
from services.pdf_generator import PDFGenerator
from services.risk_model import get_risk_engine  # NEW — ML risk engine
from services.summarizer import TransactionSummarizer

summarizer = TransactionSummarizer()
pdf_gen = PDFGenerator()


# ═════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ═════════════════════════════════════════════════════════════════════════════


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


# ═════════════════════════════════════════════════════════════════════════════
# PROJECT 1 — AI TRANSACTION SUMMARIZER
# ═════════════════════════════════════════════════════════════════════════════


@app.route("/summarizer")
def summarizer_page():
    return render_template("summarizer.html")


@app.route("/api/summary", methods=["POST"])
def generate_summary():
    body = request.get_json(force=True)
    month = int(body.get("month", 4))
    year = int(body.get("year", 2026))

    user = get_mock_user()
    transactions = get_mock_transactions(month, year)
    rates = get_mock_rates()

    if not transactions:
        return jsonify({"error": "No transactions found for the selected period."}), 404

    # summarizer.generate now runs ML models before calling Gemini
    summary = summarizer.generate(user, transactions, rates, month, year)
    return jsonify(summary)


@app.route("/api/export-pdf", methods=["POST"])
def export_pdf():
    body = request.get_json(force=True)
    month = int(body.get("month", 4))
    year = int(body.get("year", 2026))

    user = get_mock_user()
    transactions = get_mock_transactions(month, year)
    rates = get_mock_rates()

    summary = summarizer.generate(user, transactions, rates, month, year)
    pdf_bytes = pdf_gen.generate(user, transactions, summary, month, year)

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"Ajeer_Statement_{year}_{month:02d}.pdf",
    )


@app.route("/api/transactions", methods=["GET"])
def get_transactions():
    month = int(request.args.get("month", 4))
    year = int(request.args.get("year", 2026))
    return jsonify(get_mock_transactions(month, year))


# ═════════════════════════════════════════════════════════════════════════════
# PROJECT 2 — RECIPIENT RISK VERIFICATION  (ML-powered)
# ═════════════════════════════════════════════════════════════════════════════

# Gemini is now only asked to explain the ML verdict in plain English.
_EXPLAIN_SYSTEM_PROMPT = """You are a compliance assistant for Ajeer, an international remittance platform.
You will receive a completed ML risk assessment and must write a brief, clear explanation for the compliance officer or customer.

Rules:
- Write exactly 1-2 sentences.
- Reference the tier and one or two of the most important signals by name.
- Do NOT change the tier, risk score, or signals — those are decided by ML models, not you.
- Plain text only, no markdown, no JSON.
"""


@app.route("/verify")
def verify_page():
    return render_template("verify.html")


@app.route("/api/senders", methods=["GET"])
def list_senders():
    docs = list(
        senders_col.find(
            {},
            {
                "_id": 1,
                "full_name": 1,
                "typical_transfer_amount": 1,
                "monthly_limit_gbp": 1,
                "account_age_label": 1,
                "total_transfers": 1,
                "kyc_status": 1,
            },
        )
    )
    return jsonify(docs)


@app.route("/api/recipients", methods=["GET"])
def list_recipients():
    sender_id = request.args.get("sender_id")
    query = {"added_by_sender": sender_id} if sender_id else {}
    docs = list(
        recipients_col.find(
            query,
            {
                "_id": 1,
                "display_name": 1,
                "bank": 1,
                "country": 1,
                "destination_currency": 1,
                "account_masked": 1,
                "days_since_added": 1,
            },
        )
    )
    return jsonify(docs)


@app.route("/api/assess", methods=["POST"])
def assess():
    if not GEMINI_API_KEY:
        return jsonify({"error": "GEMINI_API_KEY not configured"}), 500

    body = request.get_json()
    if not body:
        return jsonify({"error": "No JSON body"}), 400

    sender_id = body.get("sender_id")
    recipient_id = body.get("recipient_id")
    amount = float(body.get("amount", 0))
    converted_amount = body.get("converted_amount", "")

    if not sender_id or not recipient_id:
        return jsonify({"error": "sender_id and recipient_id are required"}), 400

    # ── fetch from MongoDB (unchanged) ────────────────────────────────────────
    sender = senders_col.find_one({"_id": sender_id})
    recipient = recipients_col.find_one({"_id": recipient_id})

    if not sender:
        return jsonify({"error": f"Sender '{sender_id}' not found"}), 404
    if not recipient:
        return jsonify({"error": f"Recipient '{recipient_id}' not found"}), 404

    transfer_history = list(
        transfers_col.find(
            {"sender_id": sender_id, "recipient_id": recipient_id},
            {
                "_id": 0,
                "amount_gbp": 1,
                "destination_currency": 1,
                "converted_amount": 1,
                "status": 1,
                "created_at": 1,
            },
        )
        .sort("created_at", -1)
        .limit(10)
    )

    cutoff_48h = datetime.now(timezone.utc) - timedelta(hours=48)
    flag_count = flags_col.count_documents(
        {"recipient_id": recipient_id, "created_at": {"$gte": cutoff_48h}}
    )

    cutoff_30d = datetime.now(timezone.utc) - timedelta(days=30)
    pipeline = [
        {
            "$match": {
                "sender_id": sender_id,
                "created_at": {"$gte": cutoff_30d},
                "status": "completed",
            }
        },
        {"$group": {"_id": None, "total": {"$sum": "$amount_gbp"}}},
    ]
    result = list(transfers_col.aggregate(pipeline))
    monthly_sent = result[0]["total"] if result else 0.0

    # ── ML risk assessment — replaces full LLM prompt ─────────────────────────
    engine = get_risk_engine()
    assessment = engine.assess(
        amount=amount,
        sender=sender,
        recipient=recipient,
        flag_count=flag_count,
        past_transfer_count=len(transfer_history),
        monthly_sent=monthly_sent,
    )
    signals = engine.build_signals(
        assessment=assessment,
        sender=sender,
        recipient=recipient,
        amount=amount,
        monthly_sent=monthly_sent,
    )

    tier = assessment["tier"]
    risk_score = assessment["risk_score"]

    # ── tier-to-copy mapping (deterministic, no LLM) ─────────────────────────
    TIER_COPY = {
        "green": {
            "headline": "Recipient verified",
            "action_label": "Confirm transfer",
            "secondary_label": None,
        },
        "amber": {
            "headline": "Please review before sending",
            "action_label": "Proceed with caution",
            "secondary_label": "Cancel transfer",
        },
        "red": {
            "headline": "Transfer held for review",
            "action_label": "Escalate to compliance",
            "secondary_label": "Cancel transfer",
        },
    }
    copy = TIER_COPY[tier]

    # ── Gemini writes ONE explanation sentence (no decisions) ─────────────────
    try:
        signal_texts = "; ".join(s["text"] for s in signals[:3])
        explain_prompt = (
            f"ML risk assessment result:\n"
            f"  Tier: {tier}\n"
            f"  Risk score: {risk_score}/100 "
            f"(XGBoost: {assessment['xgb_score']}, IsolationForest: {assessment['iso_score']})\n"
            f"  Top signals: {signal_texts}\n\n"
            f"Write 1-2 sentences explaining this result to a compliance officer."
        )
        explain_response = gemini_client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=explain_prompt,
            config=types.GenerateContentConfig(
                system_instruction=_EXPLAIN_SYSTEM_PROMPT,
                temperature=0.1,
            ),
        )
        summary_text = explain_response.text.strip()
    except Exception as e:
        summary_text = f"{tier.capitalize()} tier — risk score {risk_score}/100."

    # ── compose final response ────────────────────────────────────────────────
    monthly_limit = sender.get("monthly_limit_gbp", 2000)
    monthly_remaining = monthly_limit - monthly_sent

    result_payload = {
        "tier": tier,
        "risk_score": risk_score,
        "headline": copy["headline"],
        "summary": summary_text,
        "signals": signals,
        "action_label": copy["action_label"],
        "secondary_label": copy["secondary_label"],
        # ML debug info — visible in the db-strip on the frontend
        "_ml_debug": {
            "xgb_score": assessment["xgb_score"],
            "iso_score": assessment["iso_score"],
            "is_outlier": assessment["is_outlier"],
        },
        "_meta": {
            "sender_name": sender["full_name"],
            "recipient_name": recipient["display_name"],
            "recipient_bank": recipient["bank"],
            "recipient_country": recipient["country"],
            "account_masked": recipient["account_masked"],
            "past_transfer_count": len(transfer_history),
            "monthly_sent": monthly_sent,
            "monthly_limit": monthly_limit,
            "destination_currency": recipient["destination_currency"],
        },
    }

    return jsonify(result_payload)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
