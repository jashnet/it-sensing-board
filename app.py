import streamlit as st
import feedparser
import google.generativeai as genai
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timedelta
import time
from deep_translator import GoogleTranslator
import requests

# --- 1. 설정 및 기본값 (API Key 및 프롬프트 최적화) ---
SETTINGS_FILE = "nod_samsung_settings.json"
DEFAULT_API_KEY = "AIzaSyCW7kwkCqCSN-usKFG9gwcPzYlHwtQW_DQ"

def default_settings():
    return {
        "api_key": DEFAULT_API_KEY,
        "slack_webhook": "",
        "sensing_period": 7,
        "filter_prompt": """당신은 글로벌 빅테크 기업의 차세대 경험기획 전문가입니다. 
        향후 2~3년 내의 미래 신규 제품, 혁신적 UX/UI, 새로운 인터페이스(HCI), 파괴적 AI 기능, 스타트업의 도전적 하드웨어 시도에 해당하는 뉴스만 'True'로 판별하세요. 
        단순한 기업 실적, 일반적인 앱 업데이트, 단순 주식 정보는 'False'로 배제하세요.""",
        "ai_prompt": """삼성전자(Samsung)의 차세대 제품 기획자 관점에서 다음 3가지를 분석하라:
        a) Fact Summary: 이 기사가 전달하는 핵심 사실을 정제하여 요약.
        b) Future Impact: 향후 3년 시점에 기존 스마트폰/웨어러블 에코시스템 및 사용자 행태에 가져올 변화 예측.
        c) Samsung Takeaway: 제조사로서 얻을 수 있는 전략적 시사점과 구체적인 경험 혁신 방향 제안.""",
        "channels": {
            "글로벌 (Tech/UX)": [
                {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "active": True},
                {"name": "Wired", "url": "https://www.wired.com/feed/rss", "active": True},
                {"name": "Yanko Design", "url": "https://www.yankodesign.com/feed/", "active": True},
                {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "active": True}
            ],
            "중국/일본 (Hardware)": [
                {"name": "36Kr (CN)", "url": "https://36kr.com/feed", "active": True},
                {"name": "Gizmochina", "url": "https://www.gizmochina.com/feed/", "active": True},
                {"name": "The Bridge (JP)", "url": "https://thebridge.jp/feed", "active": True}
            ]
        }
    }

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return default_settings()
    return default_settings()

def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

if "settings" not in st.session_state:
    st.session_state.settings = load_settings()

# --- 2. 강력한 이미지 복구 및 자연스러운 번역 로직 ---
def get_bulletproof_thumbnail(entry):
    # 1. RSS 표준 태그
    if 'media_content' in entry: return entry.media_content[0]['url']
    
    # 2. Open Graph 직접 크롤링 (The Verge 등 대응)
    link = entry.get('link')
    if link:
        try:
            res = requests.get(link, timeout=1.2)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                og_img = soup.find("meta", property="og:image")
                if og_img: return og_img["content"]
        except: pass

    # 3. 대체 이미지 (테크니컬한 플레이스홀더)
    return f"https://images.unsplash.com/photo-1550745165-9bc0b252726f?w=600&q=80" # 고품질 테크 이미지

def natural_translate(text):
    if not text: return ""
    try:
        return GoogleTranslator(source='auto', target='ko').translate(text)
    except: return text

# --- 3. UI 스타일 및 사이드바 ---
st.set_page_config(page_title="Samsung NOD Dashboard", layout="wide")
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Samsung+One:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Samsung One', sans-serif; background-color: #f0f2f6; }
    .top-pick-card { background: white; padding: 20px; border-radius: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.08); border-top: 5px solid #034EA2; height: 100%; }
    .list-item { background: white; padding: 15px; border-radius: 12px; margin-bottom: 10px; border-left: 4px solid #034EA2; display: flex; align-items: center; }
    .thumbnail { width: 100%; height: 200px; object-fit: cover; border-radius: 12px; margin-bottom: 15px; }
    .title-area { font-size: 1.1rem; font-weight: 700; color: #1c1e21; margin-bottom: 8px; line-height: 1.4; }
    .original-title { font-size: 0.8rem; color: #888; margin-bottom: 10px; font-style: italic; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.title("🛡️ Sensing Control")
    # API 키 수정 가능하도록 표시
    st.session_state.settings["api_key"] = st.text_input("Gemini API Key", value=st.session_state.settings["api_key"], type="password")
    
    st.divider()
    st.subheader("🌐 Channels")
    for cat, feeds in st.session_state.settings["channels"].items():
        with st.expander(cat):
            for f in feeds:
                f["active"] = st.checkbox(f["name"], value=f["active"], key=f"ch_{f['name']}")

    st.divider()
    with st.expander("⚙️ Advanced Prompts"):
        st.session_state.settings["filter_prompt"] = st.text_area("1. News Filter Prompt", value=st.session_state.settings["filter_prompt"], height=150)
        st.session_state.settings["ai_prompt"] = st.text_area("2. AI Analysis Prompt", value=st.session_state.settings["ai_prompt"], height=150)
        st.session_state.settings["sensing_period"] = st.slider("Period (Days)", 1, 30, st.session_state.settings["sensing_period"])
        if st.button("Save Settings"):
            save_settings(st.session_state.settings)
            st.toast("Settings Saved! 💾")

# --- 4. 데이터 수집 및 분석 엔진 ---
def get_ai_model():
    try:
        genai.configure(api_key=st.session_state.settings["api_key"])
        return genai.GenerativeModel('gemini-1.5-flash-latest')
    except: return None

@st.cache_data(ttl=3600)
def fetch_sensing_data():
    all_news = []
    limit = datetime.now() - timedelta(days=st.session_state.settings["sensing_period"])
    model = get_ai_model()

    for cat, feeds in st.session_state.settings["channels"].items():
        for f in feeds:
            if not f["active"]: continue
            d = feedparser.parse(f["url"])
            for entry in d.entries[:10]:
                try:
                    p_date = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    if p_date < limit: continue
                    
                    # AI 필터링 (필터 프롬프트 적용)
                    if model:
                        check = model.generate_content(f"기준: {st.session_state.settings['filter_prompt']}\n제목: {entry.title}\n부합하면 'True', 아니면 'False'만 답해.")
                        if "true" not in check.text.lower(): continue

                    all_news.append({
                        "title_orig": entry.title,
                        "title_ko": natural_translate(entry.title),
                        "summary": natural_translate(BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:300]),
                        "img": get_bulletproof_thumbnail(entry),
                        "source": f["name"],
                        "date": p_date.strftime("%m/%d"),
                        "link": entry.link
                    })
                except: continue
    all_news.sort(key=lambda x: x['date'], reverse=True)
    return all_news

# --- 5. 대시보드 메인 화면 ---
st.title("🚀 Samsung NOD: Future Experience Hub")
news_data = fetch_sensing_data()

if news_data:
    # Top Pick 6 (Grid 3x2)
    st.subheader("🌟 Top 6 Strategic Picks")
    top_picks = news_data[:6]
    rows = [top_picks[i:i + 3] for i in range(0, len(top_picks), 3)]
    for row in rows:
        cols = st.columns(3)
        for j, item in enumerate(row):
            with cols[j]:
                st.markdown(f"""
                <div class="top-pick-card">
                    <img src="{item['img']}" class="thumbnail">
                    <div class="title-area">{item['title_ko']}</div>
                    <div class="original-title">{item['title_orig']}</div>
                    <div style="font-size:0.85rem; color:#555; margin-bottom:15px;">{item['summary'][:150]}...</div>
                </div>
                """, unsafe_allow_html=True)
                if st.button("🔍 Deep-dive Analysis", key=f"top_{item['link'][-15:]}"):
                    model = get_ai_model()
                    if model:
                        with st.spinner("Samsung 전략 분석 중..."):
                            res = model.generate_content(f"{st.session_state.settings['ai_prompt']}\n\n내용: {item['title_orig']} - {item['summary']}")
                            st.info(res.text)
                    else: st.error("API Key를 확인해주세요.")

    st.divider()

    # 전체 리스트 (Stream View)
    st.subheader("📋 Full Sensing Stream")
    for item in news_data[6:]:
        with st.container():
            col_img, col_txt = st.columns([1, 4])
            with col_img:
                st.image(item['img'], use_container_width=True)
            with col_txt:
                st.markdown(f"**[{item['source']}] {item['title_ko']}**")
                st.caption(item['title_orig'])
                st.write(f"{item['summary'][:200]}...")
                if st.button("Quick Analysis", key=f"list_{item['link'][-15:]}"):
                    model = get_ai_model()
                    if model:
                        res = model.generate_content(f"{st.session_state.settings['ai_prompt']}\n\n내용: {item['title_orig']} - {item['summary']}")
                        st.success(res.text)
            st.markdown("---")
else:
    st.info("현재 조건에 맞는 전략적 뉴스가 없습니다. 채널이나 기간 설정을 확인해 보세요.")
