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
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 1. 초기 채널 데이터 (v11.3 Max Channels 유지) ---
def get_initial_channels():
    return {
        "Global Innovation (65)": [
            {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "active": True},
            {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "active": True},
            {"name": "Wired", "url": "https://www.wired.com/feed/rss", "active": True},
            {"name": "Engadget", "url": "https://www.engadget.com/rss.xml", "active": True},
            {"name": "9to5Google", "url": "https://9to5google.com/feed/", "active": True},
            {"name": "9to5Mac", "url": "https://9to5mac.com/feed/", "active": True},
            {"name": "MacRumors", "url": "https://feeds.macrumors.com/MacRumors-All", "active": True},
            {"name": "Android Authority", "url": "https://www.androidauthority.com/feed/", "active": True},
            {"name": "Gizmodo", "url": "https://gizmodo.com/rss", "active": True},
            {"name": "CNET", "url": "https://www.cnet.com/rss/news/", "active": True},
            {"name": "IEEE Spectrum", "url": "https://spectrum.ieee.org/rss/fulltext", "active": True},
            {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/", "active": True},
            {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "active": True},
            {"name": "VentureBeat", "url": "https://venturebeat.com/feed/", "active": True},
            {"name": "Mashable", "url": "https://mashable.com/feeds/rss/all", "active": True},
            {"name": "ZDNet", "url": "https://www.zdnet.com/news/rss.xml", "active": True},
            {"name": "Google News Tech", "url": "https://news.google.com/rss/search?q=technology&hl=en-US&gl=US&ceid=US:en", "active": True},
            {"name": "Bloomberg Tech", "url": "https://www.bloomberg.com/feeds/technology/index.rss", "active": True},
            {"name": "NYT Tech", "url": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml", "active": True},
            {"name": "WSJ Tech", "url": "https://feeds.a.dj.com/rss/RSSWSJTechnology.xml", "active": True},
            {"name": "The Information", "url": "https://www.theinformation.com/feed", "active": True}
        ],
        "China AI/HW (32)": [
            {"name": "36Kr (CN)", "url": "https://36kr.com/feed", "active": True},
            {"name": "TechNode", "url": "https://technode.com/feed/", "active": True},
            {"name": "Gizmochina", "url": "https://www.gizmochina.com/feed/", "active": True},
            {"name": "SCMP Tech", "url": "https://www.scmp.com/rss/318206/feed.xml", "active": True},
            {"name": "Pandaily", "url": "https://pandaily.com/feed/", "active": True},
            {"name": "Huxiu (虎嗅)", "url": "https://www.huxiu.com/rss/0.xml", "active": True},
            {"name": "IT Home", "url": "https://www.ithome.com/rss/", "active": True},
            {"name": "Sina Tech", "url": "https://tech.sina.com.cn/rss/all.xml", "active": True},
            {"name": "Leiphone", "url": "https://www.leiphone.com/feed", "active": True},
            {"name": "CnBeta", "url": "https://www.cnbeta.com.tw/backend.php", "active": True}
        ],
        "Japan Innovation (15)": [
            {"name": "The Bridge JP", "url": "https://thebridge.jp/feed", "active": True},
            {"name": "ITmedia News", "url": "https://rss.itmedia.co.jp/rss/2.0/news_bursts.xml", "active": True},
            {"name": "Gizmodo JP", "url": "https://www.gizmodo.jp/index.xml", "active": True},
            {"name": "Nikkei Asia", "url": "https://asia.nikkei.com/rss/feed/nar", "active": True},
            {"name": "ASCII.jp", "url": "https://ascii.jp/rss.xml", "active": True}
        ]
    }

# --- 2. 설정 로직 ---
def get_user_file(user_id): return f"nod_samsung_user_{user_id}.json"

def load_user_settings(user_id):
    fn = get_user_file(user_id)
    default_settings = {
        "api_key": "AIzaSyBpko5khWacamTzhI6lsA70LyjCCNf06aA",
        "sensing_period": 7, "max_articles": 30, "filter_strength": 3, "filter_weight": 70,
        "filter_prompt": "제조사별 차세대 디바이스, 혁신적 하드웨어 디자인 소식 위주.",
        "ai_prompt": "삼성전자 CX 기획자 관점에서 분석: 1.요약 2.영향 3.제언",
        "category_active": {"Global Innovation (65)": True, "China AI/HW (32)": True, "Japan Innovation (15)": True},
        "channels": get_initial_channels()
    }
    if os.path.exists(fn):
        with open(fn, "r", encoding="utf-8") as f:
            saved = json.load(f)
            for k, v in default_settings.items():
                if k not in saved: saved[k] = v
            return saved
    return default_settings

def save_user_settings(user_id, settings):
    with open(get_user_file(user_id), "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

# --- 3. 유틸리티 ---
def get_thumbnail(link):
    return f"https://s.wordpress.com/mshots/v1/{link}?w=600"

@st.cache_data(ttl=3600)
def safe_translate(text):
    if not text: return ""
    try: return GoogleTranslator(source='auto', target='ko').translate(text)
    except: return text

# --- 4. 데이터 수집 엔진 ---
def fetch_single_feed(args):
    cat, f, limit = args
    socket.setdefaulttimeout(12)
    articles = []
    try:
        d = feedparser.parse(f["url"])
        for entry in d.entries[:8]:
            dt = entry.get('published_parsed') or entry.get('updated_parsed')
            if dt:
                p_date = datetime.fromtimestamp(time.mktime(dt))
                if p_date < limit: continue
                raw_sum = entry.get("summary", "")
                clean_sum = BeautifulSoup(raw_sum, "html.parser").get_text()[:180]
                articles.append({
                    "id": hashlib.md5(entry.link.encode()).hexdigest()[:12],
                    "title_en": entry.title, "title_ko": safe_translate(entry.title),
                    "link": entry.link, "source": f["name"], "category": cat, "date_obj": p_date,
                    "date": p_date.strftime("%Y.%m.%d"),
                    "summary": safe_translate(clean_sum)
                })
    except: pass
    return articles

def get_all_news(settings):
    limit = datetime.now() - timedelta(days=settings["sensing_period"])
    active_tasks = [(cat, f, limit) for cat, feeds in settings["channels"].items() 
                    if settings["category_active"].get(cat, True) for f in feeds if f["active"]]
    if not active_tasks: return []
    all_news = []
    pb = st.progress(0)
    st_text = st.empty()
    total = len(active_tasks)
    with ThreadPoolExecutor(max_workers=25) as executor:
        futures = {executor.submit(fetch_single_feed, t): t for t in active_tasks}
        completed = 0
        for f in as_completed(futures):
            completed += 1
            all_news.extend(f.result())
            pb.progress(completed / total)
            st_text.caption(f"📡 {completed}/{total} 채널 데이터 센싱 중... ({int((completed/total)*100)}%)")
    st_text.empty()
    pb.empty()
    return sorted(all_news, key=lambda x: x['date_obj'], reverse=True)

# --- 5. 분석 팝업 ---
@st.dialog("🎯 Strategic Insight Deep-dive")
def show_analysis_popup(item, settings):
    genai.configure(api_key=settings["api_key"])
    model = genai.GenerativeModel('gemini-1.5-flash')
    with st.spinner("AI 분석 중..."):
        try:
            res = model.generate_content(f"{settings['ai_prompt']}\n\n제목: {item['title_en']}")
            st.markdown(f"### {item['title_ko']}")
            st.info(res.text)
        except Exception as e: st.error(f"분석 실패: {e}")
    if st.button("닫기"): st.rerun()

# --- 6. 화이트 인스타그램 UI 스타일링 ---
st.set_page_config(page_title="NGEPT Hub v11.4", layout="wide")

st.markdown("""
<style>
    body { background-color: #f8f9fa; }
    .main-header { padding: 50px 0; background: linear-gradient(135deg, #034EA2 0%, #007AFF 100%); border-radius: 0 0 40px 40px; color: white; text-align: center; margin-bottom: 40px; }
    .insta-card { background: white; border-radius: 20px; border: 1px solid #efefef; margin-bottom: 40px; overflow: hidden; box-shadow: 0 10px 20px rgba(0,0,0,0.03); }
    .card-top { padding: 12px 18px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #fcfcfc; }
    .card-top .source-name { font-weight: 700; font-size: 0.9rem; color: #262626; }
    .card-top .post-date { font-size: 0.75rem; color: #8e8e93; }
    .card-img-container { width: 100%; height: 350px; background: #fafafa; overflow: hidden; }
    .card-img { width: 100%; height: 100%; object-fit: cover; }
    .card-body { padding: 15px 20px; }
    .title-ko { font-size: 1.15rem; font-weight: 700; color: #262626; margin-bottom: 5px; line-height: 1.4; }
    .title-en { font-size: 0.8rem; color: #8e8e93; font-style: italic; margin-bottom: 15px; display: block; }
    .summary-text { font-size: 0.88rem; color: #444; line-height: 1.5; margin-bottom: 15px; }
    .origin-link { font-size: 0.8rem; font-weight: 700; color: #00376b; text-decoration: none; }
</style>
""", unsafe_allow_html=True)

# --- 7. 사이드바 구성 ---
with st.sidebar:
    st.title("👤 Strategy Profile")
    u_id = st.radio("사용자", ["1", "2", "3", "4"], horizontal=True)
    if "current_user" not in st.session_state or st.session_state.current_user != u_id:
        st.session_state.current_user = u_id
        st.session_state.settings = load_user_settings(u_id)
        st.session_state.editing_key = False
        st.rerun()

    st.divider()
    curr_key = st.session_state.settings.get("api_key", "").strip()
    if not st.session_state.get("editing_key", False) and curr_key:
        st.success("✅ API 인증 완료")
        if st.button("🔑 키 수정"):
            st.session_state.editing_key = True; st.rerun()
    else:
        new_key = st.text_input("Gemini API Key", value=curr_key, type="password")
        if st.button("💾 저장"):
            st.session_state.settings["api_key"] = new_key
            save_user_settings(u_id, st.session_state.settings)
            st.session_state.editing_key = False; st.rerun()

    st.divider()
    st.subheader("📂 카테고리 관리")
    for cat in list(st.session_state.settings["channels"].keys()):
        st.session_state.settings["category_active"][cat] = st.toggle(cat, value=st.session_state.settings["category_active"].get(cat, True))
        if st.session_state.settings["category_active"][cat]:
            with st.expander(f"📌 {cat} 리스트"):
                with st.form(f"add_{cat}", clear_on_submit=True):
                    c_name = st.text_input("채널명", placeholder="이름")
                    c_url = st.text_input("URL", placeholder="RSS 주소")
                    if st.form_submit_button("➕ 추가") and c_name and c_url:
                        st.session_state.settings["channels"][cat].append({"name": c_name, "url": c_url, "active": True})
                        save_user_settings(u_id, st.session_state.settings); st.rerun()
                for idx, f in enumerate(st.session_state.settings["channels"][cat]):
                    c1, c2 = st.columns([4, 1])
                    f["active"] = c1.checkbox(f["name"], value=f.get("active", True), key=f"cb_{u_id}_{cat}_{idx}")
                    if c2.button("🗑️", key=f"del_{u_id}_{cat}_{idx}"):
                        st.session_state.settings["channels"][cat].pop(idx)
                        save_user_settings(u_id, st.session_state.settings); st.rerun()

    st.divider()
    with st.expander("⚙️ 고급 전략 설정", expanded=True):
        st.session_state.settings["sensing_period"] = st.slider("수집 기간 (일)", 1, 30, st.session_state.settings["sensing_period"])
        st.session_state.settings["max_articles"] = st.selectbox("표시 기사 수", [10, 20, 30, 50, 100], index=2)
        st.session_state.settings["filter_strength"] = st.slider("필터 강도", 1, 5, st.session_state.settings.get("filter_strength", 3))
        st.session_state.settings["filter_weight"] = st.slider("AI 가중치 (%)", 0, 100, st.session_state.settings.get("filter_weight", 70))
        st.session_state.settings["ai_prompt"] = st.text_area("분석 가이드라인", value=st.session_state.settings["ai_prompt"], height=150)

    if st.button("🚀 Apply & Sensing Start", use_container_width=True, type="primary"):
        save_user_settings(u_id, st.session_state.settings)
        st.cache_data.clear(); st.rerun()

# --- 8. 메인 렌더링 (Unified Instagram Style) ---
st.markdown("""<div class="main-header"><h1>NGEPT Strategy Hub</h1><p>Experience Innovation & Future Sensing</p></div>""", unsafe_allow_html=True)
raw_data = get_all_news(st.session_state.settings)

if raw_data:
    # --- 상단 필터/정렬 바 ---
    f1, f2, f3 = st.columns([2, 2, 2])
    with f1: sort_v = st.selectbox("📅 정렬", ["최신순", "과거순"])
    with f2: cat_v = st.multiselect("📂 카테고리 필터", list(st.session_state.settings["channels"].keys()), default=list(st.session_state.settings["channels"].keys()))
    with f3: search_v = st.text_input("🔍 스트림 내 검색", "")

    # 데이터 필터링/정렬
    display_data = [d for d in raw_data if d["category"] in cat_v]
    if search_v: display_data = [d for d in display_data if search_v.lower() in d["title_ko"].lower() or search_v.lower() in d["title_en"].lower()]
    if sort_v == "최신순": display_data.sort(key=lambda x: x["date_obj"], reverse=True)
    else: display_data.sort(key=lambda x: x["date_obj"])

    # 카드 그리드 출력 (3열)
    rows = [display_data[i:i + 3] for i in range(0, min(len(display_data), st.session_state.settings["max_articles"]), 3)]
    
    for row in rows:
        cols = st.columns(3)
        for idx, item in enumerate(row):
            with cols[idx]:
                st.markdown(f"""
                <div class="insta-card">
                    <div class="card-top">
                        <span class="source-name">🌐 {item['source']}</span>
                        <span class="post-date">{item['date']}</span>
                    </div>
                    <div class="card-img-container">
                        <img src="{get_thumbnail(item['link'])}" class="card-img">
                    </div>
                    <div class="card-body">
                        <div class="title-ko">{item['title_ko']}</div>
                        <span class="title-en">{item['title_en']}</span>
                        <div class="summary-text">{item['summary']}...</div>
                        <a href="{item['link']}" target="_blank" class="origin-link">🔗 원문 기사 읽기</a>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if st.button("🔍 Deep Analysis", key=f"btn_{item['id']}", use_container_width=True):
                    show_analysis_popup(item, st.session_state.settings)
else:
    st.info("조건에 맞는 데이터가 없습니다. 사이드바 설정을 확인해 주세요.")
