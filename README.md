# Ajeer – AI Transaction Summarizer

A Flask application that uses **Gemini 2.5 Flash Lite** to generate
personalised monthly transfer summaries and exportable PDF statements
for the Ajeer remittance customer portal.

---

## Project structure

```
ajeer-summarizer/
├── app.py                    # Flask routes
├── requirements.txt
├── .env.example
├── data/
│   └── mock_data.py          # Mock DB layer (replace with real queries)
├── services/
│   ├── summarizer.py         # Gemini API calls + metrics computation
│   └── pdf_generator.py      # ReportLab PDF generation
├── templates/
│   └── index.html
└── static/
    ├── css/style.css
    └── js/app.js
```

---

## Setup

### 1. Clone / copy the project

```bash
cd ajeer-summarizer
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
# Edit .env and add your Gemini API key
```

Get your key from: https://aistudio.google.com/app/apikey

### 5. Run the server

```bash
python app.py
```

Visit **http://localhost:5000**

---

## API endpoints

| Method | Endpoint            | Description                        |
| ------ | ------------------- | ---------------------------------- |
| POST   | `/api/summary`      | Generate AI summary for month/year |
| POST   | `/api/export-pdf`   | Download PDF statement             |
| GET    | `/api/transactions` | Raw transaction list for a period  |

### POST /api/summary – Request body

```json
{ "month": 4, "year": 2026 }
```

### POST /api/summary – Response

```json
{
  "month": 4,
  "year": 2026,
  "month_name": "April",
  "user": { "name": "Vinoth Kumar", ... },
  "metrics": {
    "total_gbp": 721.00,
    "total_fees": 5.98,
    "transfer_count": 2,
    "received_by_currency": { "LKR": 284214.74 },
    "avg_rate_lkr": 425.03,
    "rate_change_pct": 1.56
  },
  "narrative": "AI-generated paragraph...",
  "nudge": "AI-generated nudge message...",
  "transactions": [ ... ]
}
```

---

## Connecting to a real database

Replace the functions in `data/mock_data.py` with your actual ORM/SQL queries:

```python
# data/mock_data.py
def get_mock_transactions(month: int, year: int) -> list[dict]:
    # Replace with:
    return db.session.query(Transaction).filter(
        extract('month', Transaction.created_at) == month,
        extract('year',  Transaction.created_at) == year,
        Transaction.user_id == current_user.id,
    ).all()
```

Each transaction dict must include:
`transaction_id`, `recipient_name`, `recipient_full`, `bank`, `country`,
`currency`, `amount_gbp`, `fee_gbp`, `amount_received`,
`exchange_rate`, `date`, `status`

---

## Customising the Gemini prompts

Edit the `_call_gemini` and `_call_gemini_nudge` methods in
`services/summarizer.py` to adjust tone, length, or language of the
AI-generated content
