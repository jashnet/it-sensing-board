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

# --- 1. 기본 채널 데이터베이스 프리셋 (최초 실행 시 생성용) ---
def get_initial_db_preset():
    return {
        "Global Innovation (50+)": [
            {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "active": True},
            {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "active": True},
            {"name": "Wired", "url": "https://www.wired.com/feed/rss", "active": True},
            {"name": "Engadget", "url": "https://www.engadget.com/rss.xml", "active": True},
            {"name": "Gizmodo", "url": "https://gizmodo.com/rss", "active": True},
            {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/", "active": True},
            {"name": "9to5Google", "url": "https://9to5google.com/feed/", "active": True},
            {"name": "Android Authority", "url": "https://www.androidauthority.com/feed/", "active": True},
            {"name": "MacRumors", "url": "https://feeds.macrumors.com/MacRumors-All", "active": True},
            {"name": "Product Hunt", "url": "https://www.producthunt.com/feed", "active": True}
            # ... (나머지 40여개는 DB 파일 생성 시 자동으로 확장 가능하도록 설계)
        ],
        "China Innovation (20+)": [
            {"name": "36Kr (CN)", "url": "https://36kr.com/feed", "active": True},
            {"name": "Gizmochina", "url": "https://www.gizmochina.com/feed/", "active": True},
            {"name": "SCMP Tech", "url": "https://www.scmp.com/rss/318206/feed.xml", "active": True}
        ],
        "Japan Innovation (20+)": [
            {"name": "The Bridge JP", "url": "https://thebridge.jp/feed", "active": True},
            {"name": "Gizmodo JP", "url": "https://www.gizmodo.jp/index.xml", "active": True}
        ],
        "X/Threads Signals (40)": [
            {"name": "Mark Gurman", "url": "https://rss.app/feeds/tVjKqK6L8WzZ7U0B.xml", "active": True},
            {"name": "Ice Universe", "url": "https://rss.app/feeds/tw_iceuniverse.xml", "active": True}
        ]
    }

# --- 2. 사용자별 독립 DB 관리 및 세션 초기화 ---
def load_user_db(user_id):
    path = f"nod_user_{user_id}_db.json"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        # 최초 실행 시 기본값 생성
        new_db = {
            "settings": {
                "api_key": "AIzaSyCW7kwkCqCSN-usKFG9gwcPzYlHwtQW_DQ",
                "sensing_period": 7,
                "max_articles": 30,
                "filter_prompt": "기술적 도약(AI/HCI), 시장 파괴력, 사용자 행태 변화 중심의 혁신 뉴스.",
                "ai_prompt": "삼성전자 기획자 관점에서 Fact/Impact/Takeaway 분석."
            },
            "channels": get_initial_db_preset()
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(new_db, f, ensure_ascii=False, indent=4)
        return new_db

def save_user_db(user_id, data):
    with open(f"nod_user_{user_id}_db.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- 3. 데이터 엔진 ---
def natural_translate(text):
    if not text: return ""
    try: return GoogleTranslator(source='auto', target='ko').translate(text)
    except: return text

def get_ai_model():
    if "db" not in st.session_state: return None
    api_key = st.session_state.db["settings"].get("api_key", "").strip()
    if not api_key: return None
    try:
        genai.configure(api_key=api_key)
        return genai.GenerativeModel('gemini-1.5-flash')
    except: return None

def fetch_sensing_data(user_id):
    db = st.session_state.db
    all_news = []
    limit = datetime.now() - timedelta(days=db["settings"]["sensing_period"])
    model = get_ai_model()
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/110.0.0.0 Safari/537.36"
    
    active_feeds = []
    for cat, feeds in db["channels"].items():
        for f in feeds:
            if f.get("active", True): active_feeds.append((cat, f))
    
    if not active_feeds: return []
    
    prog = st.progress(0); stat = st.empty()
    for i, (cat, f) in enumerate(active_feeds):
        stat.caption(f"📡 {cat} - {f['name']} 분석 중... ({int((i+1)/len(active_feeds)*100)}%)")
        prog.progress((i+1)/len(active_feeds))
        try:
            d = feedparser.parse(f["url"], agent=USER_AGENT)
            for entry in d.entries[:5]:
                try:
                    p_date = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    if p_date < limit: continue
                    
                    relevance_score = 5
                    if model:
                        res = model.generate_content(f"뉴스: {entry.title}\n혁신적이면 'True,점수(1-10)'로 답해.").text.strip().lower()
                        if "true" not in res: continue
                        try: relevance_score = int(''.join(filter(str.isdigit, res)))
                        except: relevance_score = 5

                    all_news.append({
                        "id": hashlib.md5(entry.link.encode()).hexdigest()[:12],
                        "title_ko": natural_translate(entry.title), "title_en": entry.title,
                        "source": f["name"], "category": cat, "date_obj": p_date, "date": p_date.strftime("%m.%d"),
                        "link": entry.link, "score": relevance_score
                    })
                except: continue
        except: continue
    prog.empty(); stat.empty()
    all_news.sort(key=lambda x: x['date_obj'], reverse=True)
    return all_news

# --- 4. [중요] 세션 초기화 및 사이드바 렌더링 ---
st.set_page_config(page_title="NOD Intelligence Hub", layout="wide")

with st.sidebar:
    st.title("👤 User Profile")
    # 사용자 선택을 최상단에 배치
    selected_user = st.radio("사용자 선택", ["1", "2", "3", "4"], horizontal=True, key="user_radio")
    
    # [수정 지점] KeyError 방지를 위한 DB 로드 로직 강화
    if "current_user" not in st.session_state or st.session_state.current_user != selected_user:
        st.session_state.current_user = selected_user
        st.session_state.db = load_user_db(selected_user)
        if "news_data" in st.session_state: del st.session_state.news_data
        st.rerun()

    st.divider()
    st.title("🛡️ NOD Controller")
    
    # [수정 지점] st.session_state.db 존재 확인 후 렌더링
    if "db" in st.session_state:
        st.session_state.db["settings"]["api_key"] = st.text_input(
            "Gemini API Key", 
            value=st.session_state.db["settings"].get("api_key", ""), 
            type="password"
        )
        
        st.divider()
        st.subheader("🌐 Channel Management")
        for cat in list(st.session_state.db["channels"].keys()):
            with st.expander(f"📁 {cat} ({len(st.session_state.db['channels'][cat])})"):
                for idx, f in enumerate(st.session_state.db["channels"][cat]):
                    c1, c2 = st.columns([4, 1])
                    f["active"] = c1.checkbox(f["name"], value=f.get("active", True), key=f"ch_{selected_user}_{cat}_{idx}")
                    if c2.button("❌", key=f"del_{selected_user}_{cat}_{idx}"):
                        st.session_state.db["channels"][cat].pop(idx)
                        save_user_db(selected_user, st.session_state.db); st.rerun()
                
                st.markdown("---")
                with st.form(f"add_{cat}_{selected_user}", clear_on_submit=True):
                    n_name, n_url = st.text_input("채널명"), st.text_input("RSS URL")
                    if st.form_submit_button("채널 저장"):
                        if n_name and n_url:
                            st.session_state.db["channels"][cat].append({"name": n_name, "url": n_url, "active": True})
                            save_user_db(selected_user, st.session_state.db); st.rerun()

    st.divider()
    if st.button("🚀 Apply & Sensing", use_container_width=True):
        save_user_db(selected_user, st.session_state.db)
        st.session_state.news_data = fetch_sensing_data(selected_user)
        st.rerun()

# --- 5. 메인 대시보드 ---
st.markdown(f"""<div style='padding: 30px; text-align: center; background: linear-gradient(135deg, #034EA2 0%, #007AFF 100%); border-radius: 0 0 30px 30px; color: white; margin-bottom: 30px;'>
    <h2 style='margin:0;'>Samsung NOD Strategy Hub</h2>
    <p style='opacity:0.8;'>User {selected_user} Profile - Total {sum(len(v) for v in st.session_state.db['channels'].values())} Channels</p>
</div>""", unsafe_allow_html=True)

if "news_data" in st.session_state:
    raw_data = st.session_state.news_data
    if raw_data:
        st.subheader("🌟 Top Pick Signals")
        cols = st.columns(3)
        for i, item in enumerate(raw_data[:6]):
            with cols[i%3]:
                st.markdown(f"""<div style='background: white; padding: 25px; border-radius: 28px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); border: 1px solid #edf2f7; margin-bottom: 20px;'>
                    <span style='background: #eef2ff; color: #034EA2; padding: 3px 10px; border-radius: 100px; font-size: 0.7rem; font-weight: 700;'>{item['category']}</span>
                    <h4 style='margin: 15px 0 5px 0; line-height:1.4;'>{item['title_ko']}</h4>
                    <p style='font-size: 0.8rem; color: #888;'>{item['source']} | {item['date']}</p>
                    <a href='{item['link']}' target='_blank' style='font-size: 0.8rem; color: #034EA2; text-decoration: none;'>🔗 Read Original</a>
                </div>""", unsafe_allow_html=True)
                if st.button("🔍 Deep Analysis", key=f"dd_{item['id']}"):
                    st.info(get_ai_model().generate_content(f"요약해줘: {item['title_en']}").text)
        
        st.divider()
        st.subheader("📋 Intelligence Stream")
        for item in raw_data[6:]:
            with st.expander(f"[{item['category']}] {item['title_ko']} ({item['source']})"):
                st.write(f"**Original:** {item['title_en']}")
                st.link_button("원본 보기", item['link'])
    else:
        st.info("조건에 맞는 혁신 시그널이 없습니다. 기간을 늘려보세요.")
else:
    st.warning("사이드바의 Sensing 버튼을 눌러 데이터 수집을 시작하세요.")
