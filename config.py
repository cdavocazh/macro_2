"""
Configuration file for API keys and settings.
Set your API keys here or as environment variables.
"""
import os

# FRED API Key (get free key from https://fred.stlouisfed.org/docs/api/api_key.html)
FRED_API_KEY = os.getenv('FRED_API_KEY', '')

# Data cache settings
CACHE_DIR = 'data_cache'
CACHE_EXPIRY_HOURS = 24

# Data sources
SHILLER_DATA_URL = 'http://www.econ.yale.edu/~shiller/data/ie_data.xls'
