"""
Article Text Extraction and Summarization Script

This script provides multiple methods to:
1. Extract text from web articles
2. Summarize the extracted content using various approaches

No GenAI API needed for basic summarization - includes multiple free options!
"""

import requests
from bs4 import BeautifulSoup
import re
from typing import Dict, List, Optional
import json


# ============================================================================
# ARTICLE TEXT EXTRACTION
# ============================================================================

def extract_article_basic(url: str, headers: Optional[Dict] = None) -> Dict:
    """
    Basic article extraction using requests + BeautifulSoup.

    Args:
        url: Article URL
        headers: Optional custom headers (useful for avoiding blocks)

    Returns:
        Dict with 'title', 'text', 'paragraphs', 'error' keys
    """
    if headers is None:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # Extract title
        title = soup.find('h1')
        title_text = title.get_text(strip=True) if title else soup.title.string if soup.title else "No title"

        # Remove script and style elements
        for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            element.decompose()

        # Try to find article content (common patterns)
        article_content = None
        for selector in ['article', '.article-content', '.post-content', 'main', '.content', '#content']:
            article_content = soup.select_one(selector)
            if article_content:
                break

        # If no article container found, use body
        if not article_content:
            article_content = soup.body

        # Extract paragraphs
        paragraphs = []
        if article_content:
            for p in article_content.find_all('p'):
                text = p.get_text(strip=True)
                if len(text) > 50:  # Filter out short paragraphs (likely navigation/footer)
                    paragraphs.append(text)

        # Combine all text
        full_text = '\n\n'.join(paragraphs)

        return {
            'title': title_text,
            'text': full_text,
            'paragraphs': paragraphs,
            'url': url,
            'word_count': len(full_text.split()),
            'success': True
        }

    except requests.exceptions.HTTPError as e:
        return {
            'error': f'HTTP Error {e.response.status_code}',
            'message': 'Website blocked access (403) or page not found (404)',
            'suggestion': 'Try manual copy-paste or use Selenium for JavaScript-heavy sites',
            'success': False
        }
    except Exception as e:
        return {
            'error': str(e),
            'success': False
        }


def extract_article_advanced(url: str) -> Dict:
    """
    Advanced extraction using newspaper3k library (install: pip install newspaper3k).
    Better at identifying main article content vs. navigation/ads.
    """
    try:
        from newspaper import Article

        article = Article(url)
        article.download()
        article.parse()

        return {
            'title': article.title,
            'text': article.text,
            'authors': article.authors,
            'publish_date': str(article.publish_date) if article.publish_date else None,
            'top_image': article.top_image,
            'url': url,
            'word_count': len(article.text.split()),
            'success': True
        }
    except ImportError:
        return {
            'error': 'newspaper3k not installed',
            'suggestion': 'Run: pip install newspaper3k',
            'success': False
        }
    except Exception as e:
        return {
            'error': str(e),
            'success': False
        }


def extract_from_clipboard() -> Dict:
    """
    Extract article text from clipboard (if user manually copied).
    Useful when websites block automated access (like Citadel Securities).

    Requires: pip install pyperclip
    """
    try:
        import pyperclip

        text = pyperclip.paste()

        if not text or len(text) < 100:
            return {
                'error': 'Clipboard is empty or too short',
                'suggestion': 'Copy the article text first',
                'success': False
            }

        # Split into paragraphs
        paragraphs = [p.strip() for p in text.split('\n') if len(p.strip()) > 50]

        return {
            'title': 'From Clipboard',
            'text': text,
            'paragraphs': paragraphs,
            'word_count': len(text.split()),
            'source': 'clipboard',
            'success': True
        }
    except ImportError:
        return {
            'error': 'pyperclip not installed',
            'suggestion': 'Run: pip install pyperclip',
            'success': False
        }
    except Exception as e:
        return {
            'error': str(e),
            'success': False
        }


# ============================================================================
# SUMMARIZATION METHODS
# ============================================================================

def summarize_extractive(text: str, num_sentences: int = 5) -> Dict:
    """
    Extractive summarization: Select most important sentences.
    Uses simple frequency-based scoring (no ML required).

    Args:
        text: Full article text
        num_sentences: Number of sentences to include in summary

    Returns:
        Dict with summary and key sentences
    """
    # Split into sentences
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    if len(sentences) <= num_sentences:
        return {
            'summary': text,
            'method': 'extractive',
            'sentences_used': len(sentences),
            'note': 'Article too short for summarization'
        }

    # Calculate word frequencies
    words = re.findall(r'\w+', text.lower())
    word_freq = {}
    for word in words:
        if len(word) > 3:  # Ignore short words
            word_freq[word] = word_freq.get(word, 0) + 1

    # Score sentences based on word frequencies
    sentence_scores = {}
    for i, sentence in enumerate(sentences):
        score = 0
        words_in_sentence = re.findall(r'\w+', sentence.lower())
        for word in words_in_sentence:
            if word in word_freq:
                score += word_freq[word]
        sentence_scores[i] = score / len(words_in_sentence) if words_in_sentence else 0

    # Select top N sentences (maintain original order)
    top_indices = sorted(sentence_scores, key=sentence_scores.get, reverse=True)[:num_sentences]
    top_indices.sort()  # Maintain original order

    summary_sentences = [sentences[i] for i in top_indices]
    summary = '. '.join(summary_sentences) + '.'

    return {
        'summary': summary,
        'method': 'extractive (frequency-based)',
        'sentences_used': num_sentences,
        'original_length': len(sentences),
        'compression_ratio': round(num_sentences / len(sentences), 2)
    }


def summarize_with_llm(text: str, style: str = 'concise') -> Dict:
    """
    Summarization using Claude API (Anthropic).

    This uses the same API that I (Claude) run on!

    Args:
        text: Article text to summarize
        style: 'concise' | 'detailed' | 'bullet_points' | 'executive'

    Returns:
        Dict with summary and metadata

    Requires:
        - pip install anthropic
        - ANTHROPIC_API_KEY environment variable
    """
    try:
        import anthropic
        import os

        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            return {
                'error': 'ANTHROPIC_API_KEY not set',
                'suggestion': 'Get free API key from: https://console.anthropic.com/',
                'success': False
            }

        client = anthropic.Anthropic(api_key=api_key)

        # Create prompt based on style
        prompts = {
            'concise': 'Summarize this article in 3-5 sentences, focusing on the main points:',
            'detailed': 'Provide a detailed summary of this article with key insights, arguments, and conclusions:',
            'bullet_points': 'Summarize this article as bullet points covering: 1) Main topic 2) Key arguments 3) Evidence presented 4) Conclusions:',
            'executive': 'Provide an executive summary suitable for busy professionals, including: situation, key findings, implications:'
        }

        prompt = prompts.get(style, prompts['concise'])

        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": f"{prompt}\n\n{text}"}
            ]
        )

        summary = message.content[0].text

        return {
            'summary': summary,
            'method': f'Claude LLM ({style})',
            'model': 'claude-3-5-sonnet-20241022',
            'tokens_used': message.usage.input_tokens + message.usage.output_tokens,
            'success': True
        }

    except ImportError:
        return {
            'error': 'anthropic library not installed',
            'suggestion': 'Run: pip install anthropic',
            'success': False
        }
    except Exception as e:
        return {
            'error': str(e),
            'success': False
        }


def summarize_with_openai(text: str, style: str = 'concise') -> Dict:
    """
    Summarization using OpenAI GPT API.

    Args:
        text: Article text
        style: Same as summarize_with_llm

    Requires:
        - pip install openai
        - OPENAI_API_KEY environment variable
    """
    try:
        import openai
        import os

        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            return {
                'error': 'OPENAI_API_KEY not set',
                'suggestion': 'Get API key from: https://platform.openai.com/',
                'success': False
            }

        client = openai.OpenAI(api_key=api_key)

        prompts = {
            'concise': 'Summarize this article in 3-5 sentences:',
            'detailed': 'Provide a detailed summary with key insights and conclusions:',
            'bullet_points': 'Summarize as bullet points covering main topic, arguments, and conclusions:',
            'executive': 'Provide an executive summary with situation, findings, and implications:'
        }

        prompt = prompts.get(style, prompts['concise'])

        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "user", "content": f"{prompt}\n\n{text}"}
            ],
            max_tokens=1000
        )

        summary = response.choices[0].message.content

        return {
            'summary': summary,
            'method': f'OpenAI GPT ({style})',
            'model': 'gpt-4-turbo-preview',
            'tokens_used': response.usage.total_tokens,
            'success': True
        }

    except ImportError:
        return {
            'error': 'openai library not installed',
            'suggestion': 'Run: pip install openai',
            'success': False
        }
    except Exception as e:
        return {
            'error': str(e),
            'success': False
        }


def summarize_with_transformers(text: str, max_length: int = 150) -> Dict:
    """
    Free local summarization using HuggingFace transformers.
    No API key needed! Runs on your machine.

    Args:
        text: Article text
        max_length: Maximum summary length in tokens

    Requires:
        - pip install transformers torch
        - First run downloads ~1GB model
    """
    try:
        from transformers import pipeline

        # Initialize summarization pipeline (downloads model on first run)
        summarizer = pipeline("summarization", model="facebook/bart-large-cnn")

        # BART has max input of 1024 tokens, truncate if needed
        max_input = 1024
        words = text.split()
        if len(words) > max_input:
            text = ' '.join(words[:max_input])

        result = summarizer(text, max_length=max_length, min_length=30, do_sample=False)

        return {
            'summary': result[0]['summary_text'],
            'method': 'HuggingFace Transformers (BART)',
            'model': 'facebook/bart-large-cnn',
            'note': 'Free, runs locally, no API key needed',
            'success': True
        }

    except ImportError:
        return {
            'error': 'transformers library not installed',
            'suggestion': 'Run: pip install transformers torch',
            'note': 'First run will download ~1GB model',
            'success': False
        }
    except Exception as e:
        return {
            'error': str(e),
            'success': False
        }


# ============================================================================
# COMBINED WORKFLOW
# ============================================================================

def extract_and_summarize(url: str, method: str = 'extractive', **kwargs) -> Dict:
    """
    Complete workflow: Extract article + summarize.

    Args:
        url: Article URL
        method: 'extractive' | 'claude' | 'openai' | 'transformers'
        **kwargs: Additional arguments for specific methods

    Returns:
        Dict with extraction results and summary
    """
    # Extract article
    print(f"Extracting article from: {url}")
    article = extract_article_basic(url)

    if not article.get('success'):
        print(f"❌ Extraction failed: {article.get('error')}")
        return article

    print(f"✅ Extracted {article['word_count']} words")

    # Summarize
    text = article['text']
    print(f"Summarizing using method: {method}")

    if method == 'extractive':
        summary_result = summarize_extractive(text, kwargs.get('num_sentences', 5))
    elif method == 'claude':
        summary_result = summarize_with_llm(text, kwargs.get('style', 'concise'))
    elif method == 'openai':
        summary_result = summarize_with_openai(text, kwargs.get('style', 'concise'))
    elif method == 'transformers':
        summary_result = summarize_with_transformers(text, kwargs.get('max_length', 150))
    else:
        summary_result = {'error': f'Unknown method: {method}'}

    if summary_result.get('success', True):
        print(f"✅ Summary generated")

    return {
        'article': article,
        'summary': summary_result,
        'combined_success': article.get('success') and summary_result.get('success', True)
    }


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def save_summary_to_file(result: Dict, filename: str = 'article_summary.txt'):
    """Save extraction and summary results to a text file."""
    with open(filename, 'w', encoding='utf-8') as f:
        if 'article' in result:
            f.write(f"TITLE: {result['article'].get('title', 'N/A')}\n")
            f.write(f"URL: {result['article'].get('url', 'N/A')}\n")
            f.write(f"WORD COUNT: {result['article'].get('word_count', 'N/A')}\n")
            f.write("=" * 80 + "\n\n")

        if 'summary' in result:
            f.write("SUMMARY:\n")
            f.write("-" * 80 + "\n")
            f.write(result['summary'].get('summary', 'N/A'))
            f.write("\n\n")
            f.write(f"Method: {result['summary'].get('method', 'N/A')}\n")

        if 'article' in result and result['article'].get('text'):
            f.write("\n" + "=" * 80 + "\n")
            f.write("FULL TEXT:\n")
            f.write("-" * 80 + "\n")
            f.write(result['article']['text'])

    print(f"Saved to: {filename}")


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

def main():
    """Example usage of article extraction and summarization."""

    # Example 1: Try Citadel Securities article (may fail with 403)
    print("\n" + "=" * 80)
    print("EXAMPLE 1: Citadel Securities Article")
    print("=" * 80)

    url = "https://www.citadelsecurities.com/news-and-insights/politics-policy-rba-boe-boj/"

    # Try basic extraction
    result = extract_and_summarize(url, method='extractive', num_sentences=5)

    if not result.get('combined_success'):
        print("\n⚠️  Website blocked access!")
        print("💡 Workaround: Manually copy the article text, then use:")
        print("   result = extract_from_clipboard()")
        print("   summary = summarize_extractive(result['text'])")
    else:
        print("\n📝 SUMMARY:")
        print(result['summary']['summary'])
        save_summary_to_file(result, 'citadel_summary.txt')

    # Example 2: Use a more accessible article
    print("\n" + "=" * 80)
    print("EXAMPLE 2: Alternative Article (Reuters)")
    print("=" * 80)

    # Try a more accessible news site
    test_url = "https://www.reuters.com/markets/"
    result2 = extract_and_summarize(test_url, method='extractive', num_sentences=3)

    if result2.get('combined_success'):
        print(f"\n✅ Successfully extracted: {result2['article']['title']}")
        print(f"📝 Summary ({result2['summary']['sentences_used']} sentences):")
        print(result2['summary']['summary'])

    # Example 3: Show all available summarization methods
    print("\n" + "=" * 80)
    print("AVAILABLE SUMMARIZATION METHODS:")
    print("=" * 80)
    print("""
    1. extractive (no API needed) - Free, basic
       → summarize_extractive(text, num_sentences=5)

    2. transformers (HuggingFace) - Free, better quality
       → summarize_with_transformers(text)
       → Requires: pip install transformers torch
       → Downloads ~1GB model on first run

    3. claude (Anthropic API) - Best quality, paid
       → summarize_with_llm(text, style='concise')
       → Requires: ANTHROPIC_API_KEY
       → Get key: https://console.anthropic.com/

    4. openai (OpenAI GPT) - High quality, paid
       → summarize_with_openai(text, style='concise')
       → Requires: OPENAI_API_KEY
       → Get key: https://platform.openai.com/
    """)

    print("\n💡 For Citadel Securities article (403 blocked):")
    print("   1. Open URL in browser")
    print("   2. Copy article text (Cmd+A, Cmd+C)")
    print("   3. Run: extract_from_clipboard()")
    print("   4. Run: summarize_extractive(result['text'])")


if __name__ == "__main__":
    main()
