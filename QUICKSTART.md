# Quick Start Guide

Get the Macro Indicators Dashboard running in 5 minutes!

## Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 2: Get FRED API Key (Free)

1. Visit [https://fred.stlouisfed.org/docs/api/api_key.html](https://fred.stlouisfed.org/docs/api/api_key.html)
2. Sign up for a free account
3. Copy your API key

## Step 3: Configure API Key

**Option A - Environment Variable (Recommended):**
```bash
export FRED_API_KEY='your_api_key_here'
```

**Option B - Edit config.py:**
```python
FRED_API_KEY = 'your_api_key_here'
```

## Step 4: Run the Dashboard

**Linux/Mac:**
```bash
./run_dashboard.sh
```

**Windows:**
```bash
run_dashboard.bat
```

**Or manually:**
```bash
streamlit run app.py
```

## Step 5: View the Dashboard

The dashboard will automatically open in your browser at:
```
http://localhost:8501
```

## Testing Your Setup

Before running the dashboard, you can test your setup:

```bash
python test_setup.py
```

This will check:
- ✓ All required packages are installed
- ✓ API keys are configured
- ✓ Data sources are accessible
- ✓ Sample indicators can be fetched

## Using the Dashboard

1. **Initial Load**: The dashboard automatically fetches all indicators on startup
2. **Manual Refresh**: Click the "🔄 Refresh All Data" button in the sidebar
3. **Navigate**: Use tabs to view different categories of indicators
4. **Interpret**: Check the metrics and their interpretations

## Troubleshooting

### "FRED_API_KEY not set" error
→ Set your API key in `config.py` or as environment variable

### "No data available" errors
→ Check internet connection and try refreshing

### Import errors
→ Run `pip install -r requirements.txt` again

### Some indicators fail to load
→ This is normal. Some sources require paid subscriptions or may be temporarily unavailable

## Next Steps

- Read the full [README.md](README.md) for detailed documentation
- Check `config.py` to customize cache settings
- Explore the code in `data_extractors/` to understand data sources

## Support

For issues or questions:
- Check the [README.md](README.md) troubleshooting section
- Review error messages in the dashboard
- Verify API keys are configured correctly

---

**Ready to go?** Run `streamlit run app.py` and start tracking macro indicators! 📊
