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

# --- 1. 초기 채널 데이터 및 설정 로드 ---
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

def get_user_file(user_id):
    return f"nod_samsung_user_{user_id}.json"

def load_user_settings(user_id):
    filename = get_user_file(user_id)
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "api_key": "",
        "sensing_period": 7,
        "max_articles": 30,
        "filter_strength": 3,
        "filter_prompt": "혁신적 인터페이스, 파괴적 AI 기능 위주 뉴스.",
        "ai_prompt": "삼성전자(Samsung) 기획자 관점 3단계 분석:\na) Fact Summary\nb) 3-Year Future Impact\nc) Samsung Takeaway",
        "category_active": {"Global Innovation (23)": True, "China AI/HW (11)": True, "Japan Innovation (11)": True},
        "channels": get_initial_channels()
    }

def save_user_settings(user_id, settings):
    with open(get_user_file(user_id), "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

# --- 2. 모델 및 유틸리티 (404 에러 방지 강화) ---
def get_ai_model(api_key):
    if not api_key: return None
    try:
        genai.configure(api_key=api_key.strip())
        # 404 에러 해결: 라이브러리 버전에 따라 다를 수 있는 모델명을 순차적으로 시도
        for model_name in ['gemini-1.5-flash', 'models/gemini-1.5-flash']:
            try:
                model = genai.GenerativeModel(model_name)
                # 모델이 존재하는지 간단히 테스트
                return model
            except: continue
        return None
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
                st.markdown(f"🔗 [기사 원문 읽기]({item['link']})")
            except Exception as e:
                st.error(f"분석 실패: {e}\n(API 키 또는 지역 제한을 확인하세요)")
    else: st.error("API Key를 확인해주세요.")

@st.cache_data(ttl=3600)
def safe_translate(text):
    if not text: return ""
    try: return GoogleTranslator(source='auto', target='ko').translate(text)
    except: return text

# --- 3. 데이터 엔진 (프로그레스 바 포함) ---
def fetch_single_feed(args):
    cat, f, limit = args
    socket.setdefaulttimeout(15)
    articles = []
    try:
        d = feedparser.parse(f["url"])
        for entry in d.entries[:8]:
            dt = entry.get('published_parsed') or entry.get('updated_parsed')
            if dt:
                p_date = datetime.fromtimestamp(time.mktime(dt))
                if p_date < limit: continue
                raw_sum = entry.get("summary", "")
                summary = BeautifulSoup(raw_sum, "html.parser").get_text()[:150] if raw_sum else ""
                articles.append({
                    "id": hashlib.md5(entry.link.encode()).hexdigest()[:12],
                    "title_en": entry.title, "title_ko": safe_translate(entry.title),
                    "summary": safe_translate(summary), "link": entry.link,
                    "source": f["name"], "category": cat, "date_obj": p_date,
                    "date": p_date.strftime("%Y.%m.%d")
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
    
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = {executor.submit(fetch_single_feed, t): t for t in active_tasks}
        completed = 0
        for f in as_completed(futures):
            completed += 1
            all_news.extend(f.result())
            pb.progress(completed / total)
            st_text.caption(f"📡 데이터 수집 중... {int((completed/total)*100)}% ({completed}/{total})")
            
    st_text.empty()
    pb.empty()
    return sorted(all_news, key=lambda x: x['date_obj'], reverse=True)

# --- 4. 사이드바 UI (위치 변경 적용) ---
st.set_page_config(page_title="NGEPT Strategy Hub", layout="wide")

with st.sidebar:
    st.title("👤 Strategy Hub")
    u_id = st.radio("사용자", ["1", "2", "3", "4"], horizontal=True)
    if "current_user" not in st.session_state or st.session_state.current_user != u_id:
        st.session_state.current_user = u_id
        st.session_state.settings = load_user_settings(u_id)
        st.session_state.editing_key = False
        st.rerun()

    st.divider()
    # API 키 상태 표시 및 수정
    curr_key = st.session_state.settings.get("api_key", "").strip()
    if not st.session_state.get("editing_key", False) and curr_key:
        st.success("✅ API Key 저장됨")
        if st.button("🔑 키 수정"):
            st.session_state.editing_key = True
            st.rerun()
    else:
        new_key = st.text_input("Gemini API Key 입력", value=curr_key, type="password")
        if st.button("💾 키 저장"):
            st.session_state.settings["api_key"] = new_key
            save_user_settings(u_id, st.session_state.settings)
            st.session_state.editing_key = False
            st.rerun()

    # --- 1. 카테고리 설정 (위로 이동) ---
    st.divider()
    st.subheader("📂 카테고리 및 채널")
    edit_ch = st.toggle("🛠️ 채널 편집 모드")
    for cat in list(st.session_state.settings["channels"].keys()):
        st.session_state.settings["category_active"][cat] = st.toggle(cat, value=st.session_state.settings["category_active"].get(cat, True))
        if st.session_state.settings["category_active"][cat]:
            with st.expander(f"📌 {cat} 리스트"):
                for idx, f in enumerate(st.session_state.settings["channels"][cat]):
                    c1, c2 = st.columns([4, 1])
                    f["active"] = c1.checkbox(f["name"], value=f.get("active", True), key=f"side_cb_{u_id}_{cat}_{idx}")
                    if edit_ch and c2.button("❌", key=f"side_del_{u_id}_{cat}_{idx}"):
                        st.session_state.settings["channels"][cat].pop(idx)
                        save_user_settings(u_id, st.session_state.settings); st.rerun()

    # --- 2. 고급 설정 (아래로 이동) ---
    st.divider()
    with st.expander("⚙️ 고급 전략 설정", expanded=False):
        st.session_state.settings["sensing_period"] = st.slider("수집 기간 (일)", 1, 30, st.session_state.settings["sensing_period"])
        st.session_state.settings["max_articles"] = st.selectbox("표시 기사 수", [10, 20, 30, 50, 100], index=2)
        st.session_state.settings["filter_strength"] = st.slider("분석 필터 강도", 1, 5, st.session_state.settings.get("filter_strength", 3))
        st.session_state.settings["ai_prompt"] = st.text_area("AI 가이드라인", value=st.session_state.settings["ai_prompt"], height=120)

    if st.button("🚀 Apply & Sensing Start", use_container_width=True, type="primary"):
        save_user_settings(u_id, st.session_state.settings)
        st.cache_data.clear(); st.rerun()

# --- 5. 메인 화면 ---
st.markdown("""
<style>
    .main-header { padding: 40px 0; background: linear-gradient(135deg, #034EA2 0%, #007AFF 100%); border-radius: 0 0 30px 30px; color: white; text-align: center; margin-bottom: 30px; }
    .insta-card { background: white; border-radius: 20px; border: 1px solid #efefef; margin-bottom: 25px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
    .card-img { width: 100%; height: 220px; object-fit: cover; }
    .card-content { padding: 20px; }
</style>
""", unsafe_allow_html=True)

st.markdown("""<div class="main-header"><h1>NGEPT Strategy Hub</h1><p>Future Experience Sensing & Opportunity Discovery</p></div>""", unsafe_allow_html=True)

raw_data = get_all_news(st.session_state.settings)

if raw_data:
    st.subheader("🌟 Strategic Top Picks")
    cols = st.columns(3)
    for i, item in enumerate(raw_data[:6]):
        with cols[i % 3]:
            st.markdown(f"""
            <div class="insta-card">
                <div style="padding:10px 20px; display:flex; justify-content:space-between; font-size:0.75rem; color:#888;">
                    <b>{item['source']}</b><span>{item['date']}</span>
                </div>
                <img src="https://s.wordpress.com/mshots/v1/{item['link']}?w=500" class="card-img">
                <div class="card-content">
                    <div style="font-weight:700; font-size:1.1rem; margin-bottom:5px;">{item['title_ko']}</div>
                    <div style="font-size:0.8rem; color:#999; margin-bottom:12px; font-style:italic;">{item['title_en']}</div>
                    <div style="font-size:0.85rem; color:#555; line-height:1.5;">{item['summary']}...</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            c_btn1, c_btn2 = st.columns(2)
            if c_btn1.button("🔍 Deep Analysis", key=f"p_{item['id']}", use_container_width=True):
                show_analysis_popup(item, st.session_state.settings["ai_prompt"], st.session_state.settings["api_key"])
            c_btn2.link_button("🔗 원문 보기", item['link'], use_container_width=True)

    st.divider()
    st.subheader("📋 실시간 센싱 스트림")
    sc1, sc2, sc3 = st.columns([2, 2, 2])
    with sc1: sort_v = st.selectbox("📅 정렬", ["최신순", "과거순"])
    with sc2: cat_v = st.multiselect("📂 필터", list(st.session_state.settings["channels"].keys()), default=list(st.session_state.settings["channels"].keys()))
    with sc3: search_v = st.text_input("🔍 검색", "")

    stream_data = [d for d in raw_data if d["category"] in cat_v]
    if search_v: stream_data = [d for d in stream_data if search_v.lower() in d["title_ko"].lower()]
    if sort_v == "최신순": stream_data.sort(key=lambda x: x["date_obj"], reverse=True)
    else: stream_data.sort(key=lambda x: x["date_obj"])

    for item in stream_data[:st.session_state.settings["max_articles"]]:
        c_img, c_txt = st.columns([1, 4])
        with c_img: st.image(f"https://s.wordpress.com/mshots/v1/{item['link']}?w=300")
        with c_txt:
            st.markdown(f"**[{item['source']}]** {item['date']} | {item['category']}")
            st.markdown(f"#### {item['title_ko']}")
            st.write(item['summary'] + "...")
            if st.button("Quick View", key=f"q_{item['id']}"):
                show_analysis_popup(item, st.session_state.settings["ai_prompt"], st.session_state.settings["api_key"])
        st.markdown("---")
