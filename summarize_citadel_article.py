"""
Quick script to extract and summarize the Citadel Securities article.

Since the website blocks automated access (403 error), this provides a workaround.
"""

from article_summarizer import (
    extract_article_basic,
    extract_from_clipboard,
    summarize_extractive,
    summarize_with_llm,
    summarize_with_transformers,
    save_summary_to_file
)


def summarize_citadel_article_manual():
    """
    Workaround for Citadel Securities article (403 blocked).

    Steps:
    1. Open https://www.citadelsecurities.com/news-and-insights/politics-policy-rba-boe-boj/
    2. Copy all article text (Cmd+A / Ctrl+A, then Cmd+C / Ctrl+C)
    3. Run this script
    """
    print("=" * 80)
    print("CITADEL SECURITIES ARTICLE SUMMARIZER")
    print("=" * 80)

    print("\n📋 Attempting to extract from clipboard...")
    print("(Make sure you've copied the article text first!)\n")

    # Extract from clipboard
    article = extract_from_clipboard()

    if not article.get('success'):
        print(f"❌ Error: {article.get('error')}")
        print(f"💡 {article.get('suggestion')}")
        print("\nMANUAL STEPS:")
        print("1. Open: https://www.citadelsecurities.com/news-and-insights/politics-policy-rba-boe-boj/")
        print("2. Select all text (Cmd+A or Ctrl+A)")
        print("3. Copy (Cmd+C or Ctrl+C)")
        print("4. Run this script again")
        return

    print(f"✅ Extracted {article['word_count']} words from clipboard")

    # Method 1: Simple extractive summary (no dependencies)
    print("\n" + "=" * 80)
    print("METHOD 1: EXTRACTIVE SUMMARY (5 key sentences)")
    print("=" * 80)

    summary1 = summarize_extractive(article['text'], num_sentences=5)
    print(summary1['summary'])

    # Method 2: Shorter extractive summary
    print("\n" + "=" * 80)
    print("METHOD 2: BRIEF SUMMARY (3 sentences)")
    print("=" * 80)

    summary2 = summarize_extractive(article['text'], num_sentences=3)
    print(summary2['summary'])

    # Save results
    result = {
        'article': article,
        'summary': summary1
    }
    save_summary_to_file(result, 'citadel_article_summary.txt')

    print("\n" + "=" * 80)
    print("✅ Summary saved to: citadel_article_summary.txt")
    print("=" * 80)

    # Optional: Try advanced methods if available
    print("\n💡 OPTIONAL: Try better summarization methods:")
    print("\n1. Free (HuggingFace Transformers):")
    print("   pip install transformers torch")
    print("   summary = summarize_with_transformers(article['text'])")
    print("\n2. Paid but best (Claude API):")
    print("   pip install anthropic")
    print("   export ANTHROPIC_API_KEY='your_key'")
    print("   summary = summarize_with_llm(article['text'], style='detailed')")


def try_automated_extraction():
    """
    Attempt automated extraction (will likely fail with 403).
    Shows the error handling.
    """
    print("=" * 80)
    print("ATTEMPTING AUTOMATED EXTRACTION")
    print("=" * 80)

    url = "https://www.citadelsecurities.com/news-and-insights/politics-policy-rba-boe-boj/"

    print(f"\n🌐 Fetching: {url}")

    article = extract_article_basic(url)

    if not article.get('success'):
        print(f"\n❌ Automated extraction failed:")
        print(f"   Error: {article.get('error')}")
        print(f"   Message: {article.get('message')}")
        print(f"   Suggestion: {article.get('suggestion')}")
        print("\n💡 Use manual method instead (copy-paste from browser)")
        return None

    print(f"✅ Success! Extracted {article['word_count']} words")

    # Summarize
    summary = summarize_extractive(article['text'], num_sentences=5)
    print("\n📝 SUMMARY:")
    print(summary['summary'])

    return article


def interactive_mode():
    """Interactive mode - ask user what to do."""
    print("=" * 80)
    print("CITADEL SECURITIES ARTICLE SUMMARIZER")
    print("=" * 80)

    print("\nChoose extraction method:")
    print("1. Automated (try to fetch from URL - may fail)")
    print("2. Manual (copy-paste from browser)")

    choice = input("\nEnter choice (1 or 2): ").strip()

    if choice == '1':
        article = try_automated_extraction()
        if not article:
            print("\n⚠️  Automated method failed. Try manual method (option 2)")
    elif choice == '2':
        summarize_citadel_article_manual()
    else:
        print("Invalid choice. Exiting.")


if __name__ == "__main__":
    # Try automated first, fall back to manual
    print("\n🤖 Trying automated extraction first...\n")

    article = try_automated_extraction()

    if not article:
        print("\n" + "=" * 80)
        print("SWITCHING TO MANUAL MODE")
        print("=" * 80)
        input("\nPress Enter after you've copied the article text to clipboard...")
        summarize_citadel_article_manual()
