import streamlit as st
import feedparser
import google.generativeai as genai
from bs4 import BeautifulSoup
import re
from datetime import datetime

# --- 1. Page Configuration & Material Design CSS ---
st.set_page_config(page_title="NOD Sensing Dashboard", layout="wide")

st.markdown("""
<style>
    /* Google Material Design Inspired Styles */
    .stApp { background-color: #f8f9fa; }
    .main-title { font-size: 32px; font-weight: 700; color: #1a73e8; margin-bottom: 20px; }
    .card {
        background-color: white;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 20px;
        border: 1px solid #e0e0e0;
        transition: transform 0.2s ease-in-out;
    }
    .card:hover { transform: translateY(-5px); box-shadow: 0 8px 15px rgba(0,0,0,0.15); }
    .card-title { font-size: 18px; font-weight: 600; color: #202124; margin-bottom: 8px; line-height: 1.4; }
    .card-summary { font-size: 14px; color: #5f6368; margin-bottom: 12px; line-height: 1.5; }
    .card-link { font-size: 13px; color: #1a73e8; text-decoration: none; font-weight: 500; }
    .best-pick-label { background-color: #fbbc04; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; margin-bottom: 10px; display: inline-block; }
    .thumbnail { width: 100%; height: 180px; object-fit: cover; border-radius: 8px; margin-bottom: 12px; background-color: #eee; }
</style>
""", unsafe_allow_html=True)

# --- 2. Session State Initialization ---
if 'api_key' not in st.session_state: st.session_state.api_key = ""
if 'user_feeds' not in st.session_state:
    st.session_state.user_feeds = {
        "글로벌": [{"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "active": True}],
        "중국": [{"name": "36Kr", "url": "https://36kr.com/feed", "active": True}, {"name": "TechNode", "url": "https://technode.com/feed/", "active": True}],
        "일본": [{"name": "The Bridge JP", "url": "https://thebridge.jp/feed", "active": True}]
    }

# --- 3. Sidebar: Configuration & Feed Management ---
with st.sidebar:
    st.title("⚙️ Dashboard Settings")
    
    # API Key Section
    new_key = st.text_input("Gemini API Key", value=st.session_state.api_key, type="password", help="키를 입력하면 세션 동안 유지됩니다.")
    if new_key != st.session_state.api_key:
        st.session_state.api_key = new_key
        st.rerun()

    st.divider()
    
    # Feed Management
    st.subheader("🌐 채널 관리")
    category = st.selectbox("카테고리 선택", list(st.session_state.user_feeds.keys()))
    
    with st.expander(f"{category} 채널 추가"):
        new_name = st.text_input("사이트 이름")
        new_url = st.text_input("RSS URL")
        if st.button("추가하기"):
            if new_name and new_url:
                st.session_state.user_feeds[category].append({"name": new_name, "url": new_url, "active": True})
                st.success(f"{new_name} 추가됨!")
                st.rerun()

    st.divider()
    
    # Toggle Switches for Feeds
    st.subheader("✅ 활성 채널 선택")
    selected_urls = []
    for cat, feeds in st.session_state.user_feeds.items():
        st.write(f"**{cat}**")
        for f in feeds:
            is_active = st.checkbox(f["name"], value=f["active"], key=f"{cat}_{f['name']}")
            f["active"] = is_active
            if is_active: selected_urls.append(f)

# --- 4. Logic: Fetching and Parsing News ---
def get_thumbnail(entry):
    # Try to find an image in the description or media tags
    desc = entry.get('description', '')
    soup = BeautifulSoup(desc, 'html.parser')
    img_tag = soup.find('img')
    if img_tag and img_tag.get('src'): return img_tag['src']
    if 'media_content' in entry: return entry['media_content'][0]['url']
    return "https://via.placeholder.com/300x180?text=No+Image"

def clean_summary(html_text):
    text = BeautifulSoup(html_text, "html.parser").get_text()
    return text[:120] + "..." if len(text) > 120 else text

all_entries = []
for f in selected_urls:
    d = feedparser.parse(f["url"])
    for entry in d.entries[:10]:
        entry['source_name'] = f["name"]
        entry['thumbnail'] = get_thumbnail(entry)
        all_entries.append(entry)

# Sort by date
all_entries.sort(key=lambda x: x.get('published_parsed', datetime.now().timetuple()), reverse=True)

# --- 5. Main UI Content ---
st.markdown('<div class="main-title">🚀 Next-Gen Experience Planning Sensing</div>', unsafe_allow_html=True)

if not st.session_state.api_key:
    st.warning("⚠️ 사이드바에서 Gemini API Key를 먼저 입력해주세요.")

# Section: Best Pick (Top 3)
st.subheader("🌟 Today's Best Pick")
best_cols = st.columns(3)
for i, entry in enumerate(all_entries[:3]):
    with best_cols[i]:
        st.markdown(f"""
        <div class="card">
            <div class="best-pick-label">BEST PICK {i+1}</div>
            <img src="{entry['thumbnail']}" class="thumbnail">
            <div class="card-title">{entry.title}</div>
            <div class="card-summary">{clean_summary(entry.get('summary', ''))}</div>
            <a href="{entry.link}" target="_blank" class="card-link">자세히 보기 ({entry['source_name']})</a>
        </div>
        """, unsafe_allow_html=True)
        if st.button(f"AI 전략 분석", key=f"best_{i}"):
            st.session_state.analysis_target = entry

st.divider()

# Section: Main Sensing Stream (Grid View)
st.subheader("📂 Sensing Stream")
cols = st.columns(3)
for i, entry in enumerate(all_entries[3:15]):
    with cols[i % 3]:
        st.markdown(f"""
        <div class="card">
            <img src="{entry['thumbnail']}" class="thumbnail">
            <div class="card-title">{entry.title}</div>
            <div class="card-summary">{clean_summary(entry.get('summary', ''))}</div>
            <a href="{entry.link}" target="_blank" class="card-link">원문 링크 ({entry['source_name']})</a>
        </div>
        """, unsafe_allow_html=True)
        if st.button(f"AI 전략 분석 수행", key=f"main_{i}"):
            st.session_state.analysis_target = entry

# --- 6. AI Analysis Sidebar/Popup Logic ---
if 'analysis_target' in st.session_state and st.session_state.api_key:
    target = st.session_state.analysis_target
    with st.sidebar:
        st.divider()
        st.subheader("🔍 Deep-dive Analysis")
        st.info(f"대상: {target.title}")
        
        with st.spinner("Analyzing..."):
            try:
                genai.configure(api_key=st.session_state.api_key)
                model = genai.GenerativeModel('models/gemini-1.5-flash')
                prompt = f"""
                당신은 차세대 경험 기획팀의 수석 전략가입니다. 아래 뉴스를 읽고 우리 팀의 NOD(New Opportunity Discovery) 프로젝트 관점에서 분석하세요.
                내용: {target.title} - {target.get('summary', '')}
                
                분석 요구사항:
                1. 핵심 기술/서비스 한줄 요약
                2. 이 시도가 기존 시장을 파괴하는 신기한 지점
                3. 우리 회사의 RTOS 워치나 포켓 컴퓨팅 디바이스 프로젝트에 적용할 구체적 아이디어 2가지
                """
                response = model.generate_content(prompt)
                st.write(response.text)
            except Exception as e:
                st.error(f"분석 중 오류 발생: {e}")
        
        if st.button("분석창 닫기"):
            del st.session_state.analysis_target
            st.rerun()
