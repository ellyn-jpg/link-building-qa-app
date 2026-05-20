import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

# Fetch the Ahrefs API key securely from Streamlit Secrets
AHREFS_API_KEY = st.secrets.get("AHREFS_API_KEY", "")

def get_domain_from_url(url):
    """Extracts the root domain (e.g., 'example.com') from a full URL."""
    try:
        parsed_domain = urlparse(url).netloc
        if parsed_domain.startswith("www."):
            parsed_domain = parsed_domain[4:]
        return parsed_domain
    except Exception:
        return None

def check_link_and_tags(page_url, target_url, expected_anchor, brand_name):
    """Scrapes the live page to verify links, anchor text, indexability, and brand mentions."""
    results = {
        "link_found": False,
        "anchor_matches": False,
        "is_follow": True,
        "rel_tags": [],
        "brand_mentioned": False,
        "is_indexable": True,
        "error": None
    }
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        response = requests.get(page_url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            results["error"] = f"Unable to fetch page (Status Code: {response.status_code})"
            return results
            
        soup = BeautifulSoup(response.text, 'html.parser')
        page_text = soup.get_text().lower()
        
        # 1. Check Brand Mention
        if brand_name and brand_name.lower() in page_text:
            results["brand_mentioned"] = True

        # 2. Check Indexability (Meta Robots)
        robots_meta = soup.find('meta', attrs={'name': 'robots'})
        if robots_meta and 'noindex' in robots_meta.get('content', '').lower():
            results["is_indexable"] = False

        # 3. Scan Links for Target URL
        links = soup.find_all('a', href=True)
        for link in links:
            if target_url.strip().lower() in link['href'].lower():
                results["link_found"] = True
                
                # Check Anchor Text
                if expected_anchor.strip().lower() in link.text.lower():
                    results["anchor_matches"] = True
                
                # Check Rel Attributes (Nofollow/Sponsored)
                rel = link.get('rel', [])
                results["rel_tags"] = rel
                if any(tag in ['nofollow', 'sponsored', 'ugc'] for tag in rel):
                    results["is_follow"] = False
                break 
                
        return results

    except Exception as e:
        results["error"] = str(e)
        return results

def fetch_ahrefs_dr(target_url):
    """Fetches the Domain Rating (DR) from Ahrefs API v3."""
    domain = get_domain_from_url(target_url)
    if not domain or not AHREFS_API_KEY:
        return {"dr": "N/A", "error": "Missing domain or Ahrefs API key configuration."}
        
    endpoint = "https://api.ahrefs.com/v3/site-explorer/domain-rating"