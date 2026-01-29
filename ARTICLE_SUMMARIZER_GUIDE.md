# Article Extraction & Summarization Guide

Complete toolkit for extracting and summarizing web articles, with special handling for the Citadel Securities article.

## 🚨 Why Did the Citadel Article Fail?

The URL `https://www.citadelsecurities.com/news-and-insights/politics-policy-rba-boe-boj/` returned a **403 Forbidden** error because:
- The website blocks automated bots/scrapers
- They detect non-browser requests
- Security measures prevent programmatic access

**Solution:** Manual copy-paste or advanced browser automation (Selenium)

---

## 📋 Quick Start (Citadel Article)

### Method 1: Manual Copy-Paste (Recommended)

```bash
# 1. Open the article in your browser
# 2. Select all text (Cmd+A / Ctrl+A)
# 3. Copy (Cmd+C / Ctrl+C)
# 4. Run the script

python summarize_citadel_article.py
```

The script will:
1. Extract text from clipboard
2. Generate 3-sentence and 5-sentence summaries
3. Save to `citadel_article_summary.txt`

### Method 2: Direct Python Usage

```python
from article_summarizer import extract_from_clipboard, summarize_extractive

# After copying article to clipboard:
article = extract_from_clipboard()
summary = summarize_extractive(article['text'], num_sentences=5)

print(summary['summary'])
```

---

## 🎯 Summarization Methods

### 1. **Extractive (No API, Free)** ✅ Recommended for Quick Use

**How it works:** Selects most important sentences based on word frequency

**Pros:**
- ✅ No API key needed
- ✅ Fast
- ✅ Works offline
- ✅ No dependencies beyond basic libraries

**Cons:**
- ❌ Basic quality
- ❌ May not capture nuance

**Usage:**
```python
from article_summarizer import summarize_extractive

summary = summarize_extractive(text, num_sentences=5)
print(summary['summary'])
```

**Best for:** Quick summaries, when you don't have API access

---

### 2. **HuggingFace Transformers (Free, Local)** ✅ Best Free Option

**How it works:** Uses BART neural network model (runs on your machine)

**Pros:**
- ✅ Free forever
- ✅ No API key needed
- ✅ Good quality summaries
- ✅ Privacy (runs locally)

**Cons:**
- ❌ Requires ~1GB download (first run only)
- ❌ Slower than extractive
- ❌ Needs GPU for best performance

**Installation:**
```bash
pip install transformers torch
```

**Usage:**
```python
from article_summarizer import summarize_with_transformers

summary = summarize_with_transformers(text, max_length=150)
print(summary['summary'])
```

**Best for:** When you want quality without paying for API

---

### 3. **Claude API (Anthropic)** 💎 Highest Quality

**How it works:** Uses Claude (same AI as this assistant!)

**Pros:**
- ✅ Excellent quality
- ✅ Multiple styles (concise, detailed, bullet points, executive)
- ✅ Understands context and nuance
- ✅ Fast

**Cons:**
- ❌ Requires API key (paid)
- ❌ Costs ~$0.01-0.05 per article

**Installation:**
```bash
pip install anthropic
export ANTHROPIC_API_KEY='your_api_key_here'
```

Get API key: https://console.anthropic.com/

**Usage:**
```python
from article_summarizer import summarize_with_llm

# Concise summary
summary = summarize_with_llm(text, style='concise')

# Detailed analysis
summary = summarize_with_llm(text, style='detailed')

# Bullet points
summary = summarize_with_llm(text, style='bullet_points')

# Executive summary
summary = summarize_with_llm(text, style='executive')

print(summary['summary'])
```

**Best for:** Professional use, when quality matters most

---

### 4. **OpenAI GPT (ChatGPT API)** 💡 Alternative Premium

**How it works:** Uses GPT-4 from OpenAI

**Pros:**
- ✅ High quality
- ✅ Multiple styles
- ✅ Fast

**Cons:**
- ❌ Requires API key (paid)
- ❌ Costs ~$0.02-0.08 per article
- ❌ Slightly more expensive than Claude

**Installation:**
```bash
pip install openai
export OPENAI_API_KEY='your_api_key_here'
```

Get API key: https://platform.openai.com/

**Usage:**
```python
from article_summarizer import summarize_with_openai

summary = summarize_with_openai(text, style='concise')
print(summary['summary'])
```

**Best for:** If you already have OpenAI credits

---

## 📊 Comparison Table

| Method | Cost | Quality | Speed | Setup Difficulty |
|--------|------|---------|-------|------------------|
| Extractive | Free | ⭐⭐ | ⚡⚡⚡ | Easy |
| Transformers | Free | ⭐⭐⭐⭐ | ⚡⚡ | Medium |
| Claude API | ~$0.02/article | ⭐⭐⭐⭐⭐ | ⚡⚡⚡ | Easy |
| OpenAI GPT | ~$0.05/article | ⭐⭐⭐⭐ | ⚡⚡⚡ | Easy |

---

## 🛠️ Installation

### Basic (Extractive only)
```bash
# Already included in macro_2 requirements
pip install requests beautifulsoup4 lxml pyperclip
```

### With Transformers (Free ML)
```bash
pip install transformers torch
```

### With Claude API
```bash
pip install anthropic
export ANTHROPIC_API_KEY='sk-ant-...'
```

### With OpenAI API
```bash
pip install openai
export OPENAI_API_KEY='sk-...'
```

### Optional: Better Article Extraction
```bash
pip install newspaper3k
```

---

## 📝 Complete Examples

### Example 1: Quick Citadel Summary

```python
from article_summarizer import extract_from_clipboard, summarize_extractive

# 1. Copy article text from browser
# 2. Run:

article = extract_from_clipboard()
summary = summarize_extractive(article['text'], num_sentences=3)

print("BRIEF SUMMARY:")
print(summary['summary'])
```

### Example 2: Detailed Analysis with Claude

```python
from article_summarizer import extract_from_clipboard, summarize_with_llm

article = extract_from_clipboard()

# Executive summary
summary = summarize_with_llm(article['text'], style='executive')
print(summary['summary'])
```

### Example 3: Batch Process Multiple URLs

```python
from article_summarizer import extract_and_summarize

urls = [
    "https://example.com/article1",
    "https://example.com/article2",
    "https://example.com/article3"
]

for url in urls:
    result = extract_and_summarize(url, method='transformers')
    if result.get('combined_success'):
        print(f"\n📄 {result['article']['title']}")
        print(f"📝 {result['summary']['summary']}")
    else:
        print(f"❌ Failed: {url}")
```

### Example 4: Save All Summaries

```python
from article_summarizer import extract_and_summarize, save_summary_to_file

url = "https://example.com/article"
result = extract_and_summarize(url, method='claude', style='detailed')

# Save to file
save_summary_to_file(result, 'output/article_summary.txt')
```

---

## 🔍 Advanced: Extract from Protected Sites

Some websites block automated access. Solutions:

### Option 1: Manual Copy-Paste (Easiest)
```python
from article_summarizer import extract_from_clipboard

# Copy text in browser, then:
article = extract_from_clipboard()
```

### Option 2: Selenium (Automated Browser)
```bash
pip install selenium webdriver-manager
```

```python
from selenium import webdriver
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# Launch actual browser
driver = webdriver.Chrome(ChromeDriverManager().install())
driver.get(url)

# Wait for page load
import time
time.sleep(3)

# Extract article
article_element = driver.find_element(By.TAG_NAME, "article")
text = article_element.text

driver.quit()

# Now summarize
from article_summarizer import summarize_extractive
summary = summarize_extractive(text, num_sentences=5)
```

### Option 3: Playwright (Modern Alternative)
```bash
pip install playwright
playwright install
```

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(url)

    # Extract text
    text = page.inner_text("article")

    browser.close()

# Summarize
summary = summarize_extractive(text)
```

---

## 📁 File Structure

```
macro_2/
├── article_summarizer.py          # Main library with all functions
├── summarize_citadel_article.py   # Quick script for Citadel article
├── ARTICLE_SUMMARIZER_GUIDE.md    # This guide
└── output/
    └── citadel_article_summary.txt # Saved summaries
```

---

## 💡 Tips & Best Practices

### 1. **Choose the Right Method**
- Quick read → Extractive (free, 5 sentences)
- Need quality → Transformers (free, ~150 words)
- Professional use → Claude API (~$0.02, best quality)

### 2. **Optimize API Costs**
```python
# For Claude API, use 'concise' for most articles
summary = summarize_with_llm(text, style='concise')  # Cheapest

# Use 'detailed' only for important articles
summary = summarize_with_llm(text, style='detailed')  # More expensive
```

### 3. **Handle Long Articles**
```python
# Transformers has 1024 token limit, truncate if needed
text_truncated = ' '.join(text.split()[:1024])
summary = summarize_with_transformers(text_truncated)
```

### 4. **Save Time with Batch Processing**
```python
articles = [extract_article_basic(url) for url in urls]
summaries = [summarize_extractive(a['text']) for a in articles if a.get('success')]
```

---

## ❓ Troubleshooting

### "403 Forbidden" Error
**Problem:** Website blocks automated access
**Solution:** Use manual copy-paste method

### "API Key Not Set" Error
**Problem:** Missing API key for Claude/OpenAI
**Solution:**
```bash
export ANTHROPIC_API_KEY='your_key'
# or
export OPENAI_API_KEY='your_key'
```

### "Module Not Found" Error
**Problem:** Missing dependencies
**Solution:**
```bash
pip install transformers  # or anthropic, or openai
```

### Poor Summary Quality (Extractive)
**Problem:** Extractive method too basic
**Solution:** Upgrade to Transformers (free) or Claude API (paid)

### Slow Performance (Transformers)
**Problem:** CPU processing is slow
**Solution:** Use GPU or switch to Claude API (cloud-based, faster)

---

## 🎓 Understanding Summarization

### Extractive vs. Abstractive

**Extractive** (used in `summarize_extractive`):
- Selects existing sentences from article
- Like highlighting important parts
- Fast, simple, preserves original wording
- May feel choppy

**Abstractive** (used in Transformers, Claude, OpenAI):
- Generates new sentences in own words
- Like a human writing a summary
- More natural, coherent
- Better captures meaning

---

## 📈 Integration with Macro Dashboard

Add article summarization to your macro indicators dashboard:

```python
# In your Streamlit dashboard
import streamlit as st
from article_summarizer import extract_article_basic, summarize_extractive

st.sidebar.header("News Summarizer")
url = st.sidebar.text_input("Article URL")

if st.sidebar.button("Summarize"):
    article = extract_article_basic(url)
    if article.get('success'):
        summary = summarize_extractive(article['text'], num_sentences=5)
        st.info(summary['summary'])
    else:
        st.error(f"Failed: {article.get('error')}")
```

---

## 🔐 Do You Need GenAI API Access?

**Short Answer: No, but it helps!**

### Without Any API (100% Free):
✅ Extractive summarization works perfectly
✅ Good for quick, basic summaries
✅ No account needed, no billing

### With Free Local ML (Still 100% Free):
✅ HuggingFace Transformers (better quality)
✅ One-time ~1GB download
✅ Runs on your machine, private

### With Paid API (Best Quality):
✅ Claude API (~$0.02 per article) - Recommended
✅ OpenAI GPT (~$0.05 per article)
✅ Requires credit card, but pay-as-you-go

**Recommendation:**
- Start with extractive (free)
- Upgrade to Transformers if you want better quality (still free)
- Use Claude API only for important articles

---

## 📞 Getting Help

**Issues with this script:**
- Check the error message
- Try manual copy-paste method
- See Troubleshooting section above

**Getting API Keys:**
- Claude: https://console.anthropic.com/
- OpenAI: https://platform.openai.com/

**Alternative Tools:**
- newspaper3k: Better article extraction
- Selenium/Playwright: For JavaScript-heavy sites
- Beautiful Soup: Custom scraping logic

---

**Last Updated:** January 29, 2026
