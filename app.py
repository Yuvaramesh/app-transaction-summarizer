from flask import Flask, render_template, request, jsonify, send_file
from services.summarizer import TransactionSummarizer
from services.pdf_generator import PDFGenerator
from data.mock_data import get_mock_transactions, get_mock_user, get_mock_rates
import io
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

summarizer = TransactionSummarizer()
pdf_gen = PDFGenerator()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/summary", methods=["POST"])
def generate_summary():
    """Generate AI summary for a given month/year."""
    body = request.get_json(force=True)
    month = int(body.get("month", 4))
    year = int(body.get("year", 2026))

    user = get_mock_user()
    transactions = get_mock_transactions(month, year)
    rates = get_mock_rates()

    if not transactions:
        return jsonify({"error": "No transactions found for the selected period."}), 404

    summary = summarizer.generate(user, transactions, rates, month, year)
    return jsonify(summary)


@app.route("/api/export-pdf", methods=["POST"])
def export_pdf():
    """Generate and return a PDF statement."""
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


if __name__ == "__main__":
    app.run(debug=True, port=5000)
