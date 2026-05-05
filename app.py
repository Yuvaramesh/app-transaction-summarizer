"""
app.py — Ajeer Unified Dashboard
Combines: AI Transaction Summarizer + Recipient Risk Verification
Flask + MongoDB + Gemini
"""

import os
import json
import re
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, jsonify, send_file
from pymongo import MongoClient
import google.generativeai as genai
from dotenv import load_dotenv
import io

load_dotenv()

app = Flask(__name__)

# ── Gemini ───────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
genai.configure(api_key=GEMINI_API_KEY)
gemini_risk = genai.GenerativeModel("gemini-2.5-flash-lite-preview-06-17")

# ── MongoDB ──────────────────────────────────────────────────────────────────
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["ajeer"]

senders_col    = db["senders"]
recipients_col = db["recipients"]
transfers_col  = db["transfers"]
flags_col      = db["recipient_flags"]

# ── Summarizer service (lazy import to keep startup clean) ───────────────────
from services.summarizer import TransactionSummarizer
from services.pdf_generator import PDFGenerator
from data.mock_data import get_mock_transactions, get_mock_user, get_mock_rates

summarizer = TransactionSummarizer()
pdf_gen    = PDFGenerator()


# ════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ════════════════════════════════════════════════════════════════════════════

@app.route("/")
def dashboard():
    return render_template("dashboard.html")


# ════════════════════════════════════════════════════════════════════════════
# AI TRANSACTION SUMMARIZER  (tool 1)
# ════════════════════════════════════════════════════════════════════════════

@app.route("/summarizer")
def summarizer_page():
    return render_template("summarizer.html")


@app.route("/api/summary", methods=["POST"])
def generate_summary():
    body  = request.get_json(force=True)
    month = int(body.get("month", 4))
    year  = int(body.get("year", 2026))

    user         = get_mock_user()
    transactions = get_mock_transactions(month, year)
    rates        = get_mock_rates()

    if not transactions:
        return jsonify({"error": "No transactions found for the selected period."}), 404

    summary = summarizer.generate(user, transactions, rates, month, year)
    return jsonify(summary)


@app.route("/api/export-pdf", methods=["POST"])
def export_pdf():
    body  = request.get_json(force=True)
    month = int(body.get("month", 4))
    year  = int(body.get("year", 2026))

    user         = get_mock_user()
    transactions = get_mock_transactions(month, year)
    rates        = get_mock_rates()

    summary   = summarizer.generate(user, transactions, rates, month, year)
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
    year  = int(request.args.get("year", 2026))
    return jsonify(get_mock_transactions(month, year))


# ════════════════════════════════════════════════════════════════════════════
# RECIPIENT RISK VERIFICATION  (tool 2)
# ════════════════════════════════════════════════════════════════════════════

RISK_SYSTEM_PROMPT = """You are an AI compliance engine for Ajeer, an international remittance platform.
Your job is to evaluate international money transfer recipients and produce a structured risk assessment.

You will receive real data fetched from the platform's database including:
- Sender profile and full transfer history
- Recipient details, how recently they were added, and how many times they've been flagged
- The specific transfer being requested

You MUST respond ONLY with a valid JSON object (no markdown, no explanation, no extra text).

Schema:
{
  "tier": "green" | "amber" | "red",
  "risk_score": <integer 0-100>,
  "headline": "<short title, e.g. 'Recipient verified' | 'Please review before sending' | 'Transfer held for review'>",
  "summary": "<1-2 sentence explanation>",
  "signals": [
    { "status": "ok" | "warn" | "flag", "text": "<specific, data-driven signal>" }
  ],
  "action_label": "<CTA button label>",
  "secondary_label": "<cancel button label or null>"
}

Scoring guidance:
- green  0-30:  All signals clean, proceed normally
- amber 31-65:  Some anomalies, soft friction required
- red   66-100: Serious flags, hold for compliance review

Signal rules:
- Always include exactly 3-5 signals. Mix statuses based on actual data.
- Reference real numbers, dates, and counts from the input, never make up values.
- Check bank account format validity for the declared country.
- Flag if: recipient added < 7 days ago, flag_count_48h > 1, amount > 2x sender's typical, monthly limit would be exceeded, sender account is < 90 days old.
- Positive signals matter too: long transfer history, clean past transfers, valid account format should produce ok signals.
"""


@app.route("/verify")
def verify_page():
    return render_template("verify.html")


@app.route("/api/senders", methods=["GET"])
def list_senders():
    docs = list(senders_col.find({}, {
        "_id": 1, "full_name": 1, "typical_transfer_amount": 1,
        "monthly_limit_gbp": 1, "account_age_label": 1,
        "total_transfers": 1, "kyc_status": 1
    }))
    return jsonify(docs)


@app.route("/api/recipients", methods=["GET"])
def list_recipients():
    sender_id = request.args.get("sender_id")
    query = {"added_by_sender": sender_id} if sender_id else {}
    docs = list(recipients_col.find(query, {
        "_id": 1, "display_name": 1, "bank": 1, "country": 1,
        "destination_currency": 1, "account_masked": 1, "days_since_added": 1
    }))
    return jsonify(docs)


@app.route("/api/assess", methods=["POST"])
def assess():
    if not GEMINI_API_KEY:
        return jsonify({"error": "GEMINI_API_KEY not configured"}), 500

    body = request.get_json()
    if not body:
        return jsonify({"error": "No JSON body"}), 400

    sender_id        = body.get("sender_id")
    recipient_id     = body.get("recipient_id")
    amount           = float(body.get("amount", 0))
    converted_amount = body.get("converted_amount", "")

    if not sender_id or not recipient_id:
        return jsonify({"error": "sender_id and recipient_id are required"}), 400

    sender    = senders_col.find_one({"_id": sender_id})
    recipient = recipients_col.find_one({"_id": recipient_id})

    if not sender:
        return jsonify({"error": f"Sender '{sender_id}' not found"}), 404
    if not recipient:
        return jsonify({"error": f"Recipient '{recipient_id}' not found"}), 404

    # Transfer history
    transfer_history = list(transfers_col.find(
        {"sender_id": sender_id, "recipient_id": recipient_id},
        {"_id": 0, "amount_gbp": 1, "destination_currency": 1,
         "converted_amount": 1, "status": 1, "created_at": 1}
    ).sort("created_at", -1).limit(10))

    # Flags in 48h
    cutoff_48h = datetime.now(timezone.utc) - timedelta(hours=48)
    flag_count = flags_col.count_documents({
        "recipient_id": recipient_id,
        "created_at": {"$gte": cutoff_48h}
    })

    # Monthly sent
    cutoff_30d = datetime.now(timezone.utc) - timedelta(days=30)
    pipeline = [
        {"$match": {"sender_id": sender_id, "created_at": {"$gte": cutoff_30d}, "status": "completed"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount_gbp"}}}
    ]
    result = list(transfers_col.aggregate(pipeline))
    monthly_sent = result[0]["total"] if result else 0.0

    # Build prompt
    history_lines = "\n".join(
        f"  - £{t['amount_gbp']} -> {t.get('converted_amount', '?')} {t.get('destination_currency', '')}  "
        f"({t['status']})  {t['created_at'].strftime('%Y-%m-%d') if t.get('created_at') else 'N/A'}"
        for t in transfer_history
    ) or "  (no previous transfers to this recipient)"

    monthly_limit     = sender.get("monthly_limit_gbp", 2000)
    monthly_remaining = monthly_limit - monthly_sent

    prompt = f"""Assess this international transfer:

SENDER:
- ID: {sender['_id']}
- Name: {sender['full_name']}
- KYC status: {sender.get('kyc_status', 'unknown')}
- Account age: {sender.get('account_age_label', 'unknown')}
- Typical transfer amount: £{sender.get('typical_transfer_amount', 0)}
- Total lifetime transfers: {sender.get('total_transfers', 0)}
- 30-day sending limit: £{monthly_limit}
- 30-day total sent (from DB): £{monthly_sent:.2f}
- Remaining this month: £{monthly_remaining:.2f}

RECIPIENT:
- ID: {recipient['_id']}
- Name: {recipient['display_name']}
- Bank: {recipient['bank']}
- Country: {recipient['country']}
- Account (masked): {recipient['account_masked']}
- Days since added to sender account: {recipient['days_since_added']}
- Times flagged by other senders in past 48h: {flag_count}

PAST TRANSFERS (this sender to this recipient):
{history_lines}

THIS TRANSFER:
- Amount: £{amount}
- Destination: {converted_amount} {recipient['destination_currency']}

Provide the risk assessment JSON now."""

    try:
        response = gemini_risk.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.2,
                response_mime_type="application/json"
            ),
            system_instruction=RISK_SYSTEM_PROMPT
        )
        raw = response.text.strip()
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        return jsonify({"error": f"AI parse error: {e}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    result["_meta"] = {
        "sender_name":          sender["full_name"],
        "recipient_name":       recipient["display_name"],
        "recipient_bank":       recipient["bank"],
        "recipient_country":    recipient["country"],
        "account_masked":       recipient["account_masked"],
        "past_transfer_count":  len(transfer_history),
        "monthly_sent":         monthly_sent,
        "monthly_limit":        sender.get("monthly_limit_gbp", 2000),
        "destination_currency": recipient["destination_currency"],
    }

    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
