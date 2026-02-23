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

# --- 1. 설정 및 기본값 (v8 기반 유지) ---
SETTINGS_FILE = "nod_samsung_pro_v8.json"
DEFAULT_API_KEY = "AIzaSyCW7kwkCqCSN-usKFG9gwcPzYlHwtQW_DQ"

def default_settings():
    return {
        "api_key": DEFAULT_API_KEY,
        "slack_webhook": "",
        "sensing_period": 7, # 기본 수집 기간
        "max_articles": 30,
        "filter_strength": 3,
        "additional_filter": "",
        "filter_prompt": "혁신적 인터페이스, 파괴적 AI 기능, 스타트업의 신규 디바이스 시도에 해당하는 뉴스 위주.",
        "ai_prompt": """삼성전자(Samsung) 기획자 관점에서 3단계 분석을 수행하라:
        a) Fact Summary: 핵심 사실 요약 (한국어로 자연스럽게)
        b) 3-Year Future Impact: 향후 3년 내 에코시스템 변화 예측
        c) Samsung Takeaway: 삼성 제품 혁신을 위한 시사점""",
        "category_active": {"Global Innovation (23)": True, "China AI/HW (11)": True, "Japan Innovation (11)": True},
        "channels": {
            "Global Innovation (23)": [
                {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "active": True},
                {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "active": True},
                {"name": "Wired", "url": "https://www.wired.com/feed/rss", "active": True},
                {"name": "Engadget", "url": "https://www.engadget.com/rss.xml", "active": True},
                {"name": "Gizmodo", "url": "https://gizmodo.com/rss", "active": True},
                {"name": "Product Hunt", "url": "https://www.producthunt.com/feed", "active": True},
                {"name": "Yanko Design", "url": "https://www.yankodesign.com/feed/", "active": True},
                {"name": "Fast Company Design", "url": "https://www.fastcompany.com/design/rss", "active": True},
                {"name": "IEEE Spectrum", "url": "https://spectrum.ieee.org/rss/fulltext", "active": True},
                {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/", "active": True},
                {"name": "9to5Google", "url": "https://9to5google.com/feed/", "active": True},
                {"name": "9to5Mac", "url": "https://9to5mac.com/feed/", "active": True},
                {"name": "Android Authority", "url": "https://www.androidauthority.com/feed/", "active": True},
                {"name": "MacRumors", "url": "https://feeds.macrumors.com/MacRumors-All", "active": True},
                {"name": "Android Central", "url": "https://www.androidcentral.com/feed", "active": True},
                {"name": "SlashGear", "url": "https://www.slashgear.com/feed/", "active": True},
                {"name": "Digital Trends", "url": "https://www.digitaltrends.com/feed/", "active": True},
                {"name": "VentureBeat", "url": "https://venturebeat.com/feed/", "active": True},
                {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "active": True},
                {"name": "Mashable", "url": "https://mashable.com/feeds/rss/all", "active": True},
                {"name": "The Next Web", "url": "https://thenextweb.com/feed", "active": True},
                {"name": "ReadWrite", "url": "https://readwrite.com/feed/", "active": True},
                {"name": "ZDNet", "url": "https://www.zdnet.com/news/rss.xml", "active": True}
            ],
            "China AI/HW (11)": [
                {"name": "36Kr (CN)", "url": "https://36kr.com/feed", "active": True},
                {"name": "TechNode", "url": "https://technode.com/feed/", "active": True},
                {"name": "Gizmochina", "url": "https://www.gizmochina.com/feed/", "active": True},
                {"name": "SCMP Tech", "url": "https://www.scmp.com/rss/318206/feed.xml", "active": True},
                {"name": "Pandaily", "url": "https://pandaily.com/feed/", "active": True},
                {"name": "KrASIA", "url": "https://kr-asia.com/feed", "active": True},
                {"name": "Huxiu (虎嗅)", "url": "https://www.huxiu.com/rss/0.xml", "active": True},
                {"name": "CnBeta", "url": "https://www.cnbeta.com.tw/backend.php", "active": True},
                {"name": "IT Home", "url": "https://www.ithome.com/rss/", "active": True},
                {"name": "Sina Tech", "url": "https://tech.sina.com.cn/rss/all.xml", "active": True},
                {"name": "Leiphone", "url": "https://www.leiphone.com/feed", "active": True}
            ],
            "Japan Innovation (11)": [
                {"name": "The Bridge JP", "url": "https://thebridge.jp/feed", "active": True},
                {"name": "ITmedia News", "url": "https://rss.itmedia.co.jp/rss/2.0/news_bursts.xml", "active": True},
                {"name": "Gizmodo JP", "url": "https://www.gizmodo.jp/index.xml", "active": True},
                {"name": "CNET Japan", "url": "https://japan.cnet.com/rss/index.rdf", "active": True},
                {"name": "Nikkei Asia Tech", "url": "https://asia.nikkei.com/rss/feed/nar", "active": True},
                {"name": "ASCII.jp", "url": "https://ascii.jp/rss.xml", "active": True},
                {"name": "PC Watch", "url": "https://pc.watch.impress.co.jp/data/rss/1.0/pcw/feed.rdf", "active": True},
                {"name": "Impress Watch", "url": "https://www.watch.impress.co.jp/data/rss/1.0/ipw/feed.rdf", "active": True},
                {"name": "Mynavi Tech", "url": "https://news.mynavi.jp/rss/digital/it/", "active": True},
                {"name": "Techable JP", "url": "https://techable.jp/feed", "active": True},
                {"name": "Yahoo JP Tech", "url": "https://news.yahoo.co.jp/rss/categories/it.xml", "active": True}
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

# [수정] 모델 호출 로직을 직접 지정하여 안정성 강화 (Deep-dive 에러 해결)
def get_ai_model():
    api_key = st.session_state.settings.get("api_key", "").strip()
    if not api_key: return None
    try:
        genai.configure(api_key=api_key)
        return genai.GenerativeModel('gemini-1.5-flash')
    except: return None

# --- 3. 데이터 엔진 (진행률 및 에러 방어) ---
def fetch_sensing_data(settings):
    all_news = []
    limit = datetime.now() - timedelta(days=settings["sensing_period"])
    model = get_ai_model()
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
    socket.setdefaulttimeout(15)

    active_feeds = []
    for cat, feeds in settings["channels"].items():
        if settings["category_active"].get(cat, True):
            for f in feeds:
                if f["active"]: active_feeds.append((cat, f))
    
    if not active_feeds: return []

    progress_bar = st.progress(0)
    status_text = st.empty()
    processed_count = 0

    for cat, f in active_feeds:
        processed_count += 1
        percent = int((processed_count / len(active_feeds)) * 100)
        status_text.caption(f"📡 {cat} - {f['name']} 센싱 중... ({percent}%)")
        progress_bar.progress(processed_count / len(active_feeds))
        
        try:
            d = feedparser.parse(f["url"], agent=USER_AGENT)
            for entry in d.entries[:8]:
                try:
                    p_date = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    if p_date < limit: continue
                    
                    relevance_score = 5
                    if model:
                        filter_query = f"[제목] {entry.title}\n기준: {settings['filter_prompt']}\n추가 필터: {settings['additional_filter']}\nTrue/False,점수(1-10) 형식 답해."
                        res = model.generate_content(filter_query).text.strip()
                        if "true" not in res.lower(): continue
                        try: relevance_score = int(res.split(",")[-1])
                        except: relevance_score = 5

                    all_news.append({
                        "id": hashlib.md5(entry.link.encode()).hexdigest()[:12],
                        "title_en": entry.title,
                        "title_ko": natural_translate(entry.title),
                        "summary_ko": natural_translate(BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:250]),
                        "img": get_rescue_thumbnail(entry),
                        "source": f["name"], "category": cat,
                        "date_obj": p_date, "date": p_date.strftime("%Y.%m.%d"), "link": entry.link,
                        "score": relevance_score
                    })
                except: continue
        except: continue
    
    status_text.empty()
    progress_bar.empty()
    all_news.sort(key=lambda x: x['date_obj'], reverse=True)
    return all_news

# --- 4. 모던 UI 스타일 ---
st.set_page_config(page_title="Samsung NOD Center v8.2", layout="wide")
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700&family=Noto+Sans+KR:wght@300;400;700&display=swap');
    body { font-family: 'Noto Sans KR', sans-serif; background-color: #f8f9fc; color: #1d1d1f; }
    .header-container { padding: 40px 0; text-align: center; background: linear-gradient(135deg, #034EA2 0%, #007AFF 100%); border-radius: 0 0 40px 40px; color: white; margin-bottom: 40px; box-shadow: 0 10px 30px rgba(3, 78, 162, 0.2); }
    .header-title { font-size: 2.3rem; font-weight: 700; margin-bottom: 5px; }
    .modern-card { background: white; padding: 25px; border-radius: 28px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); border: 1px solid #edf2f7; height: 100%; display: flex; flex-direction: column; transition: all 0.3s ease; }
    .modern-card:hover { transform: translateY(-8px); box-shadow: 0 20px 40px rgba(0,0,0,0.08); border-color: #034EA2; }
    .card-thumb { width: 100%; height: 200px; object-fit: cover; border-radius: 20px; margin-bottom: 18px; background-color: #f0f0f0; }
    .card-badge { background: #eef2ff; color: #034EA2; padding: 4px 12px; border-radius: 100px; font-size: 0.7rem; font-weight: 700; display: inline-block; margin-bottom: 12px; }
    .card-title-ko { font-size: 1.1rem; font-weight: 700; color: #1a1c1e; line-height: 1.4; margin-bottom: 4px; }
    .card-title-en { font-size: 0.8rem; color: #8e8e93; font-style: italic; margin-bottom: 12px; display: block; }
    .card-summary { font-size: 0.85rem; color: #4a5568; line-height: 1.6; flex-grow: 1; margin-bottom: 15px; }
    .link-btn { font-size: 0.8rem; font-weight: 700; color: #034EA2; text-decoration: none; }
</style>
""", unsafe_allow_html=True)

# --- 5. 사이드바 제어 ---
with st.sidebar:
    st.title("🛡️ NOD Controller")
    if "show_api" not in st.session_state: st.session_state.show_api = False
    
    current_api = st.session_state.settings.get("api_key", DEFAULT_API_KEY)
    if current_api and not st.session_state.show_api:
        st.success("✅ AI 가동 중")
        if st.button("키 수정"): st.session_state.show_api = True; st.rerun()
    else:
        new_key = st.text_input("Gemini API Key", value=current_api, type="password")
        if st.button("저장 및 적용"):
            st.session_state.settings["api_key"] = new_key; st.session_state.show_api = False; save_settings(st.session_state.settings); st.rerun()

    st.divider()
    st.subheader("🌐 채널 그룹")
    for cat in list(st.session_state.settings["channels"].keys()):
        st.session_state.settings["category_active"][cat] = st.toggle(cat, value=st.session_state.settings["category_active"].get(cat, True))
        if st.session_state.settings["category_active"][cat]:
            with st.expander(f"{cat} 채널"):
                for f in st.session_state.settings["channels"][cat]:
                    f["active"] = st.checkbox(f["name"], value=f["active"], key=f"side_{f['name']}")

    st.divider()
    with st.expander("⚙️ 고급 설정", expanded=True):
        # [수정] 수집 날짜 조절 슬라이더 추가 (1-30일)
        st.session_state.settings["sensing_period"] = st.slider("수집 날짜 범위 (최근 N일)", 1, 30, st.session_state.settings.get("sensing_period", 7))
        st.session_state.settings["filter_prompt"] = st.text_area("News Filter", value=st.session_state.settings["filter_prompt"])
        st.session_state.settings["additional_filter"] = st.text_area("Additional Filter", value=st.session_state.settings.get("additional_filter", ""))
        st.session_state.settings["ai_prompt"] = st.text_area("AI 전략 분석 가이드", value=st.session_state.settings.get("ai_prompt", ""))
        st.session_state.settings["filter_strength"] = st.slider("Filter 강도", 1, 5, st.session_state.settings["filter_strength"])
        st.session_state.settings["max_articles"] = st.selectbox("기사 개수", [10, 20, 30, 50], index=1)

    if st.button("🚀 Apply & Sensing Start", use_container_width=True):
        save_settings(st.session_state.settings)
        if "news_data" in st.session_state: del st.session_state.news_data
        st.rerun()

# --- 6. 메인 렌더링 ---
st.markdown("""<div class="header-container"><div class="header-title">NGEPT NOD Sensing Dashboard</div><div>Future Experience Sensing & Opportunity Discovery</div></div>""", unsafe_allow_html=True)

if "news_data" not in st.session_state:
    st.session_state.news_data = fetch_sensing_data(st.session_state.settings)

raw_data = st.session_state.news_data

if raw_data:
    # 🌟 Top Picks Section (고정 6개)
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
                if st.button("🔍 Deep-dive", key=f"dd_{item['id']}"):
                    model = get_ai_model()
                    if model:
                        with st.spinner("Samsung 전략 분석 중..."):
                            try:
                                res = model.generate_content(f"{st.session_state.settings['ai_prompt']}\n내용: {item['title_en']}")
                                st.info(res.text)
                            except Exception as e: st.error(f"분석 오류: {e}")
                    else: st.error("API Key 확인 필요")

    st.markdown("<br><br>", unsafe_allow_html=True)
    st.divider()

    # 📋 Sensing Stream Section (필터/소팅 적용)
    st.subheader("📋 Sensing Stream")
    
    with st.container():
        c1, c2, c3 = st.columns([2, 2, 2])
        with c1: sort_val = st.selectbox("📅 정렬", ["최신순", "과거순", "AI 관련도순"])
        with c2: cat_val = st.multiselect("📂 카테고리", list(st.session_state.settings["channels"].keys()), default=list(st.session_state.settings["channels"].keys()))
        with c3: search_val = st.text_input("🔍 스트림 내 검색", "")

    stream_data = [d for d in raw_data[6:] if d["category"] in cat_val]
    if search_val: stream_data = [d for d in stream_data if search_val.lower() in d["title_ko"].lower()]
    if sort_val == "최신순": stream_data.sort(key=lambda x: x["date_obj"], reverse=True)
    elif sort_val == "과거순": stream_data.sort(key=lambda x: x["date_obj"])
    else: stream_data.sort(key=lambda x: x["score"], reverse=True)

    for item in stream_data[:st.session_state.settings["max_articles"]]:
        with st.container():
            col_img, col_txt = st.columns([1, 4])
            with col_img: st.image(item['img'], use_container_width=True)
            with col_txt:
                st.markdown(f"""
                <div style="margin-bottom:15px;">
                    <div class="card-badge" style="margin-bottom:5px;">{item['category']} | {item['source']}</div>
                    <div class="card-title-ko" style="font-size:1.1rem;">{item['title_ko']}</div>
                    <span class="card-title-en">{item['title_en']}</span>
                    <p style="font-size:0.9rem; color:#4a5568;">{item['summary_ko']}...</p>
                    <a href="{item['link']}" target="_blank" class="link-btn">🔗 원본 보기</a>
                </div>
                """, unsafe_allow_html=True)
                if st.button("Quick Analysis", key=f"qa_{item['id']}"):
                    model = get_ai_model()
                    if model: st.success(model.generate_content(f"{st.session_state.settings['ai_prompt']}\n내용: {item['title_en']}").text)
            st.markdown("<hr style='border-top: 1px solid #edf2f7;'>", unsafe_allow_html=True)
else:
    st.info("조건에 맞는 뉴스가 없습니다. 설정을 변경하고 Apply 버튼을 눌러보세요.")
