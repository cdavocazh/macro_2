# Historical Data Extraction Guide

Complete system for downloading and managing historical macroeconomic indicator data in CSV format.

## 🎯 Features

✅ **Append-Only Mode** - New data is added, never overwrites existing
✅ **Timestamp Tracking** - Metadata tracks last extraction time
✅ **Incremental Updates** - Only fetch new data since last run
✅ **CSV Format** - Standard, portable, easy to analyze
✅ **Deduplication** - Automatically removes duplicate entries
✅ **Summary Files** - Latest values from all indicators in one file

---

## 📁 Output Structure

```
macro_2/
├── historical_data/               # Created automatically
│   ├── data_metadata.json        # Tracks last_timestamp
│   ├── russell_2000.csv          # Russell 2000 Value & Growth
│   ├── sp500_ma200.csv           # S&P 500 with 200-day MA
│   ├── vix_move.csv              # VIX and MOVE indices
│   ├── dxy.csv                   # US Dollar Index
│   ├── shiller_cape.csv          # Shiller CAPE historical
│   ├── sp500_fundamentals.csv    # P/E and P/B ratios
│   ├── cboe_skew.csv             # CBOE SKEW Index
│   ├── us_gdp.csv                # US GDP (quarterly)
│   ├── market_cap.csv            # S&P 500 Market Cap
│   ├── marketcap_to_gdp.csv      # Buffett Indicator
│   └── _summary_latest.csv       # Latest values from all indicators
```

---

## 🚀 Quick Start

### Step 1: Initial Extraction

```bash
# Download all historical data (first time)
python extract_historical_data.py
```

**What it does:**
- Downloads historical data for all 10 indicators
- Creates CSV files in `historical_data/` directory
- Saves metadata with timestamp
- Takes 2-5 minutes

**Output example:**
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

...

================================================================================
EXTRACTION SUMMARY
================================================================================
Successfully extracted 8 indicator groups

Extracted indicators:
  ✅ Russell 2000                      | Last date: 2026-01-29 | Rows: 730
  ✅ S&P 500 / 200MA                   | Last date: 2026-01-29 | Rows: 730
  ✅ VIX / MOVE                        | Last date: 2026-01-29 | Rows: 365
  ✅ DXY                               | Last date: 2026-01-29 | Rows: 365
  ✅ Shiller CAPE                      | Last date: 2026-01    | Rows: 1800+
  ✅ S&P 500 P/E & P/B                 | Last date: 2026-01-29 | Rows: 1
  ✅ CBOE SKEW                         | Last date: 2026-01-29 | Rows: 30
  ✅ FRED (GDP, Market Cap)            | Last date: 2026-01-29 | Rows: varies
================================================================================
```

### Step 2: Daily Updates

```bash
# Update with new data (append-only)
python update_data.py
```

**What it does:**
- Checks `last_timestamp` from metadata
- Fetches only new data since last run
- Appends to existing CSV files (no duplication)
- Updates metadata timestamp
- Takes 30-60 seconds

### Step 3: View Data

```bash
# Interactive viewer
python view_data.py

# Or specific commands:
python view_data.py list              # List all CSV files
python view_data.py summary           # Show latest values
python view_data.py preview vix_move.csv    # Preview a file
python view_data.py stats vix_move.csv      # Show statistics
```

---

## 📊 Available Data Files

### 1. `russell_2000.csv`
Historical data for Russell 2000 Value and Growth indices.

**Columns:**
- `timestamp` - Date and time
- `date` - Date only
- `russell_2000_value` - Value index price
- `russell_2000_growth` - Growth index price
- `value_growth_ratio` - Value/Growth ratio

**Update Frequency:** Daily (real-time during market hours)
**History:** ~2 years (730 trading days)

### 2. `sp500_ma200.csv`
S&P 500 price with 200-day moving average.

**Columns:**
- `timestamp` - Date and time
- `date` - Date only
- `sp500_close` - S&P 500 closing price
- `sp500_ma200` - 200-day moving average
- `price_to_ma200_ratio` - Price / MA200 ratio

**Update Frequency:** Daily (real-time during market hours)
**History:** ~2 years (need 200 days for MA calculation)

### 3. `vix_move.csv`
VIX (equity volatility) and MOVE (bond volatility) indices.

**Columns:**
- `timestamp` - Date and time
- `date` - Date only
- `vix` - CBOE Volatility Index
- `move` - ICE BofA MOVE Index
- `vix_move_ratio` - VIX/MOVE ratio

**Update Frequency:** Daily
**History:** ~1 year (365 days)

### 4. `dxy.csv`
US Dollar Index (DXY).

**Columns:**
- `timestamp` - Date and time
- `date` - Date only
- `dxy` - US Dollar Index value

**Update Frequency:** Daily (real-time during market hours)
**History:** ~1 year (365 days)

### 5. `shiller_cape.csv`
Shiller CAPE Ratio (Cyclically Adjusted P/E).

**Columns:**
- `date` - Month/Year
- `timestamp` - Date timestamp
- `cape_ratio` - CAPE value

**Update Frequency:** Monthly
**History:** Since 1871 (150+ years!)

### 6. `sp500_fundamentals.csv`
S&P 500 P/E and P/B ratios (snapshot).

**Columns:**
- `timestamp` - Date and time
- `date` - Date only
- `pe_ratio_trailing` - Trailing P/E
- `pb_ratio` - Price-to-Book ratio

**Update Frequency:** Daily snapshot
**History:** Accumulates with each run

### 7. `cboe_skew.csv`
CBOE SKEW Index (tail risk measure).

**Columns:**
- `timestamp` - Date and time
- `date` - Date only
- `cboe_skew` - SKEW value

**Update Frequency:** Daily
**History:** ~30 days

### 8. `us_gdp.csv`
US Gross Domestic Product.

**Columns:**
- `timestamp` - Date timestamp
- `date` - Date (quarterly)
- `us_gdp` - GDP in billions of dollars

**Update Frequency:** Quarterly
**History:** Historical FRED data

### 9. `market_cap.csv`
S&P 500 Market Capitalization.

**Columns:**
- `timestamp` - Date timestamp
- `date` - Date
- `market_cap` - Market cap value

**Update Frequency:** Varies (annual/quarterly)
**History:** Historical FRED data

### 10. `marketcap_to_gdp.csv`
Buffett Indicator (Market Cap / GDP ratio).

**Columns:**
- `timestamp` - Date timestamp
- `date` - Date (quarterly)
- `us_gdp` - US GDP
- `market_cap` - Market capitalization
- `marketcap_to_gdp_ratio` - Ratio as percentage

**Update Frequency:** Quarterly
**History:** Historical calculated data

### 11. `_summary_latest.csv`
Summary file with latest values from all indicators.

**Columns:**
- `timestamp` - When extracted
- `date` - Date
- `indicator` - Indicator name
- `indicator_key` - Internal key
- `status` - 'success' or 'failed'
- `value_main` - Primary value
- `value_secondary` - Secondary value (if applicable)
- `value_ratio` - Calculated ratio (if applicable)

**Update Frequency:** Updated with every extraction
**Use:** Quick overview of current market conditions

---

## 🔄 Append-Only Mechanism

### How It Works

1. **First Run:**
   ```python
   # Downloads all historical data
   # Creates CSV: russell_2000.csv (730 rows)
   # Saves metadata: {"last_extraction": "2026-01-29T10:00:00"}
   ```

2. **Second Run (Next Day):**
   ```python
   # Loads existing CSV (730 rows)
   # Fetches new data (1 new row)
   # Combines: 730 + 1 = 731 rows
   # Removes duplicates based on timestamp
   # Saves updated CSV (731 rows)
   # Updates metadata: {"last_extraction": "2026-01-30T10:00:00"}
   ```

3. **Deduplication:**
   ```python
   # Automatically removes duplicate timestamps
   # Keeps latest value if duplicates exist
   # Maintains chronological order
   ```

### Example Code

```python
def append_to_csv(filename, new_data, timestamp_col='timestamp'):
    """Append new data, avoiding duplicates."""
    filepath = os.path.join(OUTPUT_DIR, filename)

    if os.path.exists(filepath):
        # Load existing data
        existing_data = pd.read_csv(filepath)

        # Combine and deduplicate
        combined = pd.concat([existing_data, new_data], ignore_index=True)
        combined = combined.drop_duplicates(subset=[timestamp_col], keep='last')
        combined = combined.sort_values(timestamp_col)
    else:
        combined = new_data

    # Save
    combined.to_csv(filepath, index=False)
```

---

## 📈 Metadata Tracking

### File: `data_metadata.json`

```json
{
  "last_extraction": "2026-01-29T10:30:45",
  "indicators": {
    "russell_2000": {
      "indicator": "Russell 2000",
      "last_date": "2026-01-29",
      "rows": 730
    },
    "sp500_ma200": {
      "indicator": "S&P 500 / 200MA",
      "last_date": "2026-01-29",
      "rows": 730
    },
    "vix_move": {
      "indicator": "VIX / MOVE",
      "last_date": "2026-01-29",
      "rows": 365
    }
  }
}
```

**Purpose:**
- Track when data was last extracted
- Store metadata for each indicator
- Enable incremental updates
- Provide extraction history

---

## 🛠️ Usage Examples

### Example 1: Daily Automated Update

```bash
#!/bin/bash
# daily_update.sh - Run this daily via cron

cd /path/to/macro_2
python update_data.py

# Optional: Upload to cloud storage
# aws s3 sync historical_data/ s3://my-bucket/macro-data/
```

### Example 2: Force Full Re-extraction

```bash
# Re-download all historical data
python update_data.py --full
```

### Example 3: View Latest Values

```bash
# Quick summary
python view_data.py summary
```

**Output:**
```
================================================================================
LATEST VALUES SUMMARY
================================================================================
As of: 2026-01-29 10:30:45

✅ S&P 500 Forward P/E                 |         N/A
✅ Russell 2000 Value/Growth          |       125.50
✅ S&P 500 P/E & P/B                  |        22.50
❌ S&P 500 Put/Call Ratio             |         N/A
✅ SPX Call Skew                      |       125.00
✅ S&P 500 / 200MA                    |      5000.00
✅ Market Cap / GDP                   |       175.00
✅ Shiller CAPE                       |        32.50
✅ VIX                                |        15.50
✅ VIX/MOVE Ratio                     |         0.15
✅ MOVE Index                         |       105.00
✅ DXY                                |       103.50
================================================================================
```

### Example 4: Analyze with Pandas

```python
import pandas as pd

# Load VIX/MOVE data
df = pd.read_csv('historical_data/vix_move.csv')

# Convert timestamp
df['timestamp'] = pd.to_datetime(df['timestamp'])

# Calculate statistics
print(f"VIX Average: {df['vix'].mean():.2f}")
print(f"VIX Max: {df['vix'].max():.2f}")
print(f"VIX Min: {df['vix'].min():.2f}")

# Find high volatility days
high_vix = df[df['vix'] > 25]
print(f"\nHigh volatility days: {len(high_vix)}")
print(high_vix[['date', 'vix']])

# Plot
import matplotlib.pyplot as plt
plt.figure(figsize=(12, 6))
plt.plot(df['timestamp'], df['vix'], label='VIX')
plt.plot(df['timestamp'], df['move'], label='MOVE')
plt.legend()
plt.title('VIX vs MOVE')
plt.show()
```

### Example 5: Export to Excel

```python
import pandas as pd

# Load multiple files
russell = pd.read_csv('historical_data/russell_2000.csv')
sp500 = pd.read_csv('historical_data/sp500_ma200.csv')
vix = pd.read_csv('historical_data/vix_move.csv')

# Export to Excel with multiple sheets
with pd.ExcelWriter('macro_indicators.xlsx') as writer:
    russell.to_excel(writer, sheet_name='Russell 2000', index=False)
    sp500.to_excel(writer, sheet_name='S&P 500', index=False)
    vix.to_excel(writer, sheet_name='VIX MOVE', index=False)

print("✅ Exported to macro_indicators.xlsx")
```

---

## 🔧 Customization

### Add New Indicator

1. **Create extractor function:**

```python
def extract_my_indicator():
    """Extract custom indicator."""
    # Fetch data
    data = fetch_from_source()

    # Create DataFrame
    df = pd.DataFrame({
        'timestamp': data.index,
        'date': data.index.date,
        'my_value': data.values
    })

    df['timestamp'] = pd.to_datetime(df['timestamp'])

    # Save
    append_to_csv('my_indicator.csv', df)

    return {
        'indicator': 'My Indicator',
        'last_date': df['date'].max(),
        'rows': len(df)
    }
```

2. **Add to extraction script:**

```python
# In extract_all_historical_data()
result = extract_my_indicator()
if result:
    results.append(result)
    metadata['indicators']['my_indicator'] = result
```

### Change Data History Length

Edit extractor functions to adjust date ranges:

```python
# In yfinance_extractors.py
# Change from 730 days to 365 days
end_date = datetime.now()
start_date = end_date - timedelta(days=365)  # Changed from 730
```

### Filter Data on Export

```python
# Only export last 90 days
df = pd.read_csv('historical_data/vix_move.csv')
df['timestamp'] = pd.to_datetime(df['timestamp'])

recent = df[df['timestamp'] >= (datetime.now() - timedelta(days=90))]
recent.to_csv('vix_move_recent_90d.csv', index=False)
```

---

## ⚙️ Scheduled Automation

### Using Cron (Linux/Mac)

```bash
# Edit crontab
crontab -e

# Add daily update at 6 PM
0 18 * * * cd /path/to/macro_2 && python update_data.py >> logs/update.log 2>&1
```

### Using Task Scheduler (Windows)

1. Open Task Scheduler
2. Create Basic Task
3. Trigger: Daily at 6:00 PM
4. Action: Start a program
5. Program: `python`
6. Arguments: `update_data.py`
7. Start in: `C:\path\to\macro_2`

### Using Python Script

```python
import schedule
import time

def job():
    """Daily update job."""
    print(f"Running update at {datetime.now()}")
    import subprocess
    subprocess.run(['python', 'update_data.py'])

# Schedule daily at 6 PM
schedule.every().day.at("18:00").do(job)

print("Scheduler started. Press Ctrl+C to stop.")
while True:
    schedule.run_pending()
    time.sleep(60)
```

---

## 📊 Data Quality & Validation

### Check for Gaps

```python
import pandas as pd

df = pd.read_csv('historical_data/vix_move.csv')
df['timestamp'] = pd.to_datetime(df['timestamp'])

# Check for date gaps
df = df.sort_values('timestamp')
df['days_diff'] = df['timestamp'].diff().dt.days

gaps = df[df['days_diff'] > 1]
if len(gaps) > 0:
    print("⚠️  Date gaps found:")
    print(gaps[['timestamp', 'days_diff']])
else:
    print("✅ No date gaps")
```

### Validate Values

```python
df = pd.read_csv('historical_data/vix_move.csv')

# Check for missing values
missing = df.isnull().sum()
print("Missing values:")
print(missing)

# Check for outliers (VIX > 80 is unusual)
outliers = df[df['vix'] > 80]
if len(outliers) > 0:
    print(f"⚠️  {len(outliers)} potential outliers found")
```

---

## 🚨 Troubleshooting

### Issue: "No module named 'pandas'"
**Solution:**
```bash
pip install -r requirements.txt
```

### Issue: "FRED_API_KEY not set"
**Solution:**
```bash
export FRED_API_KEY='your_key_here'
# Or edit config.py
```

### Issue: "Permission denied" when saving files
**Solution:**
```bash
chmod -R 755 historical_data/
# Or run with appropriate permissions
```

### Issue: Duplicate rows in CSV
**Solution:** The append mechanism automatically deduplicates, but you can manually clean:
```python
import pandas as pd

df = pd.read_csv('historical_data/vix_move.csv')
df = df.drop_duplicates(subset=['timestamp'], keep='last')
df.to_csv('historical_data/vix_move.csv', index=False)
```

### Issue: Data extraction takes too long
**Solution:** Extract one indicator at a time:
```python
# In extract_historical_data.py, comment out indicators you don't need
# result = extract_dxy()  # Comment this line
```

---

## 📁 Files Summary

| File | Purpose | Size |
|------|---------|------|
| `extract_historical_data.py` | Main extraction script | 600+ LOC |
| `update_data.py` | Quick update script | 50 LOC |
| `view_data.py` | Data viewer utility | 200 LOC |
| `DATA_EXTRACTION_GUIDE.md` | This documentation | - |

---

## 🎯 Best Practices

1. **Daily Updates**: Run `update_data.py` daily after market close (6 PM ET)
2. **Backup Data**: Regularly backup `historical_data/` directory
3. **Validate**: Check `_summary_latest.csv` for data quality
4. **Monitor Metadata**: Review `data_metadata.json` for extraction history
5. **Version Control**: Don't commit CSV files to git (too large)
6. **Cloud Storage**: Consider syncing to S3/Google Drive for backup

---

## 📈 Next Steps

1. **Run initial extraction**: `python extract_historical_data.py`
2. **View your data**: `python view_data.py summary`
3. **Set up daily updates**: Add to cron or Task Scheduler
4. **Analyze**: Use pandas/Excel to analyze CSV files
5. **Integrate**: Load data into your dashboard or analytics tools

---

**Last Updated:** January 29, 2026
