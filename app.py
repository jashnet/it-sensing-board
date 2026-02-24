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
from concurrent.futures import ThreadPoolExecutor

# --- 1. 초기 채널 데이터 ---
def get_initial_channels():
    return {
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

# --- 2. 설정 로직 ---
def get_user_file(user_id):
    return f"nod_samsung_user_{user_id}.json"

def load_user_settings(user_id):
    filename = get_user_file(user_id)
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "api_key": "AIzaSyBpko5khWacamTzhI6lsA70LyjCCNf06aA", # 요청하신 키로 변경
        "sensing_period": 7,
        "max_articles": 30,
        "filter_strength": 3,
        "filter_prompt": "혁신적 인터페이스, 파괴적 AI 기능, 스타트업의 신규 디바이스 시도에 해당하는 뉴스 위주.",
        "ai_prompt": "삼성전자(Samsung) 기획자 관점에서 3단계 분석을 수행하라:\na) Fact Summary: 핵심 요약\nb) 3-Year Future Impact: 에코시스템 변화\nc) Samsung Takeaway: 혁신 시사점",
        "category_active": {"Global Innovation (23)": True, "China AI/HW (11)": True, "Japan Innovation (11)": True},
        "channels": get_initial_channels()
    }

def save_user_settings(user_id, settings):
    with open(get_user_file(user_id), "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

# --- 3. 모델 및 팝업 기능 ---
def get_ai_model(api_key):
    if not api_key: return None
    try:
        genai.configure(api_key=api_key.strip())
        return genai.GenerativeModel('gemini-1.5-flash')
    except: return None

@st.dialog("🔍 Deep-dive Analysis")
def show_analysis_popup(item, prompt, api_key):
    model = get_ai_model(api_key)
    if model:
        with st.spinner("Samsung Strategy AI 분석 중..."):
            try:
                res = model.generate_content(f"{prompt}\n\n제목: {item['title_en']}")
                st.markdown(f"### {item['title_ko']}")
                st.info(res.text)
                st.markdown(f"[원본 기사 읽기]({item['link']})")
            except Exception as e:
                st.error(f"분석 실패: {e}")
    else:
        st.error("유효한 API Key가 없습니다.")
    if st.button("닫기"):
        st.rerun()

@st.cache_data(ttl=3600)
def safe_translate(text):
    if not text: return ""
    try: return GoogleTranslator(source='auto', target='ko').translate(text)
    except: return text

# --- 4. 데이터 엔진 ---
def fetch_single_feed(args):
    cat, f, limit = args
    socket.setdefaulttimeout(15)
    articles = []
    try:
        d = feedparser.parse(f["url"])
        for entry in d.entries[:10]:
            dt = entry.get('published_parsed') or entry.get('updated_parsed')
            if dt:
                p_date = datetime.fromtimestamp(time.mktime(dt))
                if p_date < limit: continue
                # 요약 추출
                raw_sum = entry.get("summary", "")
                summary = BeautifulSoup(raw_sum, "html.parser").get_text()[:150] if raw_sum else "No summary available."
                
                articles.append({
                    "id": hashlib.md5(entry.link.encode()).hexdigest()[:12],
                    "title_en": entry.title,
                    "title_ko": safe_translate(entry.title),
                    "summary": safe_translate(summary),
                    "link": entry.link,
                    "source": f["name"],
                    "category": cat,
                    "date_obj": p_date,
                    "date": p_date.strftime("%Y.%m.%d")
                })
    except: pass
    return articles

@st.cache_data(ttl=3600)
def get_all_news(settings):
    limit = datetime.now() - timedelta(days=settings["sensing_period"])
    active_tasks = [(cat, f, limit) for cat, feeds in settings["channels"].items() 
                    if settings["category_active"].get(cat, True) for f in feeds if f["active"]]
    if not active_tasks: return []
    with ThreadPoolExecutor(max_workers=15) as executor:
        results = list(executor.map(fetch_single_feed, active_tasks))
    return [item for sublist in results for item in sublist]

# --- 5. UI 설정 및 사이드바 ---
st.set_page_config(page_title="NGEPT Strategy Hub", layout="wide")

# Modern CSS (Instagram + Tech Style)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .main-header { padding: 60px 0; background: linear-gradient(135deg, #034EA2 0%, #007AFF 100%); border-radius: 0 0 50px 50px; color: white; text-align: center; margin-bottom: 40px; box-shadow: 0 15px 35px rgba(0,122,255,0.2); }
    .main-header h1 { font-size: 3rem; font-weight: 800; letter-spacing: -1px; }
    .insta-card { background: white; border-radius: 24px; border: 1px solid #efefef; margin-bottom: 30px; overflow: hidden; box-shadow: 0 10px 20px rgba(0,0,0,0.02); transition: transform 0.3s ease; }
    .insta-card:hover { transform: translateY(-5px); box-shadow: 0 20px 40px rgba(0,0,0,0.08); }
    .card-header { padding: 15px 20px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #fafafa; }
    .source-badge { background: #f0f2f6; color: #034EA2; padding: 4px 12px; border-radius: 100px; font-size: 0.75rem; font-weight: 700; }
    .date-text { color: #8e8e93; font-size: 0.75rem; }
    .card-img { width: 100%; height: 280px; object-fit: cover; }
    .card-content { padding: 20px; }
    .card-title-ko { font-size: 1.2rem; font-weight: 700; color: #1a1a1a; margin-bottom: 8px; line-height: 1.3; }
    .card-title-en { font-size: 0.85rem; color: #8e8e93; font-style: italic; margin-bottom: 15px; display: block; }
    .card-summary { font-size: 0.9rem; color: #4b4b4b; line-height: 1.6; margin-bottom: 20px; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.title("👤 Strategy Profile")
    u_id = st.radio("사용자 선택", ["1", "2", "3", "4"], horizontal=True)
    if "current_user" not in st.session_state or st.session_state.current_user != u_id:
        st.session_state.current_user = u_id
        st.session_state.settings = load_user_settings(u_id)
        st.rerun()

    st.divider()
    st.session_state.settings["api_key"] = st.text_input("Gemini API Key", value=st.session_state.settings["api_key"], type="password")
    
    edit_mode = st.toggle("🛠️ 채널/설정 편집 모드")
    if edit_mode:
        with st.expander("⚙️ 고급 파라미터"):
            st.session_state.settings["sensing_period"] = st.slider("기간", 1, 30, st.session_state.settings["sensing_period"])
            st.session_state.settings["max_articles"] = st.selectbox("기사 수", [10, 20, 30, 50, 100], index=2)
            st.session_state.settings["ai_prompt"] = st.text_area("분석 프롬프트", value=st.session_state.settings["ai_prompt"], height=150)
        
        for cat in list(st.session_state.settings["channels"].keys()):
            st.session_state.settings["category_active"][cat] = st.toggle(cat, value=st.session_state.settings["category_active"].get(cat, True))
            if st.session_state.settings["category_active"][cat]:
                with st.expander(f"📌 {cat} 관리"):
                    for idx, f in enumerate(st.session_state.settings["channels"][cat]):
                        c1, c2 = st.columns([4, 1])
                        f["active"] = c1.checkbox(f["name"], value=f.get("active", True), key=f"cb_{u_id}_{cat}_{idx}")
                        if c2.button("❌", key=f"del_{u_id}_{cat}_{idx}"):
                            st.session_state.settings["channels"][cat].pop(idx)
                            save_user_settings(u_id, st.session_state.settings); st.rerun()

    if st.button("🚀 Apply & Sensing", use_container_width=True, type="primary"):
        save_user_settings(u_id, st.session_state.settings)
        st.cache_data.clear(); st.rerun()

# --- 6. 메인 화면 렌더링 ---
st.markdown("""<div class="main-header"><h1>NGEPT Strategic Hub</h1><p>Future Sensing & Experience Discovery</p></div>""", unsafe_allow_html=True)

raw_data = get_all_news(st.session_state.settings)

if raw_data:
    # --- 상단 Top Picks (3컬럼 인스타그램 스타일) ---
    st.subheader("🌟 Strategic Top Picks")
    top_6 = raw_data[:6]
    cols = st.columns(3)
    for i, item in enumerate(top_6):
        with cols[i % 3]:
            st.markdown(f"""
            <div class="insta-card">
                <div class="card-header">
                    <span class="source-badge">{item['source']}</span>
                    <span class="date-text">{item['date']}</span>
                </div>
                <img src="https://s.wordpress.com/mshots/v1/{item['link']}?w=500" class="card-img">
                <div class="card-content">
                    <div class="card-title-ko">{item['title_ko']}</div>
                    <span class="card-title-en">{item['title_en']}</span>
                    <div class="card-summary">{item['summary']}...</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("🔍 Deep Analysis", key=f"pop_{item['id']}", use_container_width=True):
                show_analysis_popup(item, st.session_state.settings["ai_prompt"], st.session_state.settings["api_key"])

    st.divider()
    
    # --- 실시간 스트림 (필터 및 소팅) ---
    st.subheader("📋 Real-time Sensing Stream")
    c1, c2, c3 = st.columns([2, 2, 2])
    with c1: sort_val = st.selectbox("📅 정렬", ["최신순", "과거순", "가나다순"])
    with c2: cat_filter = st.multiselect("📂 카테고리", list(st.session_state.settings["channels"].keys()), default=list(st.session_state.settings["channels"].keys()))
    with c3: search_key = st.text_input("🔍 검색어", "")

    # 데이터 가공
    stream_data = [d for d in raw_data if d["category"] in cat_filter]
    if search_key: stream_data = [d for d in stream_data if search_key.lower() in d["title_ko"].lower() or search_key.lower() in d["title_en"].lower()]
    
    if sort_val == "최신순": stream_data.sort(key=lambda x: x["date_obj"], reverse=True)
    elif sort_val == "과거순": stream_data.sort(key=lambda x: x["date_obj"])
    else: stream_data.sort(key=lambda x: x["title_ko"])

    for item in stream_data[:st.session_state.settings["max_articles"]]:
        with st.container():
            col_img, col_txt = st.columns([1, 3])
            with col_img:
                st.image(f"https://s.wordpress.com/mshots/v1/{item['link']}?w=300", use_container_width=True)
            with col_txt:
                st.markdown(f"**[{item['source']}]** {item['date']}")
                st.markdown(f"### {item['title_ko']}")
                st.caption(item['title_en'])
                st.write(item['summary'] + "...")
                if st.button("Quick View", key=f"q_{item['id']}"):
                    show_analysis_popup(item, st.session_state.settings["ai_prompt"], st.session_state.settings["api_key"])
            st.markdown("---")
else:
    st.info("조건에 맞는 데이터가 없습니다. 사이드바 설정을 확인하세요.")
