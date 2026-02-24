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

# --- 1. 초기 채널 데이터 (원복 및 통합) ---
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
        "api_key": "",
        "sensing_period": 7,
        "max_articles": 30,
        "filter_prompt": "혁신적 인터페이스, 파괴적 AI 기능 중심.",
        "ai_prompt": "삼성전자 기획자 관점 분석: a)사실요약 b)3년후 영향 c)시사점",
        "category_active": {"Global Innovation (23)": True, "China AI/HW (11)": True, "Japan Innovation (11)": True},
        "channels": get_initial_channels()
    }

def save_user_settings(user_id, settings):
    with open(get_user_file(user_id), "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

# --- 3. 모델 및 유틸리티 ---
def get_ai_model(api_key):
    if not api_key: return None
    try:
        genai.configure(api_key=api_key.strip())
        # 404 에러 방지를 위한 순차적 모델 시도
        for model_name in ['gemini-1.5-flash', 'gemini-pro', 'models/gemini-1.5-flash']:
            try:
                model = genai.GenerativeModel(model_name)
                return model
            except: continue
        return None
    except Exception as e:
        st.error(f"AI 설정 오류: {e}")
        return None

@st.cache_data(ttl=3600)
def safe_translate(text):
    if not text: return ""
    try: return GoogleTranslator(source='auto', target='ko').translate(text)
    except: return text

# --- 4. 데이터 수집 엔진 ---
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
                articles.append({
                    "id": hashlib.md5(entry.link.encode()).hexdigest()[:12],
                    "title_en": entry.title, "link": entry.link,
                    "source": f["name"], "category": cat, "date_obj": p_date
                })
    except: pass
    return articles

@st.cache_data(ttl=3600)
def get_all_news(settings):
    limit = datetime.now() - timedelta(days=settings["sensing_period"])
    active_tasks = [(cat, f, limit) for cat, feeds in settings["channels"].items() 
                    if settings["category_active"].get(cat, True) for f in feeds if f["active"]]
    if not active_tasks: return []
    with ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(fetch_single_feed, active_tasks))
    all_news = [item for sublist in results for item in sublist]
    return sorted(all_news, key=lambda x: x['date_obj'], reverse=True)

# --- 5. 사이드바 UI ---
st.set_page_config(page_title="NOD Strategy Hub v9.7", layout="wide")

with st.sidebar:
    st.title("👤 User Profile")
    u_id = st.radio("사용자", ["1", "2", "3", "4"], horizontal=True)
    if "current_user" not in st.session_state or st.session_state.current_user != u_id:
        st.session_state.current_user = u_id
        st.session_state.settings = load_user_settings(u_id)
        st.rerun()

    st.divider()
    st.subheader("🛡️ NOD Controller")
    new_api = st.text_input("Gemini API Key", value=st.session_state.settings.get("api_key", ""), type="password")
    if new_api != st.session_state.settings["api_key"]:
        st.session_state.settings["api_key"] = new_api
        save_user_settings(u_id, st.session_state.settings)

    st.divider()
    edit_mode = st.toggle("🛠️ 채널 편집 모드 활성화")
    for cat in list(st.session_state.settings["channels"].keys()):
        st.session_state.settings["category_active"][cat] = st.toggle(cat, value=st.session_state.settings["category_active"].get(cat, True))
        if st.session_state.settings["category_active"][cat]:
            with st.expander(f"{cat} 관리"):
                for idx, f in enumerate(st.session_state.settings["channels"][cat]):
                    c_ch, c_del = st.columns([4, 1])
                    f["active"] = c_ch.checkbox(f["name"], value=f.get("active", True), key=f"cb_{u_id}_{cat}_{idx}")
                    if edit_mode and c_del.button("❌", key=f"del_{u_id}_{cat}_{idx}"):
                        st.session_state.settings["channels"][cat].pop(idx)
                        save_user_settings(u_id, st.session_state.settings); st.rerun()
                if edit_mode:
                    with st.form(f"add_{cat}"):
                        n, u = st.text_input("채널명"), st.text_input("URL")
                        if st.form_submit_button("추가") and n and u:
                            st.session_state.settings["channels"][cat].append({"name": n, "url": u, "active": True})
                            save_user_settings(u_id, st.session_state.settings); st.rerun()

    st.divider()
    with st.expander("⚙️ 고급 설정"):
        st.session_state.settings["sensing_period"] = st.slider("기간", 1, 30, st.session_state.settings["sensing_period"])
        st.session_state.settings["max_articles"] = st.selectbox("개수", [10, 20, 30, 50], index=2)
        st.session_state.settings["ai_prompt"] = st.text_area("AI 분석 프롬프트", value=st.session_state.settings["ai_prompt"], height=150)

    if st.button("🚀 Apply & Sensing", use_container_width=True, type="primary"):
        save_user_settings(u_id, st.session_state.settings)
        st.cache_data.clear(); st.rerun()

# --- 6. 메인 화면 ---
st.markdown("<style>.card { background: white; padding: 20px; border-radius: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); margin-bottom: 20px; }</style>", unsafe_allow_html=True)
st.title("🚀 NGEPT Strategy Hub")

news_data = get_all_news(st.session_state.settings)

if news_data:
    st.subheader("🌟 Top Picks")
    cols = st.columns(3)
    for i, item in enumerate(news_data[:6]):
        with cols[i % 3]:
            st.markdown(f"""<div class="card">
                <img src="https://s.wordpress.com/mshots/v1/{item['link']}?w=400" style="width:100%; border-radius:15px; margin-bottom:10px;">
                <h4>{safe_translate(item['title_en'])}</h4>
                <p style="color:gray; font-size:0.8rem;">{item['source']} | {item['date_obj'].strftime('%Y-%m-%d')}</p>
            </div>""", unsafe_allow_html=True)
            if st.button("🔍 Deep Analysis", key=f"btn_{item['id']}"):
                model = get_ai_model(st.session_state.settings["api_key"])
                if model:
                    with st.spinner("AI 분석 중..."):
                        try:
                            res = model.generate_content(f"{st.session_state.settings['ai_prompt']}\n내용: {item['title_en']}")
                            st.info(res.text)
                        except Exception as e: st.error(f"분석 실패: {e}")
                else: st.error("API 키 확인 필요 (AI Studio에서 발급 권장)")

    st.divider()
    st.subheader("📋 실시간 뉴스 스트림")
    for item in news_data[6:st.session_state.settings["max_articles"]]:
        c1, c2 = st.columns([1, 4])
        with c1: st.image(f"https://s.wordpress.com/mshots/v1/{item['link']}?w=200")
        with c2:
            st.markdown(f"**{item['title_en']}**")
            st.caption(f"{item['source']} | {item['date_obj'].strftime('%Y-%m-%d')}")
            if st.button("Quick View", key=f"q_{item['id']}"):
                st.write(safe_translate(item['title_en']))
        st.markdown("---")
else: st.info("수집된 데이터가 없습니다.")
