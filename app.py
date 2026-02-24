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

# --- 1. 초기 채널 데이터 (핵심 샘플링) ---
def get_initial_channels():
    # 코드 길이상 대표 채널만 명시 (실제 실행 시 100여 개 구성 가능)
    return {
        "Global Innovation (65)": [
            {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "active": True},
            {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "active": True},
            {"name": "9to5Google", "url": "https://9to5google.com/feed/", "active": True},
            {"name": "Engadget", "url": "https://www.engadget.com/rss.xml", "active": True},
        ],
        "China AI/HW (32)": [
            {"name": "36Kr (CN)", "url": "https://36kr.com/feed", "active": True},
            {"name": "Gizmochina", "url": "https://www.gizmochina.com/feed/", "active": True},
            {"name": "IT Home", "url": "https://www.ithome.com/rss/", "active": True},
        ],
        "Japan Innovation (15)": [
            {"name": "The Bridge JP", "url": "https://thebridge.jp/feed", "active": True},
            {"name": "Nikkei Asia", "url": "https://asia.nikkei.com/rss/feed/nar", "active": True},
        ]
    }

# --- 2. 설정 로직 (KeyError 방지 보완) ---
def get_user_file(user_id): return f"nod_samsung_user_{user_id}.json"

def load_user_settings(user_id):
    fn = get_user_file(user_id)
    default_settings = {
        "api_key": "AIzaSyBpko5khWacamTzhI6lsA70LyjCCNf06aA",
        "sensing_period": 7, 
        "max_articles": 30, 
        "filter_weight": 70,
        "filter_prompt": "제조사별 차세대 디바이스, 혁신적 하드웨어 디자인 소식 위주.",
        "ai_prompt": "삼성전자 CX 기획자 관점에서 분석: 1.요약 2.영향 3.제언",
        "category_active": {"Global Innovation (65)": True, "China AI/HW (32)": True, "Japan Innovation (15)": True},
        "channels": get_initial_channels()
    }
    
    if os.path.exists(fn):
        with open(fn, "r", encoding="utf-8") as f:
            saved = json.load(f)
            # [KeyError 방지] 저장된 파일에 새 설정항목이 없으면 기본값으로 업데이트
            for k, v in default_settings.items():
                if k not in saved:
                    saved[k] = v
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

# --- 4. 데이터 엔진 ---
def fetch_single_feed(args):
    cat, f, limit = args
    socket.setdefaulttimeout(10)
    articles = []
    try:
        d = feedparser.parse(f["url"])
        for entry in d.entries[:5]:
            dt = entry.get('published_parsed') or entry.get('updated_parsed')
            if dt:
                p_date = datetime.fromtimestamp(time.mktime(dt))
                if p_date < limit: continue
                articles.append({
                    "id": hashlib.md5(entry.link.encode()).hexdigest()[:12],
                    "title_en": entry.title, "title_ko": safe_translate(entry.title),
                    "link": entry.link, "source": f["name"], "category": cat, "date_obj": p_date,
                    "date": p_date.strftime("%m.%d"),
                    "summary": BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:120]
                })
    except: pass
    return articles

def get_all_news(settings):
    limit = datetime.now() - timedelta(days=settings["sensing_period"])
    active_tasks = [(cat, f, limit) for cat, feeds in settings["channels"].items() 
                    if settings["category_active"].get(cat, True) for f in feeds if f["active"]]
    if not active_tasks: return []

    all_news = []
    pb = st.sidebar.progress(0) # 사이드바에 표시
    total = len(active_tasks)
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch_single_feed, t): t for t in active_tasks}
        completed = 0
        for f in as_completed(futures):
            completed += 1
            all_news.extend(f.result())
            pb.progress(completed / total)
            
    pb.empty()
    return sorted(all_news, key=lambda x: x['date_obj'], reverse=True)

# --- 5. 팝업 분석 ---
@st.dialog("🎯 Strategic Insight")
def show_analysis_popup(item, settings):
    genai.configure(api_key=settings["api_key"])
    model = genai.GenerativeModel('gemini-1.5-flash')
    with st.spinner("AI가 기획 포인트를 도출 중..."):
        try:
            res = model.generate_content(f"{settings['ai_prompt']}\n\n제목: {item['title_en']}")
            st.markdown(f"### {item['title_ko']}")
            st.write(res.text)
        except Exception as e: st.error(f"분석 실패: {e}")

# --- 6. 모던 UI & 사이드바 ---
st.set_page_config(page_title="NGEPT Hub v11.1", layout="wide")

# 사이드바 스타일링
st.markdown("""
<style>
    /* 사이드바 배경 및 폰트 */
    [data-testid="stSidebar"] { background-color: #0e1117; color: #ffffff; }
    [data-testid="stSidebar"] .stMarkdown h1, h2, h3 { color: #007AFF; }
    
    /* 모던 카드 디자인 */
    .main-header { padding: 40px; background: #007AFF; border-radius: 25px; color: white; text-align: center; margin-bottom: 30px; }
    .insta-card { background: #ffffff; border-radius: 18px; border: 1px solid #f0f0f0; margin-bottom: 25px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); overflow: hidden; }
    .card-top { padding: 12px 18px; display: flex; align-items: center; border-bottom: 1px solid #f9f9f9; }
    .card-top a { text-decoration: none; color: #1a1a1a; font-weight: 700; font-size: 0.85rem; }
    .card-img-container { width: 100%; height: 300px; background: #f8f9fa; }
    .card-body { padding: 18px; }
    .title-ko { font-size: 1.15rem; font-weight: 700; color: #1a1a1a; margin-bottom: 8px; }
    
    /* 사이드바 채널 추가/삭제 UI */
    .channel-box { background: #1c1f26; padding: 10px; border-radius: 10px; margin-bottom: 5px; border-left: 3px solid #007AFF; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## 👤 Strategy Profile")
    u_id = st.radio("사용자", ["1", "2", "3", "4"], horizontal=True)
    if "current_user" not in st.session_state or st.session_state.current_user != u_id:
        st.session_state.current_user = u_id
        st.session_state.settings = load_user_settings(u_id)
        st.rerun()

    st.divider()
    st.markdown("### 🌐 Category & Channels")
    for cat in list(st.session_state.settings["channels"].keys()):
        st.session_state.settings["category_active"][cat] = st.toggle(cat, value=st.session_state.settings["category_active"].get(cat, True))
        if st.session_state.settings["category_active"][cat]:
            with st.expander(f"📌 {cat} 관리"):
                # 채널 추가 UI 현대화
                with st.container():
                    st.caption("➕ 새 채널 등록")
                    c_n = st.text_input("이름", key=f"n_{cat}", label_visibility="collapsed", placeholder="채널명")
                    c_u = st.text_input("URL", key=f"u_{cat}", label_visibility="collapsed", placeholder="RSS URL")
                    if st.button("추가", key=f"btn_{cat}", use_container_width=True):
                        if c_n and c_u:
                            st.session_state.settings["channels"][cat].append({"name": c_n, "url": c_u, "active": True})
                            save_user_settings(u_id, st.session_state.settings); st.rerun()
                
                st.markdown("---")
                # 채널 리스트 UI
                for idx, f in enumerate(st.session_state.settings["channels"][cat]):
                    with st.container():
                        col1, col2 = st.columns([5, 1])
                        f["active"] = col1.checkbox(f["name"], value=f.get("active", True), key=f"cb_{u_id}_{cat}_{idx}")
                        if col2.button("🗑️", key=f"del_{u_id}_{cat}_{idx}"):
                            st.session_state.settings["channels"][cat].pop(idx)
                            save_user_settings(u_id, st.session_state.settings); st.rerun()

    st.divider()
    with st.expander("⚙️ Advanced Strategy"):
        st.session_state.settings["filter_weight"] = st.slider("AI 필터 가중치 (%)", 0, 100, st.session_state.settings.get("filter_weight", 70))
        st.session_state.settings["sensing_period"] = st.slider("수집 기간 (일)", 1, 30, st.session_state.settings["sensing_period"])
        st.session_state.settings["ai_prompt"] = st.text_area("분석 가이드라인", value=st.session_state.settings["ai_prompt"], height=100)

    if st.button("🚀 Apply & Sensing", use_container_width=True, type="primary"):
        save_user_settings(u_id, st.session_state.settings)
        st.cache_data.clear(); st.rerun()

# --- 7. 메인 렌더링 ---
st.markdown("""<div class="main-header"><h1>NGEPT Strategy Hub</h1><p>Experience Innovation & Future Sensing</p></div>""", unsafe_allow_html=True)

raw_data = get_all_news(st.session_state.settings)

if raw_data:
    st.subheader(f"🌟 Strategic Top Picks")
    cols = st.columns(3)
    for i, item in enumerate(raw_data[:6]):
        with cols[i % 3]:
            st.markdown(f"""
            <div class="insta-card">
                <div class="card-top">
                    <a href="{item['link']}" target="_blank">🌐 {item['source']}</a>
                    <span style="margin-left:auto; font-size:0.7rem; color:#888;">{item['date']}</span>
                </div>
                <div class="card-img-container">
                    <img src="{get_thumbnail(item['link'])}" style="width:100%; height:100%; object-fit:cover;">
                </div>
                <div class="card-body">
                    <div class="title-ko">{item['title_ko']}</div>
                    <p style="font-size:0.85rem; color:#666; line-height:1.4;">{item['summary']}...</p>
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("🔍 Deep Insight", key=f"ana_{item['id']}", use_container_width=True):
                show_analysis_popup(item, st.session_state.settings)
else:
    st.info("조건에 맞는 데이터가 없습니다.")
