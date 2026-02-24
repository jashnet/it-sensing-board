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

# --- 1. 초기 채널 데이터 (원복 완료) ---
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

# --- 2. 설정 로드/저장 ---
def load_user_settings(user_id):
    filename = f"user_{user_id}_config.json"
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "api_key": "",
        "sensing_period": 7,
        "max_articles": 30,
        "filter_prompt": "혁신적 인터페이스, 파괴적 AI 기능 위주",
        "ai_prompt": "삼성전자 기획자 관점에서 요약, 향후 3년 영향, 시사점을 분석하라.",
        "category_active": {"Global Innovation (23)": True, "China AI/HW (11)": True, "Japan Innovation (11)": True},
        "channels": get_initial_channels()
    }

def save_user_settings(user_id, settings):
    with open(f"user_{user_id}_config.json", "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

@st.cache_data(ttl=1800)
def safe_translate(text):
    if not text: return ""
    try: return GoogleTranslator(source='auto', target='ko').translate(text)
    except: return text

# --- 3. 데이터 엔진 (병렬 수집) ---
def fetch_single_feed(args):
    cat, f, limit = args
    socket.setdefaulttimeout(10)
    articles = []
    try:
        d = feedparser.parse(f["url"])
        for entry in d.entries[:10]:
            dt = entry.get('published_parsed') or entry.get('updated_parsed')
            if dt:
                p_date = datetime.fromtimestamp(time.mktime(dt))
                if p_date < limit: continue
                articles.append({
                    "id": hashlib.md5(entry.link.encode()).hexdigest()[:12],
                    "title_en": entry.title,
                    "link": entry.link,
                    "source": f["name"],
                    "category": cat,
                    "date_obj": p_date
                })
    except: pass
    return articles

@st.cache_data(ttl=3600)
def get_all_news(settings):
    all_news = []
    limit = datetime.now() - timedelta(days=settings["sensing_period"])
    active_tasks = [(cat, f, limit) for cat, feeds in settings["channels"].items() 
                    if settings["category_active"].get(cat, True) for f in feeds if f["active"]]
    
    if not active_tasks: return []
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(fetch_single_feed, active_tasks))
    for res in results: all_news.extend(res)
    return sorted(all_news, key=lambda x: x['date_obj'], reverse=True)

# --- 4. 메인 UI 및 사이드바 ---
st.set_page_config(page_title="NOD Strategy Hub v9.2", layout="wide")

with st.sidebar:
    st.title("👤 User Profile")
    user_id = st.radio("사용자 선택", ["1", "2", "3", "4"], horizontal=True)
    if "current_user" not in st.session_state or st.session_state.current_user != user_id:
        st.session_state.current_user = user_id
        st.session_state.settings = load_user_settings(user_id)
        st.rerun()

    st.divider()
    # 채널 편집 모드 토글
    edit_mode = st.toggle("🛠️ 채널 편집 모드 활성화")
    
    for cat in list(st.session_state.settings["channels"].keys()):
        st.session_state.settings["category_active"][cat] = st.toggle(cat, value=st.session_state.settings["category_active"].get(cat, True))
        
        if st.session_state.settings["category_active"][cat]:
            with st.expander(f"{cat} 리스트"):
                # 채널 목록 표시
                for idx, f in enumerate(st.session_state.settings["channels"][cat]):
                    col_ch, col_del = st.columns([4, 1])
                    f["active"] = col_ch.checkbox(f["name"], value=f.get("active", True), key=f"cb_{user_id}_{cat}_{idx}")
                    
                    # 편집 모드일 때만 삭제 버튼 노출
                    if edit_mode:
                        if col_del.button("❌", key=f"del_{user_id}_{cat}_{idx}"):
                            st.session_state.settings["channels"][cat].pop(idx)
                            save_user_settings(user_id, st.session_state.settings)
                            st.rerun()
                
                # 편집 모드일 때만 추가 폼 노출
                if edit_mode:
                    st.markdown("---")
                    with st.form(key=f"add_{cat}_{user_id}"):
                        new_n = st.text_input("새 채널 이름")
                        new_u = st.text_input("RSS URL")
                        if st.form_submit_button("채널 추가"):
                            if new_n and new_u:
                                st.session_state.settings["channels"][cat].append({"name": new_n, "url": new_u, "active": True})
                                save_user_settings(user_id, st.session_state.settings)
                                st.rerun()

    if st.button("🚀 설정 저장 및 수집 시작", use_container_width=True):
        save_user_settings(user_id, st.session_state.settings)
        st.cache_data.clear()
        st.rerun()

# --- 5. 콘텐츠 렌더링 ---
st.title("🚀 NGEPT Strategic Sensing")
news_list = get_all_news(st.session_state.settings)

if news_list:
    top_6 = news_list[:6]
    cols = st.columns(3)
    for i, item in enumerate(top_6):
        with cols[i % 3]:
            st.markdown(f"""
            <div style="border:1px solid #eee; padding:15px; border-radius:15px; margin-bottom:10px;">
                <img src="https://s.wordpress.com/mshots/v1/{item['link']}?w=400" style="width:100%; border-radius:10px;">
                <h4 style="margin:10px 0;">{safe_translate(item['title_en'])}</h4>
                <p style="font-size:0.8rem; color:grey;">{item['source']} | {item['date_obj'].strftime('%Y-%m-%d')}</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button("AI Deep Analysis", key=f"ai_{item['id']}"):
                st.info("Gemini 분석 결과가 여기에 표시됩니다. (API 연동 시)")
else:
    st.info("수집된 기사가 없습니다. 사이드바에서 채널을 활성화하고 '수집 시작'을 눌러주세요.")
