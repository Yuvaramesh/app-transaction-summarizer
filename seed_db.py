"""
seed_db.py — Populate MongoDB with sample Ajeer data.
Run once before starting the app:  python seed_db.py
"""

"""
seed_db.py — Populate MongoDB with sample Ajeer data.
Run once before starting the app:  python seed_db.py
"""

import os
import certifi
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient, ASCENDING
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")

client = MongoClient(
    MONGO_URI,
    tlsCAFile=certifi.where(),
    serverSelectionTimeoutMS=30000,
)
_db_name = MONGO_URI.split("/")[-1].split("?")[0] or "ajeer"
db = client[_db_name]
# ── Drop existing collections so seed is idempotent ──────────────────────────
for col in ["senders", "recipients", "transfers", "recipient_flags"]:
    db[col].drop()

print("Dropped old collections. Seeding fresh data…")

now = datetime.now(timezone.utc)


def days_ago(n):
    return now - timedelta(days=n)


# ─────────────────────────────────────────────────────────────────────────────
# SENDERS
# ─────────────────────────────────────────────────────────────────────────────
senders = [
    {
        "_id": "S001",
        "full_name": "Kavitha Rajendran",
        "email": "kavitha.r@example.com",
        "account_created": days_ago(1095),
        "account_age_label": "3 years",
        "typical_transfer_amount": 240,
        "monthly_limit_gbp": 2000,
        "monthly_sent_gbp": 600,
        "total_transfers": 28,
        "kyc_status": "verified",
    },
    {
        "_id": "S002",
        "full_name": "Arjun Selvam",
        "email": "arjun.s@example.com",
        "account_created": days_ago(180),
        "account_age_label": "6 months",
        "typical_transfer_amount": 150,
        "monthly_limit_gbp": 1500,
        "monthly_sent_gbp": 150,
        "total_transfers": 9,
        "kyc_status": "verified",
    },
    {
        "_id": "S003",
        "full_name": "Priya Natarajan",
        "email": "priya.n@example.com",
        "account_created": days_ago(730),
        "account_age_label": "2 years",
        "typical_transfer_amount": 400,
        "monthly_limit_gbp": 3000,
        "monthly_sent_gbp": 1100,
        "total_transfers": 54,
        "kyc_status": "verified",
    },
    {
        "_id": "S004",
        "full_name": "Rajan Murugesan",
        "email": "rajan.m@example.com",
        "account_created": days_ago(30),
        "account_age_label": "30 days",
        "typical_transfer_amount": 80,
        "monthly_limit_gbp": 500,
        "monthly_sent_gbp": 80,
        "total_transfers": 2,
        "kyc_status": "pending",
    },
]

db["senders"].insert_many(senders)
db["senders"].create_index([("email", ASCENDING)], unique=True)
print(f"  ✓ Inserted {len(senders)} senders")


# ─────────────────────────────────────────────────────────────────────────────
# RECIPIENTS
# ─────────────────────────────────────────────────────────────────────────────
recipients = [
    {
        "_id": "R001",
        "display_name": "Pommi · Shanthiru Menon",
        "bank": "Commercial Bank of Ceylon",
        "country": "Sri Lanka",
        "destination_currency": "LKR",
        "account_masked": "****3939",
        "added_by_sender": "S001",
        "added_at": days_ago(120),
        "days_since_added": 120,
        "flag_count_48h": 0,
    },
    {
        "_id": "R002",
        "display_name": "Meena · Meena Krishnan",
        "bank": "State Bank of India",
        "country": "India",
        "destination_currency": "INR",
        "account_masked": "****5512",
        "added_by_sender": "S003",
        "added_at": days_ago(365),
        "days_since_added": 365,
        "flag_count_48h": 0,
    },
    {
        "_id": "R003",
        "display_name": "Dinesh · Dinesh Fernando",
        "bank": "Bank of Ceylon",
        "country": "Sri Lanka",
        "destination_currency": "LKR",
        "account_masked": "****7701",
        "added_by_sender": "S002",
        "added_at": days_ago(60),
        "days_since_added": 60,
        "flag_count_48h": 0,
    },
    {
        "_id": "R004",
        "display_name": "Anitha · ANITHA Nadesan",
        "bank": "United Bank Limited",
        "country": "Pakistan",
        "destination_currency": "PKR",
        "account_masked": "****6789",
        "added_by_sender": "S001",
        "added_at": days_ago(6),
        "days_since_added": 6,
        "flag_count_48h": 0,
    },
    {
        "_id": "R005",
        "display_name": "Siva · Sivaramakrishnan P",
        "bank": "Hatton National Bank",
        "country": "Sri Lanka",
        "destination_currency": "LKR",
        "account_masked": "****2244",
        "added_by_sender": "S002",
        "added_at": days_ago(10),
        "days_since_added": 10,
        "flag_count_48h": 1,
    },
    {
        "_id": "R006",
        "display_name": "Mohammed Rashid",
        "bank": "National Bank",
        "country": "Bangladesh",
        "destination_currency": "BDT",
        "account_masked": "****4421",
        "added_by_sender": "S004",
        "added_at": days_ago(2),
        "days_since_added": 2,
        "flag_count_48h": 3,
    },
    {
        "_id": "R007",
        "display_name": "Tariq · Tariq Hassan",
        "bank": "Sonali Bank",
        "country": "Bangladesh",
        "destination_currency": "BDT",
        "account_masked": "****0099",
        "added_by_sender": "S004",
        "added_at": days_ago(1),
        "days_since_added": 1,
        "flag_count_48h": 5,
    },
]

db["recipients"].insert_many(recipients)
print(f"  ✓ Inserted {len(recipients)} recipients")


# ─────────────────────────────────────────────────────────────────────────────
# TRANSFERS
# ─────────────────────────────────────────────────────────────────────────────
transfers = [
    {
        "sender_id": "S001",
        "recipient_id": "R001",
        "amount_gbp": 356,
        "destination_currency": "LKR",
        "converted_amount": 140333,
        "status": "completed",
        "created_at": days_ago(15),
    },
    {
        "sender_id": "S001",
        "recipient_id": "R001",
        "amount_gbp": 320,
        "destination_currency": "LKR",
        "converted_amount": 126080,
        "status": "completed",
        "created_at": days_ago(45),
    },
    {
        "sender_id": "S003",
        "recipient_id": "R002",
        "amount_gbp": 390,
        "destination_currency": "INR",
        "converted_amount": 41300,
        "status": "completed",
        "created_at": days_ago(8),
    },
    {
        "sender_id": "S003",
        "recipient_id": "R002",
        "amount_gbp": 410,
        "destination_currency": "INR",
        "converted_amount": 43460,
        "status": "completed",
        "created_at": days_ago(38),
    },
    {
        "sender_id": "S003",
        "recipient_id": "R002",
        "amount_gbp": 380,
        "destination_currency": "INR",
        "converted_amount": 40280,
        "status": "completed",
        "created_at": days_ago(68),
    },
    {
        "sender_id": "S002",
        "recipient_id": "R003",
        "amount_gbp": 145,
        "destination_currency": "LKR",
        "converted_amount": 57100,
        "status": "completed",
        "created_at": days_ago(20),
    },
    {
        "sender_id": "S002",
        "recipient_id": "R005",
        "amount_gbp": 500,
        "destination_currency": "LKR",
        "converted_amount": 197000,
        "status": "pending",
        "created_at": days_ago(1),
    },
]

db["transfers"].insert_many(transfers)
db["transfers"].create_index([("sender_id", ASCENDING), ("recipient_id", ASCENDING)])
db["transfers"].create_index([("created_at", ASCENDING)])
print(f"  ✓ Inserted {len(transfers)} transfers")


# ─────────────────────────────────────────────────────────────────────────────
# RECIPIENT FLAGS
# ─────────────────────────────────────────────────────────────────────────────
flags = [
    {
        "recipient_id": "R006",
        "flagged_by_sender": "S001",
        "reason": "Suspicious account format",
        "created_at": days_ago(1),
    },
    {
        "recipient_id": "R006",
        "flagged_by_sender": "S002",
        "reason": "Recipient unresponsive after transfer",
        "created_at": days_ago(0),
    },
    {
        "recipient_id": "R006",
        "flagged_by_sender": "S003",
        "reason": "Account number mismatch reported",
        "created_at": days_ago(0),
    },
    {
        "recipient_id": "R007",
        "flagged_by_sender": "S001",
        "reason": "Possible fraud",
        "created_at": days_ago(1),
    },
    {
        "recipient_id": "R007",
        "flagged_by_sender": "S002",
        "reason": "Duplicate of flagged account",
        "created_at": days_ago(0),
    },
    {
        "recipient_id": "R007",
        "flagged_by_sender": "S003",
        "reason": "Reported by recipient's own bank",
        "created_at": days_ago(0),
    },
    {
        "recipient_id": "R007",
        "flagged_by_sender": "S004",
        "reason": "Attempted double transfer",
        "created_at": days_ago(0),
    },
    {
        "recipient_id": "R007",
        "flagged_by_sender": "S004",
        "reason": "AML watchlist match suspected",
        "created_at": days_ago(0),
    },
    {
        "recipient_id": "R005",
        "flagged_by_sender": "S003",
        "reason": "Unusual recipient behaviour",
        "created_at": days_ago(1),
    },
]

db["recipient_flags"].insert_many(flags)
db["recipient_flags"].create_index(
    [("recipient_id", ASCENDING), ("created_at", ASCENDING)]
)
print(f"  ✓ Inserted {len(flags)} recipient flags")

print("\n✅ MongoDB seed complete. Collections in database:")
for col in db.list_collection_names():
    count = db[col].count_documents({})
    print(f"   {col}: {count} documents")

client.close()
