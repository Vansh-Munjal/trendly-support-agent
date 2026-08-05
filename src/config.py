"""Configuration — loads .env and exposes all settings."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

ORDERS_FILE = DATA_DIR / "orders.json"
POLICY_FILE = DATA_DIR / "trendly_policy.md"
DB_FILE = DATA_DIR / "trendly.db"

# Primary LLM (set LLM_PROVIDER in .env to switch: "groq" or "gemini")
LLM_PROVIDER:    str = os.getenv("LLM_PROVIDER", "groq")
GROQ_MODEL:      str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GEMINI_MODEL:    str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))
