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
import hashlib
import socket

# --- 1. 설정 및 기본값 ---
SETTINGS_FILE = "nod_samsung_pro_v8.json"
DEFAULT_API_KEY = "AIzaSyCW7kwkCqCSN-usKFG9gwcPzYlHwtQW_DQ"

def default_settings():
    return {
        "api_key": DEFAULT_API_KEY,
        "slack_webhook": "",
        "sensing_period": 7,
        "max_articles": 30,
        "filter_strength": 3,
        "additional_filter": "",
        "filter_prompt": "혁신적 인터페이스, 파괴적 AI 기능, 스타트업의 신규 디바이스 시도에 해당하는 뉴스 위주.",
        "ai_prompt": """Samsung 기획자 관점 분석:
        a) Fact Summary: 핵심 내용 요약.
        b) 3-Year Future Impact: 에코시스템 변화 예측.
        c) Samsung Takeaway: 제품 혁신 제언.""",
        "category_active": {"Global Innovation (23)": True, "China AI/HW (11)": True, "Japan Innovation (11)": True},
        "channels": {
            "Global Innovation (23)": [{"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "active": True}, {"name": "Wired", "url": "https://www.wired.com/feed/rss", "active": True}],
            "China AI/HW (11)": [{"name": "36Kr (CN)", "url": "https://36kr.com/feed", "active": True}],
            "Japan Innovation (11)": [{"name": "The Bridge JP", "url": "https://thebridge.jp/feed", "active": True}]
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

# --- 2. 유틸리티 함수 ---
def natural_translate(text):
    if not text: return ""
    try: return GoogleTranslator(source='auto', target='ko').translate(text)
    except: return text

def get_rescue_thumbnail(entry):
    link = entry.get('link')
    if 'media_content' in entry: return entry.media_content[0]['url']
    if link:
        try:
            res = requests.get(link, timeout=1.0)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                og_img = soup.find("meta", property="og:image")
                if og_img: return og_img["content"]
        except: pass
    return f"https://s.wordpress.com/mshots/v1/{link}?w=600" if link else "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=600&q=80"

def get_ai_model():
    try:
        genai.configure(api_key=st.session_state.settings["api_key"])
        available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        target = next((m for m in available if "1.5-flash" in m), available[0])
        return genai.GenerativeModel(target)
    except: return None

# --- 3. 데이터 엔진 (진행률 표시 및 에러 핸들링) ---
def fetch_sensing_data(settings):
    all_news = []
    limit = datetime.now() - timedelta(days=settings["sensing_period"])
    model = get_ai_model()
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    socket.setdefaulttimeout(10)

    active_feeds = []
    for cat, feeds in settings["channels"].items():
        if settings["category_active"].get(cat, True):
            for f in feeds:
                if f["active"]: active_feeds.append((cat, f))
    
    if not active_feeds: return []
    
    p_bar = st.progress(0)
    status_text = st.empty()
    processed = 0

    for cat, f in active_feeds:
        processed += 1
        percent = int((processed / len(active_feeds)) * 100)
        status_text.caption(f"📡 {cat} - {f['name']} 센싱 중... ({percent}%)")
        p_bar.progress(processed / len(active_feeds))
        
        try:
            d = feedparser.parse(f["url"], agent=USER_AGENT)
            for entry in d.entries[:10]:
                try:
                    p_date = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    if p_date < limit: continue
                    
                    relevance_score = 5
                    if model:
                        filter_query = f"[제목] {entry.title}\n{settings['filter_prompt']}\n관련성 1-10 점수 포함 'True/False,점수' 형식 답해."
                        res = model.generate_content(filter_query).text.strip()
                        if "true" not in res.lower(): continue
                        try: relevance_score = int(res.split(",")[-1])
                        except: relevance_score = 5

                    all_news.append({
                        "id": hashlib.md5(entry.link.encode()).hexdigest()[:12],
                        "title_en": entry.title,
                        "title_ko": natural_translate(entry.title),
                        "summary_ko": natural_translate(BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:300]),
                        "img": get_rescue_thumbnail(entry),
                        "source": f["name"], "category": cat,
                        "date_obj": p_date, "date": p_date.strftime("%Y.%m.%d"), "link": entry.link,
                        "score": relevance_score
                    })
                except: continue
        except: continue
    
    status_text.empty()
    p_bar.empty()
    all_news.sort(key=lambda x: x['date_obj'], reverse=True)
    return all_news

# --- 4. UI 스타일 (Modern Glassmorphism & Samsung One) ---
st.set_page_config(page_title="NOD Strategy Hub", layout="wide")
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700&family=Noto+Sans+KR:wght@300;400;700&display=swap');
    body { font-family: 'Noto Sans KR', sans-serif; background-color: #f8f9fc; color: #1d1d1f; }
    
    /* 헤더 스타일링 */
    .header-container { padding: 40px 0; text-align: center; background: linear-gradient(135deg, #034EA2 0%, #007AFF 100%); border-radius: 0 0 40px 40px; color: white; margin-bottom: 40px; box-shadow: 0 10px 30px rgba(3, 78, 162, 0.2); }
    .header-title { font-size: 2.5rem; font-weight: 700; margin-bottom: 10px; letter-spacing: -1px; }
    
    /* 카드 디자인 */
    .modern-card { background: white; padding: 25px; border-radius: 28px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); border: 1px solid #edf2f7; height: 100%; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
    .modern-card:hover { transform: translateY(-8px); box-shadow: 0 20px 40px rgba(0,0,0,0.08); border-color: #034EA2; }
    
    .card-thumb { width: 100%; height: 200px; object-fit: cover; border-radius: 20px; margin-bottom: 18px; }
    .card-badge { background: #f0f4ff; color: #034EA2; padding: 4px 12px; border-radius: 100px; font-size: 0.7rem; font-weight: 700; display: inline-block; margin-bottom: 12px; text-transform: uppercase; }
    
    .card-title-ko { font-size: 1.15rem; font-weight: 700; line-height: 1.4; color: #1a1c1e; margin-bottom: 4px; }
    .card-title-en { font-size: 0.8rem; color: #8e8e93; font-style: italic; margin-bottom: 15px; display: block; }
    .card-summary { font-size: 0.9rem; color: #4a5568; line-height: 1.6; margin-bottom: 20px; }
    
    .link-btn { font-size: 0.8rem; font-weight: 700; color: #034EA2; text-decoration: none; display: inline-flex; align-items: center; gap: 4px; }
    .link-btn:hover { text-decoration: underline; }
</style>
""", unsafe_allow_html=True)

# --- 5. 사이드바 제어 ---
with st.sidebar:
    st.title("🛡️ NOD Controller")
    if "show_api" not in st.session_state: st.session_state.show_api = False
    if st.session_state.settings["api_key"] and not st.session_state.show_api:
        st.success("✅ AI 가동 중")
        if st.button("키 수정"): st.session_state.show_api = True; st.rerun()
    else:
        new_key = st.text_input("Gemini API Key", value=st.session_state.settings["api_key"], type="password")
        if st.button("저장"): st.session_state.settings["api_key"] = new_key; st.session_state.show_api = False; save_settings(st.session_state.settings); st.rerun()

    st.divider()
    st.subheader("🌐 채널 그룹")
    for cat in list(st.session_state.settings["channels"].keys()):
        st.session_state.settings["category_active"][cat] = st.toggle(cat, value=st.session_state.settings["category_active"].get(cat, True))
        if st.session_state.settings["category_active"][cat]:
            with st.expander(f"{cat} 채널"):
                for f in st.session_state.settings["channels"][cat]:
                    f["active"] = st.checkbox(f["name"], value=f["active"], key=f"side_{f['name']}")

    st.divider()
    with st.expander("⚙️ 고급 필터 및 프롬프트"):
        st.session_state.settings["filter_prompt"] = st.text_area("News Filter", value=st.session_state.settings["filter_prompt"])
        st.session_state.settings["additional_filter"] = st.text_area("Additional Keywords", value=st.session_state.settings.get("additional_filter", ""))
        st.session_state.settings["ai_prompt"] = st.text_area("AI Analysis Guide", value=st.session_state.settings.get("ai_prompt", ""))
        st.session_state.settings["filter_strength"] = st.slider("Filter Strength", 1, 5, st.session_state.settings["filter_strength"])
        st.session_state.settings["max_articles"] = st.selectbox("Max Articles", [10, 20, 30, 50], index=1)

    if st.button("🚀 Apply Settings & Sensing", use_container_width=True):
        save_settings(st.session_state.settings)
        if "news_data" in st.session_state: del st.session_state.news_data
        st.rerun()

# --- 6. 메인 렌더링 ---
st.markdown("""<div class="header-container"><div class="header-title">Samsung NOD Intelligence Hub</div><div>Next Opportunity Discovery & Future Experience Sensing</div></div>""", unsafe_allow_html=True)

if "news_data" not in st.session_state:
    st.session_state.news_data = fetch_sensing_data(st.session_state.settings)

raw_data = st.session_state.news_data

if raw_data:
    # 🌟 Top 6 Picks (정적 섹션)
    st.subheader("🌟 Strategic Top Picks")
    top_6 = raw_data[:6]
    rows = [top_6[i:i+3] for i in range(0, len(top_6), 3)]
    for row in rows:
        cols = st.columns(3)
        for j, item in enumerate(row):
            with cols[j]:
                st.markdown(f"""
                <div class="modern-card">
                    <div class="card-badge">{item['source']} | {item['date']}</div>
                    <img src="{item['img']}" class="card-thumb">
                    <div class="card-title-ko">{item['title_ko']}</div>
                    <span class="card-title-en">{item['title_en']}</span>
                    <div class="card-summary">{item['summary_ko']}...</div>
                    <a href="{item['link']}" target="_blank" class="link-btn">🔗 원본 기사 읽기</a>
                </div>
                """, unsafe_allow_html=True)
                if st.button("🔍 전략 Deep-dive", key=f"dd_{item['id']}"):
                    model = get_ai_model()
                    if model:
                        with st.spinner("Samsung 전략 분석 리포트 생성 중..."):
                            res = model.generate_content(f"{st.session_state.settings['ai_prompt']}\n내용: {item['title_en']}")
                            st.info(res.text)
                    else: st.error("API Key 확인 필요")

    st.markdown("<br><br>", unsafe_allow_html=True)
    st.divider()

    # 📋 Sensing Stream (필터/소팅 적용 섹션)
    st.subheader("📋 Sensing Stream")
    
    # 이 섹션에만 적용되는 컨트롤러
    with st.container():
        c1, c2, c3 = st.columns([2, 2, 2])
        with c1: sort_val = st.selectbox("📅 정렬", ["최신순", "과거순", "AI 관련도순"])
        with c2: cat_val = st.multiselect("📂 카테고리", list(st.session_state.settings["channels"].keys()), default=list(st.session_state.settings["channels"].keys()))
        with c3: search_val = st.text_input("🔍 스트림 내 검색", "")

    # 필터링/소팅 로직
    stream_data = [d for d in raw_data[6:] if d["category"] in cat_val]
    if search_val: stream_data = [d for d in stream_data if search_val.lower() in d["title_ko"].lower()]
    if sort_val == "최신순": stream_data.sort(key=lambda x: x["date_obj"], reverse=True)
    elif sort_val == "과거순": stream_data.sort(key=lambda x: x["date_obj"])
    else: stream_data.sort(key=lambda x: x["score"], reverse=True)

    # 리스트 출력
    for item in stream_data[:st.session_state.settings["max_articles"]]:
        with st.container():
            col_img, col_txt = st.columns([1, 4])
            with col_img: st.image(item['img'], use_container_width=True)
            with col_txt:
                st.markdown(f"""
                <div style="margin-bottom:10px;">
                    <div class="card-badge" style="margin-bottom:5px;">{item['category']} | {item['source']}</div>
                    <div class="card-title-ko" style="font-size:1.1rem;">{item['title_ko']}</div>
                    <span class="card-title-en">{item['title_en']}</span>
                    <p style="font-size:0.9rem; color:#4a5568;">{item['summary_ko']}...</p>
                    <a href="{item['link']}" target="_blank" class="link-btn">🔗 원본 보기</a>
                </div>
                """, unsafe_allow_html=True)
                if st.button("Quick Analysis", key=f"qa_{item['id']}"):
                    st.success(get_ai_model().generate_content(f"{st.session_state.settings['ai_prompt']}\n내용: {item['title_en']}").text)
            st.markdown("<hr style='border-top: 1px solid #edf2f7;'>", unsafe_allow_html=True)
else:
    st.info("조건에 맞는 혁신 뉴스가 없습니다. 사이드바에서 설정을 조정하고 Apply를 눌러보세요.")
