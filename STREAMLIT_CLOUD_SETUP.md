# Streamlit Cloud Deployment Guide

## 🚀 Quick Deploy to Streamlit Cloud

### Step 1: Push Your Code to GitHub

Make sure your repository is pushed to GitHub with all the latest changes.

### Step 2: Deploy on Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with your GitHub account
3. Click "New app"
4. Select your repository: `cdavocazh/macro_2`
5. Set the main file path: `app.py`
6. Click "Deploy"

### Step 3: Configure Secrets (FRED API Key)

**Important:** You need to add your FRED API key as a secret in Streamlit Cloud.

1. In your deployed app dashboard, click "⚙️ Settings"
2. Click on "Secrets" in the left sidebar
3. Add the following in the secrets editor:

```toml
FRED_API_KEY = "your_actual_fred_api_key_here"
```

4. Click "Save"
5. Your app will automatically restart with the new secret

### Get Your FRED API Key (Free)

1. Visit: https://fred.stlouisfed.org/docs/api/api_key.html
2. Create a free account
3. Request an API key (instant approval)
4. Copy the API key and paste it in Streamlit secrets

## 📋 Streamlit Cloud Configuration Files

### 1. `.streamlit/secrets.toml` (Local Development)

For local testing of Streamlit secrets, create this file:

```bash
mkdir -p .streamlit
nano .streamlit/secrets.toml
```

Add:
```toml
FRED_API_KEY = "your_key_here"
```

**Note:** This file is in `.gitignore` and won't be committed to GitHub.

### 2. `requirements.txt`

Already configured with Python 3.13-compatible versions:
```
streamlit>=1.31.0
pandas>=2.2.0
numpy>=1.26.0
yfinance>=0.2.36
fredapi>=0.5.1
requests>=2.31.0
beautifulsoup4>=4.12.3
lxml>=5.1.0
plotly>=5.18.0
openpyxl>=3.1.2
```

**Note:** OpenBB has been removed from requirements as it's optional and may cause deployment issues.

## ⚙️ Configuration Options

### Option 1: Streamlit Secrets (Recommended for Cloud)

In Streamlit Cloud dashboard → Settings → Secrets:
```toml
FRED_API_KEY = "your_key_here"
```

### Option 2: Environment Variables (Local Development)

```bash
export FRED_API_KEY='your_key_here'
streamlit run app.py
```

### Option 3: Edit `config.py` (Local Development Only)

**Not recommended for deployed apps**, but you can edit `config.py` directly:

```python
FRED_API_KEY = 'your_key_here'  # Replace the line that reads from env/secrets
```

## 🔧 Troubleshooting

### Build Errors

**Issue:** `pandas` compilation fails
**Solution:** Updated `requirements.txt` to use `pandas>=2.2.0` (compatible with Python 3.13)

**Issue:** `openbb` installation fails
**Solution:** OpenBB is now optional. The dashboard will work without it, just some indicators may not be available.

### API Key Issues

**Issue:** "FRED_API_KEY not set" error
**Solution:** Add your FRED API key in Streamlit Cloud Secrets (see Step 3 above)

**Issue:** Secrets not loading
**Solution:**
1. Check secrets are saved in TOML format with quotes: `FRED_API_KEY = "key"`
2. Restart the app after adding secrets
3. Check there are no syntax errors in the secrets editor

### Data Source Failures

**Issue:** Some indicators show errors
**Expected:** Some data sources (MacroMicro, CBOE Put/Call) may fail due to scraping limitations
**Solution:** These are expected failures for free data sources. The dashboard is designed to handle them gracefully.

## 📊 Working Indicators (No API Key Required)

Even without FRED API key, these indicators will work:

✅ Russell 2000 Value & Growth (Yahoo Finance)
✅ S&P 500 / 200MA (Yahoo Finance)
✅ Shiller CAPE Ratio (Robert Shiller/Yale)
✅ VIX (Yahoo Finance)
✅ VIX/MOVE Ratio (Yahoo Finance)
✅ MOVE Index (Yahoo Finance)
✅ DXY - US Dollar Index (Yahoo Finance)
✅ CBOE SKEW (Yahoo Finance)

## 🔐 Indicators Requiring FRED API Key

❗ S&P 500 Market Cap / GDP (Buffett Indicator)

## ⚠️ Indicators with Limitations

⚠️ S&P 500 Forward P/E (MacroMicro - may require authentication)
⚠️ S&P 500 Trailing P/E & P/B (requires OpenBB - optional)
⚠️ S&P 500 Put/Call Ratio (CBOE - web scraping limited)

## 🎯 Expected Performance

- **App startup time:** 30-60 seconds (first time)
- **Refresh time:** 10-30 seconds (depends on data sources)
- **Most indicators:** Should load successfully
- **Some failures:** Expected for MacroMicro and CBOE Put/Call

## 📱 Accessing Your Deployed App

Once deployed, your app will be available at:
```
https://your-app-name.streamlit.app
```

You can share this URL with anyone!

## 🔄 Updating Your App

To update your deployed app:

1. Push changes to your GitHub repository
2. Streamlit Cloud will automatically detect changes
3. Click "Reboot" in the app dashboard, or wait for auto-deploy

## 💡 Best Practices

1. **Always use Secrets for API keys** - Never hardcode keys in your code
2. **Test locally first** - Use `.streamlit/secrets.toml` for local testing
3. **Monitor logs** - Check Streamlit Cloud logs for any errors
4. **Keep dependencies minimal** - Removed optional packages like OpenBB

## 📚 Additional Resources

- [Streamlit Cloud Documentation](https://docs.streamlit.io/streamlit-community-cloud)
- [Streamlit Secrets Management](https://docs.streamlit.io/streamlit-community-cloud/deploy-your-app/secrets-management)
- [FRED API Documentation](https://fred.stlouisfed.org/docs/api/fred/)

---

**Having issues?** Check the "Manage app" → "Logs" section in Streamlit Cloud for detailed error messages.
