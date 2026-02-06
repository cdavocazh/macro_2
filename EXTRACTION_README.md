# Data Extraction - Quick Reference

## 📊 To Refresh/Download Historical Data

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 2: Set API Key

```bash
export FRED_API_KEY='b4580ee69e5d56057d81490b590e4e95'
```

### Step 3: Run Extraction

```bash
# Full extraction (first time or complete refresh)
python extract_historical_data.py

# Incremental update (daily use - appends new data only)
python update_data.py
```

### What Gets Created

The `historical_data/` directory with 11 CSV files:

```
historical_data/
├── data_metadata.json          # Tracks last_extraction timestamp
├── russell_2000.csv            # ~730 rows (2 years of daily data)
├── sp500_ma200.csv             # ~730 rows (2 years of daily data)
├── vix_move.csv                # ~365 rows (1 year of daily data)
├── dxy.csv                     # ~365 rows (1 year of daily data)
├── shiller_cape.csv            # ~1,850 rows (since 1871!)
├── sp500_fundamentals.csv      # Accumulates daily snapshots
├── cboe_skew.csv               # ~30 rows (1 month of daily data)
├── us_gdp.csv                  # ~200 rows (quarterly since 1947)
├── market_cap.csv              # Historical data (varies)
├── marketcap_to_gdp.csv        # Calculated buffett indicator
└── _summary_latest.csv         # Latest values from all indicators
```

### Expected Output

```
================================================================================
HISTORICAL DATA EXTRACTION
================================================================================
Started at: 2026-01-29 10:00:00

✅ Output directory: historical_data/

📊 Extracting Russell 2000 indices...
  💾 Saved to: russell_2000.csv (730 total rows)

📊 Extracting S&P 500 / 200MA...
  💾 Saved to: sp500_ma200.csv (730 total rows)

📊 Extracting VIX and MOVE...
  💾 Saved to: vix_move.csv (365 total rows)

📊 Extracting DXY...
  💾 Saved to: dxy.csv (365 total rows)

📊 Extracting Shiller CAPE...
  💾 Saved to: shiller_cape.csv (1850 total rows)

📊 Extracting S&P 500 Fundamentals...
  💾 Saved to: sp500_fundamentals.csv (1 total rows)

📊 Extracting CBOE SKEW...
  💾 Saved to: cboe_skew.csv (30 total rows)

📊 Extracting FRED indicators...
  💾 Saved to: us_gdp.csv (200 total rows)
  💾 Saved to: market_cap.csv (100 total rows)
  💾 Saved to: marketcap_to_gdp.csv (100 total rows)

📊 Creating summary file...
  ✅ Summary file created

================================================================================
EXTRACTION SUMMARY
================================================================================
Successfully extracted 8 indicator groups

Files saved to: historical_data/

Extracted indicators:
  ✅ Russell 2000                      | Last date: 2026-01-29 | Rows: 730
  ✅ S&P 500 / 200MA                   | Last date: 2026-01-29 | Rows: 730
  ✅ VIX / MOVE                        | Last date: 2026-01-29 | Rows: 365
  ✅ DXY                               | Last date: 2026-01-29 | Rows: 365
  ✅ Shiller CAPE                      | Last date: 2026-01    | Rows: 1850
  ✅ S&P 500 P/E & P/B                 | Last date: 2026-01-29 | Rows: 1
  ✅ CBOE SKEW                         | Last date: 2026-01-29 | Rows: 30
  ✅ FRED (GDP, Market Cap)            | Last date: 2026-01-29 | Rows: varies

================================================================================
Completed at: 2026-01-29 10:05:23
================================================================================
```

## 📈 View the Data

```bash
# Interactive viewer
python view_data.py

# Quick summary
python view_data.py summary

# Preview a file
python view_data.py preview vix_move.csv

# Statistics
python view_data.py stats vix_move.csv
```

## 🔄 Daily Automation

### Option 1: Cron (Linux/Mac)

```bash
# Edit crontab
crontab -e

# Add this line (runs daily at 6 PM)
0 18 * * * cd /path/to/macro_2 && python update_data.py >> logs/update.log 2>&1
```

### Option 2: Task Scheduler (Windows)

1. Open Task Scheduler
2. Create Basic Task
3. Trigger: Daily at 6:00 PM
4. Action: Start a program
   - Program: `python`
   - Arguments: `update_data.py`
   - Start in: `C:\path\to\macro_2`

### Option 3: Python Scheduler

```python
import schedule
import time

def job():
    import subprocess
    subprocess.run(['python', 'update_data.py'])

schedule.every().day.at("18:00").do(job)

while True:
    schedule.run_pending()
    time.sleep(60)
```

## 📁 CSV File Format Examples

### russell_2000.csv

```csv
timestamp,date,russell_2000_value,russell_2000_growth,value_growth_ratio
2025-01-27 16:00:00,2025-01-27,195.50,202.30,0.9664
2025-01-28 16:00:00,2025-01-28,196.20,203.10,0.9660
2025-01-29 16:00:00,2025-01-29,197.00,204.50,0.9633
```

### vix_move.csv

```csv
timestamp,date,vix,move,vix_move_ratio
2025-01-27 16:00:00,2025-01-27,15.5,105.2,0.1473
2025-01-28 16:00:00,2025-01-28,16.2,106.8,0.1517
2025-01-29 16:00:00,2025-01-29,14.8,104.1,0.1421
```

### _summary_latest.csv

```csv
timestamp,date,indicator,indicator_key,status,value_main,value_secondary,value_ratio
2026-01-29 10:05:00,2026-01-29,Russell 2000 Value/Growth,2_russell_2000,success,197.0,204.5,0.9633
2026-01-29 10:05:00,2026-01-29,S&P 500 / 200MA,6a_sp500_to_ma200,success,5000.0,4850.0,1.0309
2026-01-29 10:05:00,2026-01-29,VIX,8_vix,success,14.8,,,
2026-01-29 10:05:00,2026-01-29,DXY,10_dxy,success,103.5,,,
```

## 🔧 Troubleshooting

### "No module named 'pandas'"

```bash
pip install -r requirements.txt
```

### "FRED_API_KEY not set"

```bash
# Option 1: Environment variable
export FRED_API_KEY='your_key_here'

# Option 2: Edit config.py (already set to working key)
# FRED_API_KEY = 'b4580ee69e5d56057d81490b590e4e95'
```

### "Permission denied"

```bash
chmod -R 755 historical_data/
```

### Extraction takes too long

The initial extraction downloads 2+ years of data. Subsequent runs with `update_data.py` are much faster (30-60 seconds) as they only fetch new data.

## 📊 Data Usage Examples

### Load and Analyze with Pandas

```python
import pandas as pd

# Load data
df = pd.read_csv('historical_data/vix_move.csv')
df['timestamp'] = pd.to_datetime(df['timestamp'])

# Calculate statistics
print(f"VIX Average: {df['vix'].mean():.2f}")
print(f"VIX Max: {df['vix'].max():.2f}")
print(f"High volatility days: {len(df[df['vix'] > 25])}")

# Filter recent data
recent = df[df['timestamp'] >= '2026-01-01']
print(recent.describe())
```

### Export to Excel

```python
import pandas as pd

# Load multiple files
russell = pd.read_csv('historical_data/russell_2000.csv')
sp500 = pd.read_csv('historical_data/sp500_ma200.csv')
vix = pd.read_csv('historical_data/vix_move.csv')

# Export to Excel
with pd.ExcelWriter('macro_data.xlsx') as writer:
    russell.to_excel(writer, sheet_name='Russell 2000', index=False)
    sp500.to_excel(writer, sheet_name='S&P 500', index=False)
    vix.to_excel(writer, sheet_name='VIX MOVE', index=False)
```

## 🎯 Key Features

✅ **Append-Only** - Never overwrites existing data
✅ **Deduplication** - Automatically removes duplicates by timestamp
✅ **Incremental** - Only fetch new data with `update_data.py`
✅ **Tracked** - `data_metadata.json` records last extraction time
✅ **Standard Format** - CSV files work with Excel, pandas, SQL, etc.

---

**For complete documentation:** See `DATA_EXTRACTION_GUIDE.md`
