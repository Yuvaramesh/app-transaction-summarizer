# quicktest.py
import certifi
from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URI = os.environ.get("MONGO_URI")
try:
    c = MongoClient(MONGO_URI, tlsInsecure=True, serverSelectionTimeoutMS=10000)
    c.admin.command("ping")
    print("✅ Connected with tlsInsecure=True")
except Exception as e:
    print(f"❌ Still failed: {e}")
