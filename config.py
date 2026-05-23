"""
Configuration file for API keys and settings.
Set your API keys in .env or as environment variables.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root (works regardless of cwd)
_PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(_PROJECT_ROOT / '.env')

# FRED API Key (get free key from https://fred.stlouisfed.org/docs/api/api_key.html)
# Priority: Streamlit secrets > .env file > environment variable
try:
    import streamlit as st
    FRED_API_KEY = st.secrets.get('FRED_API_KEY', os.getenv('FRED_API_KEY', ''))
except (ImportError, FileNotFoundError, KeyError):
    FRED_API_KEY = os.getenv('FRED_API_KEY', '')

# Data cache settings
CACHE_DIR = 'data_cache'
CACHE_EXPIRY_HOURS = 24

# IBKR Streaming Configuration
IBKR_HOST = os.getenv('IBKR_HOST', '127.0.0.1')
IBKR_PORT = os.getenv('IBKR_PORT', '')  # empty = auto-detect
IBKR_CLIENT_ID = int(os.getenv('IBKR_CLIENT_ID', '31'))
IBKR_JSON_INTERVAL = 3       # seconds between realtime JSON writes
IBKR_CSV_INTERVAL = 300      # seconds between CSV summary writes (5 min)
IBKR_RECONNECT_DELAY = 3600  # seconds between connection retries (1 hour)

# Data sources
SHILLER_DATA_URL = 'http://www.econ.yale.edu/~shiller/data/ie_data.xls'
