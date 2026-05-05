"""
Mock data layer — replace with real DB queries in production.
"""


def get_mock_user() -> dict:
    return {
        "name": "Vinoth Kumar",
        "email": "knowledgefindit18@gmail.com",
        "phone": "+447475355392",
        "kyc_status": "Approved",
        "account_type": "Personal",
    }


def get_mock_transactions(month: int, year: int) -> list[dict]:
    """Return transactions for the given month/year."""
    all_transactions = {
        (4, 2026): [
            {
                "transaction_id": "TXN2026040900026",
                "recipient_name": "Pommi",
                "recipient_full": "Shanthiru Menon",
                "bank": "Commercial Bank of Ceylon",
                "account_last4": "3939",
                "country": "Sri Lanka",
                "currency": "LKR",
                "amount_gbp": 356.00,
                "fee_gbp": 2.99,
                "amount_received": 140333.49,
                "exchange_rate": 425.03,
                "date": "Apr 9, 2026",
                "time": "5:37 PM",
                "status": "Processing",
            },
            {
                "transaction_id": "TXN2026040900025",
                "recipient_name": "Pommi",
                "recipient_full": "Shanthiru Menon",
                "bank": "Commercial Bank of Ceylon",
                "account_last4": "3939",
                "country": "Sri Lanka",
                "currency": "LKR",
                "amount_gbp": 365.00,
                "fee_gbp": 2.99,
                "amount_received": 143881.25,
                "exchange_rate": 425.03,
                "date": "Apr 9, 2026",
                "time": "5:37 PM",
                "status": "Processing",
            },
        ],
        (3, 2026): [
            {
                "transaction_id": "TXN2026031500010",
                "recipient_name": "Pommi",
                "recipient_full": "Shanthiru Menon",
                "bank": "Commercial Bank of Ceylon",
                "account_last4": "3939",
                "country": "Sri Lanka",
                "currency": "LKR",
                "amount_gbp": 400.00,
                "fee_gbp": 2.99,
                "amount_received": 163802.00,
                "exchange_rate": 418.50,
                "date": "Mar 15, 2026",
                "time": "3:12 PM",
                "status": "Completed",
            },
        ],
    }
    return all_transactions.get((month, year), [])


def get_mock_rates() -> dict:
    return {
        "LKR": {
            "current": 425.03,
            "prev_month": 418.50,
            "two_months_ago": 411.20,
            "currency_name": "Sri Lankan Rupee",
        },
        "PKR": {
            "current": 430.03,
            "prev_month": 425.10,
            "currency_name": "Pakistani Rupee",
        },
        "BDT": {
            "current": 166.75,
            "prev_month": 164.20,
            "currency_name": "Bangladeshi Taka",
        },
        "NPR": {
            "current": 204.04,
            "prev_month": 201.80,
            "currency_name": "Nepalese Rupee",
        },
        "USD": {
            "current": 1.36,
            "prev_month": 1.34,
            "currency_name": "US Dollar",
        },
    }
