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

import datetime

def fetch_advanced_ahrefs_data(target_url):
    """
    Queries Ahrefs v3 endpoints to pull DR, 6-Month Traffic History, 
    Top Countries, and Sample Organic Keywords.
    """
    domain = get_domain_from_url(target_url)
    results = {
        "dr": "N/A",
        "traffic_history": None, # Will hold a dataframe for the chart
        "top_countries": [],
        "keywords": [],
        "error": None
    }
    
    if not domain:
        results["error"] = "Invalid target domain format."
        return results
    if not AHREFS_API_KEY:
        results["error"] = "Ahrefs API key configuration is missing."
        return results

    headers = {
        "Authorization": f"Bearer {AHREFS_API_KEY}",
        "Accept": "application/json"
    }
    
    # Calculate Date Ranges for 6 months history
    today = datetime.date.today()
    six_months_ago = today - datetime.timedelta(days=180)
    
    # ----------------------------------------------------
    # ENDPOINT 1: FETCH DOMAIN RATING (DR)
    # ----------------------------------------------------
    try:
        dr_endpoint = "https://api.ahrefs.com/v3/site-explorer/domain-rating"
        dr_params = {"target": domain, "date": today.strftime("%Y-%m-%d"), "output": "json"}
        dr_res = requests.get(dr_endpoint, headers=headers, params=dr_params, timeout=10)
        if dr_res.status_code == 200:
            results["dr"] = dr_res.json().get("domain_rating", {}).get("domain_rating", 0)
    except Exception as e:
        pass

    # ----------------------------------------------------
    # ENDPOINT 2: FETCH 6-MONTH TRAFFIC HISTORY
    # ----------------------------------------------------
    try:
        history_endpoint = "https://api.ahrefs.com/v3/site-explorer/metrics-history"
        history_params = {
            "target": domain,
            "date_from": six_months_ago.strftime("%Y-%m-%d"),
            "date_to": today.strftime("%Y-%m-%d"),
            "history_grouping": "monthly",
            "output": "json"
            # Default select returns: date, org_traffic
        }
        hist_res = requests.get(history_endpoint, headers=headers, params=history_params, timeout=10)
        if hist_res.status_code == 200:
            raw_metrics = hist_res.json().get("metrics", [])
            # Sort chronologically by date
            sorted_metrics = sorted(raw_metrics, key=lambda x: x.get('date', ''))
            results["traffic_history"] = sorted_metrics
    except Exception as e:
        pass

    # ----------------------------------------------------
    # ENDPOINT 3: FETCH TOP GEOGRAPHIC REGIONS
    # ----------------------------------------------------
    try:
        geo_endpoint = "https://api.ahrefs.com/v3/site-explorer/metrics-by-country"
        geo_params = {"target": domain, "output": "json"}
        geo_res = requests.get(geo_endpoint, headers=headers, params=geo_params, timeout=10)
        if geo_res.status_code == 200:
            # Sort breakdown by traffic volume descending, take top 5
            countries = geo_res.json().get("metrics", [])
            sorted_countries = sorted(countries, key=lambda x: x.get('org_traffic', 0), reverse=True)
            results["top_countries"] = sorted_countries[:5]
    except Exception as e:
        pass

    # ----------------------------------------------------
    # ENDPOINT 4: FETCH SAMPLE ORGANIC KEYWORDS (Top 20 for brief summary)
    # ----------------------------------------------------
    try:
        kw_endpoint = "https://api.ahrefs.com/v3/site-explorer/organic-keywords"
        kw_params = {
            "target": domain, 
            "limit": 20, 
            "select": "keyword,position,volume,traffic", 
            "output": "json"
        }
        kw_res = requests.get(kw_endpoint, headers=headers, params=kw_params, timeout=10)
        if kw_res.status_code == 200:
            results["keywords"] = kw_res.json().get("keywords", [])
    except Exception as e:
        pass

    return results

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
        # Step 1: Run local scraper
        with st.spinner("Step 1/3: Scraping page HTML & checking guidelines..."):
            qa_results = check_link_and_tags(page_url, target_url, anchor_text, brand_name)
            
        # Step 2: Query Advanced Ahrefs Profiles
        with st.spinner("Step 2/3: Gathering advanced traffic, regional, and keyword graphs from Ahrefs..."):
            ahrefs_results = fetch_advanced_ahrefs_data(page_url)
            
        # Step 3: Run Gemini Evaluation
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
        raw_html_content = ""
        try:
            raw_html_content = requests.get(page_url, headers=headers, timeout=10).text
        except Exception:
            pass

        with st.spinner("Step 3/3: Running contextual AI Relevancy Audit via Gemini..."):
            ai_relevancy = analyze_relevancy_with_gemini(raw_html_content, target_niche, business_topic)
            
        # ==========================================
        # RENDER DASHBOARD INTERFACE
        # ==========================================
        st.markdown("---")
        st.subheader("📊 Live Backlink Audit Report")
        
        if qa_results["error"]:
            st.error(f"Scraping Error: {qa_results['error']}")
        else:
            # Top-Level Core Metric Highlights
            m_col1, m_col2, m_col3 = st.columns(3)
            with m_col1:
                st.metric(label="Domain Rating", value=f"DR {ahrefs_results['dr']}")
            with m_col2:
                status = "Indexable" if qa_results["is_indexable"] else "NoIndex ❌"
                st.metric(label="Crawler Index Status", value=status)
            with m_col3:
                brand_status = "Found" if qa_results["brand_mentioned"] else "Missing"
                st.metric(label="Brand Mention", value=brand_status)
                
            # --- CREATING CLEAN VISUAL TABS ---
            tab1, tab2, tab3 = st.tabs(["🔒 Compliance & Placement Rules", "📈 Traffic & Keyword Health", "🧠 Contextual Relevancy"])
            
            # --- TAB 1: SCRAPER COMPLIANCE ---
            with tab1:
                st.markdown("### Technical Risk Assessment")
                if qa_results["is_redirecting"]:
                    st.warning(f"⚠️ **Redirect Alert:** Link hops to: `{qa_results['final_destination_url']}`")
                else:
                    st.success("✅ **Redirect Check:** URL resolves directly without adjustments.")
                    
                if qa_results["is_ugc"]:
                    st.error(f"❌ **UGC Signal Found:** Flagged comment/forum footprint: *{qa_results['ugc_reason']}*")
                else:
                    st.success("✅ **UGC Profile Check:** Structured as editorial news/article space.")
                    
                if qa_results["listicle_top_3_pass"] == "PASS":
                    st.success(f"✅ **Listicle Spotting:** Brand '{brand_name}' ranked in top 3 headings!")
                elif qa_results["listicle_top_3_pass"] == "FAIL":
                    st.error(f"❌ **Listicle Hierarchy Failure:** Brand '{brand_name}' is sitting below item entry 3.")

                st.markdown("---")
                st.markdown("### Anchor Link Delivery Verification")
                if qa_results["link_found"]:
                    st.success("✅ **Link Footprint:** Verified matching target URL destination.")
                    if qa_results["anchor_matches"]:
                        st.success(f"✅ **Anchor Framework:** Text matches: *'{anchor_text}'*")
                    else:
                        st.warning("⚠️ **Anchor Framework Discrepancy:** URL matches, text does not.")
                    if qa_results["is_follow"]:
                        st.success("✅ **SEO Attribution:** Standard follow link.")
                    else:
                        st.error(f"❌ **SEO Attribution Failure:** Contains negative parameters: `{qa_results['rel_tags']}`")
                else:
                    st.error("❌ **Link Asset Missing:** Destination domain was completely missing from the markup framework.")

            # --- TAB 2: ADVANCED TRAFFIC & KEYWORDS ---
            with tab2:
                st.markdown("### Ahrefs Traffic & Performance Audit")
                
                # Plot 6 Month Historical Trend Line
                if ahrefs_results["traffic_history"]:
                    st.markdown("#### 📉 6-Month Organic Traffic Performance Trend")
                    dates = [item.get('date') for item in ahrefs_results["traffic_history"]]
                    traffic = [item.get('org_traffic', 0) for item in ahrefs_results["traffic_history"]]
                    
                    # Renders a native line chart inside Streamlit
                    st.line_chart(data=dict(zip(dates, traffic)))
                else:
                    st.caption("Historical traffic trend line unavailable for this host profile.")
                
                col_left, col_right = st.columns(2)
                
                with col_left:
                    st.markdown("#### 🌍 Top Traffic Regions")
                    if ahrefs_results["top_countries"]:
                        for item in ahrefs_results["top_countries"]:
                            st.write(f"🏳️‍🌈 **{item.get('country', 'Unknown')}**: {item.get('org_traffic', 0):,} organic visitors/mo")
                    else:
                        st.caption("No geographical distribution profiles found.")
                        
                with col_right:
                    st.markdown("#### 🔤 Organic Keyword Samples")
                    if ahrefs_results["keywords"]:
                        for item in ahrefs_results["keywords"]:
                            st.write(f"🔑 *{item.get('keyword')}* (Pos: #{item.get('position')} | Vol: {item.get('volume', 0):,})")
                    else:
                        st.caption("No matching organic keyword ranks observed.")

            # --- TAB 3: AI CONTEXT AND RELEVANCY ---
            with tab3:
                st.markdown("### Contextual Evaluation Engine")
                ai_col1, ai_col2 = st.columns(2)
                with ai_col1:
                    if ai_relevancy["niche_pass"] == "PASS":
                        st.success(f"🎯 **Niche Guardrail:** PASS")
                    else:
                        st.error(f"❌ **Niche Guardrail:** FAIL")
                    st.caption(f"Target Niche Profile: *{target_niche}*")
                        
                with ai_col2:
                    if ai_relevancy["topic_pass"] == "PASS":
                        st.success(f"✍️ **Topic Alignment:** PASS")
                    else:
                        st.error(f"❌ **Topic Alignment:** FAIL")
                    st.caption(f"Business Theme Profile: *{business_topic}*")
                        
                st.info(f"🤖 **AI Evaluation Reasoning:** {ai_relevancy['reason']}")