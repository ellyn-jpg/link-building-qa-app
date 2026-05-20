import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import json
from google import genai  # <--- Clean Gemini Import

# Secure API Keys
AHREFS_API_KEY = st.secrets.get("AHREFS_API_KEY", "")
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")

# Initialize Gemini Client
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

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
    """
    Advanced scraping suite: Validates live placements, follow metrics, 
    UGC flags, redirect vulnerabilities, and listicle positioning.
    """
    results = {
        "link_found": False,
        "anchor_matches": False,
        "is_follow": True,
        "rel_tags": [],
        "brand_mentioned": False,
        "is_indexable": True,
        "is_ugc": False,
        "ugc_reason": "",
        "is_redirecting": False,
        "final_destination_url": page_url,
        "listicle_top_3_pass": "N/A",
        "error": None
    }
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        
        # --- 1. DOUBLE CHECK LINK REDIRECTS ---
        # allow_redirects=True lets us see where the link ultimately lands
        response = requests.get(page_url, headers=headers, timeout=10, allow_redirects=True)
        
        if response.status_code != 200:
            results["error"] = f"Unable to fetch page (Status Code: {response.status_code})"
            return results
            
        # Check if the initial URL hopped to a different URL
        if len(response.history) > 0:
            results["is_redirecting"] = True
            results["final_destination_url"] = response.url

        soup = BeautifulSoup(response.text, 'html.parser')
        page_text = soup.get_text().lower()
        
        # --- 2. BRAND MENTION CHECK ---
        if brand_name and brand_name.lower() in page_text:
            results["brand_mentioned"] = True

        # --- 3. CRAWLER INDEXABILITY CHECK ---
        robots_meta = soup.find('meta', attrs={'name': 'robots'})
        if robots_meta and 'noindex' in robots_meta.get('content', '').lower():
            results["is_indexable"] = False

        # --- 4. ANTI-UGC FOOTPRINT DETECTION ---
        # Look for common footprints left behind by forums, user comments, or open blogging sites
        ugc_signals = {
            "class_or_id": ['comment-list', 'comment-body', 'comments-area', 'forum-table', 'vbulletin', 'disqus_thread', 'bbpress-forums'],
            "text_patterns": ['leave a comment', 'post a comment', 'reply to this', 'anonymous user', 'user-generated']
        }
        
        # Check elements for UGC classes/IDs
        for element in soup.find_all(True, class_=True):
            if any(signal in ' '.join(element.get('class', [])).lower() for signal in ugc_signals["class_or_id"]):
                results["is_ugc"] = True
                results["ugc_reason"] = "UGC system classes/IDs detected in page code."
                break
                
        # Check plain text for UGC phrases if not caught yet
        if not results["is_ugc"]:
            if any(phrase in page_text for phrase in ugc_signals["text_patterns"]):
                results["is_ugc"] = True
                results["ugc_reason"] = "User-Generated text footprints found in body."

        # --- 5. TARGET BACKLINK AUDIT ---
        links = soup.find_all('a', href=True)
        for link in links:
            if target_url.strip().lower() in link['href'].lower():
                results["link_found"] = True
                
                # Verify Anchor Matches
                if expected_anchor.strip().lower() in link.text.lower():
                    results["anchor_matches"] = True
                
                # Check for paid/sponsored/ugc rel labels
                rel = link.get('rel', [])
                results["rel_tags"] = rel
                if any(tag in ['nofollow', 'sponsored', 'ugc'] for tag in rel):
                    results["is_follow"] = False
                break 

        # --- 6. LISTICLE TOP-3 RANKING CHECK ---
        # Detect if it's a listicle by checking titles for numbers followed by common buzzwords
        page_title = soup.title.text.lower() if soup.title else ""
        listicle_triggers = ['best', 'top', 'tools', 'ways', 'apps', 'platforms', 'services']
        
        is_listicle = any(char.isdigit() for char in page_title) and any(word in page_title for word in listicle_triggers)
        
        if is_listicle and brand_name:
            # Gather the first three primary contextual headings (H1, H2, or H3)
            headings = [h.text.strip().lower() for h in soup.find_all(['h1', 'h2', 'h3'])][:3]
            
            # Check if our brand name is highlighted in any of those top 3 headings
            brand_in_top_3 = any(brand_name.lower() in heading for heading in headings)
            results["listicle_top_3_pass"] = "PASS" if brand_in_top_3 else "FAIL"

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

def analyze_relevancy_with_gemini(page_html, target_niche, business_topic):
    """Runs structural JSON relevancy audit using Gemini 1.5 Flash."""
    if not gemini_client:
        return {"niche_pass": "Error", "topic_pass": "Error", "reason": "Gemini API Key missing."}
        
    try:
        soup = BeautifulSoup(page_html, 'html.parser')
        for script in soup(["script", "style"]):
            script.decompose()
            
        pure_text = soup.get_text(separator=' ')
        truncated_text = " ".join(pure_text.split()[:1500])
        
        prompt = f"""
        You are an expert SEO Quality Assurance Auditor. Analyze this article's content to determine its niche and topic contextual relevancy for a link placement.

        Target Niche/Industry: {target_niche}
        Client Business Topic/Core Product: {business_topic}

        Article Content Snippet:
        \"\"\"{truncated_text}\"\"\"

        Evaluate:
        1. Niche Relevancy: Is the website or article content contextually relevant or adjacent to the 'Target Niche'?
        2. Topic Relevancy: Does the specific theme of this article make contextual sense to reference or talk about the 'Client Business Topic'?
        """
        
        # We define a strict schema structure so Gemini outputs 100% predictable JSON
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',  # <--- Upgraded to the current stable version
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema={
                    "type": "OBJECT",
                    "properties": {
                        "niche_pass": {"type": "STRING", "enum": ["PASS", "FAIL"]},
                        "topic_pass": {"type": "STRING", "enum": ["PASS", "FAIL"]},
                        "reason": {"type": "STRING"}
                    },
                    "required": ["niche_pass", "topic_pass", "reason"]
                },
                temperature=0.1
            )
        )
        
        return json.loads(response.text)

    except Exception as e:
        return {"niche_pass": "Error", "topic_pass": "Error", "reason": f"Gemini Engine Exception: {str(e)}"}


# --- STREAMLIT USER INTERFACE ---
st.set_page_config(page_title="Link Building QA", page_icon="🔗", layout="centered")

st.title("🔗 Link Building QA Assistant")
st.write("Instantly audit live backlinks against compliance criteria and SEO targets.")
st.markdown("---")

# --- STREAMLIT USER INTERFACE FORM ---
with st.form("qa_form"):
    st.subheader("📋 Input Criteria")
    col1, col2 = st.columns(2)
    with col1:
        page_url = st.text_input("Live Page URL", placeholder="https://external-site.com/blog-post")
        target_url = st.text_input("Target URL (Your Site)", placeholder="https://mysite.com/landing-page")
        brand_name = st.text_input("Customer Brand Name", placeholder="MyBrand")
    with col2:
        anchor_text = st.text_input("Expected Anchor Text", placeholder="click here")
        target_niche = st.text_input("Target Niche / Industry", placeholder="e.g., Cybersecurity SaaS")
        business_topic = st.text_input("Client Core Topic / Product", placeholder="e.g., Password Manager App")
        
    submitted = st.form_submit_button("Run Full QA Audit")

# --- UNIFIED FORM SUBMISSION EXECUTION LAYER ---
if submitted:
    if not page_url or not target_url:
        st.error("❌ Please provide both the Live Page URL and Target URL to run the check.")
    else:
        # Step 1: Execute local rule scraper module
        with st.spinner("Step 1/3: Scraping page HTML & checking guidelines..."):
            qa_results = check_link_and_tags(page_url, target_url, anchor_text, brand_name)
            
        # Step 2: Execute Ahrefs API module
        with st.spinner("Step 2/3: Ping Ahrefs for Authority metrics..."):
            ahrefs_results = fetch_ahrefs_dr(page_url)
            
        # Step 3: Extract clean HTML string copy and feed the Gemini engine
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
        raw_html_content = ""
        try:
            raw_html_content = requests.get(page_url, headers=headers, timeout=10).text
        except Exception:
            pass

        with st.spinner("Step 3/3: Running contextual AI Relevancy Audit via Gemini..."):
            # Variables here match the exact text_input names declared right above
            ai_relevancy = analyze_relevancy_with_gemini(raw_html_content, target_niche, business_topic)
            
        # ==========================================
        # RENDER USER INTERFACE AUDIT REPORT
        # ==========================================
        st.markdown("---")
        st.subheader("📊 Advanced Audit Results Summary")
        
        if qa_results["error"]:
            st.error(f"Scraping Error: {qa_results['error']}")
        else:
            # Main high-level dashboard counters
            m_col1, m_col2, m_col3 = st.columns(3)
            with m_col1:
                st.metric(label="Domain Rating (DR)", value=f"DR {ahrefs_results['dr']}")
            with m_col2:
                status = "Indexable" if qa_results["is_indexable"] else "NoIndex ❌"
                st.metric(label="Crawler Index Status", value=status)
            with m_col3:
                brand_status = "Found" if qa_results["brand_mentioned"] else "Missing"
                st.metric(label="Brand Mention Check", value=brand_status)
            
            # --- AI Relevancy Visualization Cards ---
            st.markdown("### 🧠 AI Context & Relevancy Engine")
            ai_col1, ai_col2 = st.columns(2)
            with ai_col1:
                if ai_relevancy["niche_pass"] == "PASS":
                    st.success(f"🎯 **Domain Niche:** PASS")
                else:
                    st.error(f"❌ **Domain Niche:** FAIL")
                st.caption(f"Target Expectation: *{target_niche}*")
                    
            with ai_col2:
                if ai_relevancy["topic_pass"] == "PASS":
                    st.success(f"✍️ **Topic Alignment:** PASS")
                else:
                    st.error(f"❌ **Topic Alignment:** FAIL")
                st.caption(f"Target Expectation: *{business_topic}*")
                    
            st.info(f"🤖 **AI Audit Insights:** {ai_relevancy['reason']}")

            # --- Technical Risk Analysis Cards ---
            st.markdown("### 🔍 Risk & Quality Guardrails")
            
            if qa_results["is_redirecting"]:
                st.warning(f"⚠️ **Redirect Detected:** The source URL undergoes a redirect. It lands at: `{qa_results['final_destination_url']}`")
            else:
                st.success("✅ **URL Redirect Status:** Clean. The page resolves with zero sneaky redirects.")
                
            if qa_results["is_ugc"]:
                st.error(f"❌ **UGC Risk Found:** This page looks like a comment section, forum, or public blogging tier. Reason: *{qa_results['ugc_reason']}*")
            else:
                st.success("✅ **UGC Risk Evaluation:** Clean. Content looks like an editorial or standalone article.")
                
            if qa_results["listicle_top_3_pass"] == "PASS":
                st.success(f"✅ **Listicle Placement:** Your brand '{brand_name}' was found within the top 3 items of the article headings!")
            elif qa_results["listicle_top_3_pass"] == "FAIL":
                st.error(f"❌ **Listicle Placement Failure:** This looks like a listicle, but your brand '{brand_name}' is buried below the top 3 spots.")

            # --- Target Backlink Placement Verification ---
            st.markdown("### 🔗 Target Link Placement Verification")
            
            if qa_results["link_found"]:
                st.success("✅ **Link Discovery:** Target URL found live on the page layout.")
                
                if qa_results["anchor_matches"]:
                    st.success(f"✅ **Anchor Text:** Match found for: *'{anchor_text}'*")
                else:
                    st.warning(f"⚠️ **Anchor Text Mismatch:** Link found, but anchor text does not match.")
                
                if qa_results["is_follow"]:
                    st.success("✅ **Link Attributes:** Clean DoFollow link (No 'nofollow', 'sponsored', or 'ugc' parameters found).")
                else:
                    st.error(f"❌ **Link Attribute Error:** Restrictive parameters found inside link tag: `{qa_results['rel_tags']}`")
            else:
                st.error("❌ **Link Placement Failure:** The target URL could not be found anywhere in the page's HTML structure.")
                
            if ahrefs_results["error"]:
                st.caption(f"Ahrefs Debug Info: {ahrefs_results['error']}")