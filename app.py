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
    if not domain:
        return {"dr": "N/A", "error": "Invalid target domain extracted."}
    if not AHREFS_API_KEY:
        return {"dr": "N/A", "error": "Ahrefs API key is empty in Streamlit Secrets."}
        
    endpoint = "https://api.ahrefs.com/v3/site-explorer/domain-rating"
    headers = {
        "Authorization": f"Bearer {AHREFS_API_KEY}",
        "Accept": "application/json"
    }
    
    # Ahrefs v3 STRICTLY requires target, date, and output fields. 
    params = {
        "target": domain,
        "date": "2026-05-20",  # Always request yesterday's data to avoid timezone/data latency sync drops
        "output": "json"
    }
    
    try:
        response = requests.get(endpoint, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # Safely navigate the nested JSON response object from Ahrefs
            dr_score = data.get("domain_rating", {}).get("domain_rating", 0)
            return {"dr": dr_score, "error": None}
        else:
            # Let's extract any specific error messaging the server provides in the response payload
            try:
                server_message = response.json().get('error', response.text)
            except Exception:
                server_message = response.text
            return {"dr": "Error", "error": f"Ahrefs API Error ({response.status_code}): {server_message}"}
    except Exception as e:
        return {"dr": "Error", "error": str(e)}


# --- STREAMLIT USER INTERFACE ---
st.set_page_config(page_title="Link Building QA", page_icon="🔗", layout="centered")

st.title("🔗 Link Building QA Assistant")
st.write("Instantly audit live backlinks against compliance criteria and SEO targets.")
st.markdown("---")

with st.form("qa_form"):
    st.subheader("📋 Input Criteria")
    col1, col2 = st.columns(2)
    with col1:
        page_url = st.text_input("Live Page URL", placeholder="https://external-site.com/blog-post")
        target_url = st.text_input("Target URL (Your Site)", placeholder="https://mysite.com/landing-page")
    with col2:
        anchor_text = st.text_input("Expected Anchor Text", placeholder="click here")
        brand_name = st.text_input("Customer Brand Name", placeholder="MyBrand")
        
    submitted = st.form_submit_button("Run Full QA Audit")

if submitted:
    if not page_url or not target_url:
        st.error("❌ Please provide both the Live Page URL and Target URL to run the check.")
    else:
        with st.spinner("Step 1/2: Scraping page HTML & checking guidelines..."):
            qa_results = check_link_and_tags(page_url, target_url, anchor_text, brand_name)
            
        with st.spinner("Step 2/2: Ping Ahrefs for Authority metrics..."):
            ahrefs_results = fetch_ahrefs_dr(page_url)
            
        st.markdown("---")
        st.subheader("📊 Audit Results Summary")
        
        if qa_results["error"]:
            st.error(f"Scraping Error: {qa_results['error']}")
        else:
            m_col1, m_col2, m_col3 = st.columns(3)
            with m_col1:
                st.metric(label="Domain Rating (DR)", value=f"DR {ahrefs_results['dr']}")
            with m_col2:
                status = "Indexable" if qa_results["is_indexable"] else "NoIndex ❌"
                st.metric(label="Crawler Index Status", value=status)
            with m_col3:
                brand_status = "Found" if qa_results["brand_mentioned"] else "Missing"
                st.metric(label="Brand Mention Check", value=brand_status)
            
            st.markdown("### Detailed Checks")
            
            if qa_results["link_found"]:
                st.success("✅ **Target URL Link Placement:** Link found live on the page.")
                if qa_results["anchor_matches"]:
                    st.success(f"✅ **Anchor Text:** Exact or partial match found for: *'{anchor_text}'*")
                else:
                    st.warning(f"⚠️ **Anchor Text Mismatch:** Target URL found, but anchor text looks different.")
                
                if qa_results["is_follow"]:
                    st.success("✅ **Link Attribute:** Link is clean and passed juice (No 'nofollow', 'sponsored', or 'ugc' detected).")
                else:
                    st.error(f"❌ **Link Attribute Error:** Restrictive parameters found: `{qa_results['rel_tags']}`")
            else:
                st.error("❌ **Link Placement Failure:** The target URL could not be find anywhere in the page's HTML structure.")
                
            if ahrefs_results["error"]:
                st.caption(f"Ahrefs Debug Info: {ahrefs_results['error']}")