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

# --- 1. 초기 채널 데이터 (핵심 리스트) ---
def get_initial_channels():
    return {
        "Global Innovation": [
            {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "active": True},
            {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "active": True},
            {"name": "Wired", "url": "https://www.wired.com/feed/rss", "active": True},
            {"name": "Samsung Global", "url": "https://news.samsung.com/global/feed", "active": True},
            {"name": "Apple News", "url": "https://www.apple.com/newsroom/rss-feed.rss", "active": True},
            {"name": "9to5Google", "url": "https://9to5google.com/feed/", "active": True},
            {"name": "X-MKBHD", "url": "https://rss.itdog.icu/twitter/user/mkbhd", "active": True}
        ],
        "China & East Asia": [
            {"name": "36Kr", "url": "https://36kr.com/feed", "active": True},
            {"name": "IT Home", "url": "https://www.ithome.com/rss/", "active": True},
            {"name": "Gizmochina", "url": "https://www.gizmochina.com/feed/", "active": True}
        ],
        "Japan & Robotics": [
            {"name": "The Bridge JP", "url": "https://thebridge.jp/feed", "active": True},
            {"name": "Nikkei Asia", "url": "https://asia.nikkei.com/rss/feed/nar", "active": True}
        ]
    }

# --- 2. 설정 로직 ---
def load_user_settings(user_id):
    fn = f"nod_samsung_user_{user_id}.json"
    default = {
        "api_key": "AIzaSyBpko5khWacamTzhI6lsA70LyjCCNf06aA",
        "sensing_period": 3, "max_articles": 30, "filter_weight": 70,
        "filter_prompt": "Galaxy AI, 폴더블폰, 애플의 신규 액세서리 소식만 골라내라.",
        "ai_prompt": "삼성전자 기획자 관점 분석: 1.요약 2.영향 3.시사점",
        "category_active": {"Global Innovation": True, "China & East Asia": True, "Japan & Robotics": True},
        "channels": get_initial_channels()
    }
    if os.path.exists(fn):
        with open(fn, "r", encoding="utf-8") as f:
            saved = json.load(f)
            for k, v in default.items():
                if k not in saved: saved[k] = v
            return saved
    return default

def save_user_settings(user_id, settings):
    with open(f"nod_samsung_user_{user_id}.json", "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

# --- 3. 정밀 AI 필터링 엔진 ---
def get_ai_model(api_key):
    try:
        genai.configure(api_key=api_key.strip())
        return genai.GenerativeModel('gemini-1.5-flash')
    except: return None

@st.cache_data(ttl=3600)
def safe_translate(text):
    if not text: return ""
    try: return GoogleTranslator(source='auto', target='ko').translate(text)
    except: return text

def fetch_raw_news(args):
    cat, f, limit = args
    articles = []
    try:
        d = feedparser.parse(f["url"])
        for entry in d.entries[:10]:
            dt = entry.get('published_parsed') or entry.get('updated_parsed')
            if not dt: continue
            p_date = datetime.fromtimestamp(time.mktime(dt))
            if p_date < limit: continue
            articles.append({
                "id": hashlib.md5(entry.link.encode()).hexdigest()[:12],
                "title_en": entry.title, "link": entry.link, "source": f["name"],
                "category": cat, "date_obj": p_date, "date": p_date.strftime("%Y.%m.%d"),
                "summary_en": BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:300]
            })
    except: pass
    return articles

# [핵심] 필터 프롬프트와 가중치를 인자로 받아 캐시를 무효화함
@st.cache_data(ttl=600) 
def get_filtered_news(settings, _prompt, _weight):
    limit = datetime.now() - timedelta(days=settings["sensing_period"])
    active_tasks = [(cat, f, limit) for cat, feeds in settings["channels"].items() 
                    if settings["category_active"].get(cat, True) for f in feeds if f["active"]]
    
    if not active_tasks: return []

    # 1단계: 원시 데이터 수집
    raw_news = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(fetch_raw_news, t) for t in active_tasks]
        for f in as_completed(futures): raw_news.extend(f.result())
    
    # 2단계: AI 점수제 필터링 (수집된 데이터 중 상위 50개만 정밀 분석하여 속도 확보)
    raw_news = sorted(raw_news, key=lambda x: x['date_obj'], reverse=True)[:100]
    model = get_ai_model(settings["api_key"])
    filtered_list = []
    
    if not model or not _prompt: return raw_news

    pb = st.progress(0)
    st_text = st.empty()
    
    for i, item in enumerate(raw_news):
        st_text.caption(f"🎯 프롬프트 기준 기사 필터링 중... ({i+1}/{len(raw_news)})")
        pb.progress((i + 1) / len(raw_news))
        
        try:
            check_query = f"기준: {_prompt}\n뉴스제목: {item['title_en']}\n위 뉴스가 기준에 부합하는 정도를 0~100점 사이 숫자로만 답해."
            res = model.generate_content(check_query).text.strip()
            score = int(''.join(filter(str.isdigit, res)))
        except: score = 50
        
        if score >= _weight:
            item["score"] = score
            item["title_ko"] = safe_translate(item["title_en"])
            item["summary_ko"] = safe_translate(item["summary_en"])
            filtered_list.append(item)
            
    st_text.empty()
    pb.empty()
    return filtered_list

# --- 4. UI 렌더링 ---
st.set_page_config(page_title="NGEPT Hub v14.0", layout="wide")
st.markdown("""<style>
    .insta-card { background: white; border-radius: 20px; border: 1px solid #efefef; margin-bottom: 40px; box-shadow: 0 10px 20px rgba(0,0,0,0.03); }
    .card-img { width: 100%; height: 300px; object-fit: cover; background: #fafafa; }
    .score-label { background: #E3F2FD; color: #1976D2; padding: 2px 10px; border-radius: 10px; font-weight: bold; font-size: 0.8rem; }
</style>""", unsafe_allow_html=True)

with st.sidebar:
    st.title("👤 Strategy Profile")
    u_id = st.radio("사용자", ["1", "2", "3", "4"], horizontal=True)
    if "current_user" not in st.session_state or st.session_state.current_user != u_id:
        st.session_state.current_user = u_id
        st.session_state.settings = load_user_settings(u_id)
        st.rerun()

    st.divider()
    # API 키 수정 기능 유지
    st.subheader("📂 카테고리 관리")
    for cat, feeds in st.session_state.settings["channels"].items():
        st.session_state.settings["category_active"][cat] = st.toggle(f"{cat} ({len(feeds)})", value=st.session_state.settings["category_active"].get(cat, True))

    st.divider()
    with st.expander("⚙️ 고급 필터 및 프롬프트", expanded=True):
        f_prompt = st.text_area("🔍 필터 프롬프트 (바꾸면 즉시 반영)", value=st.session_state.settings["filter_prompt"])
        f_weight = st.slider("🎯 필터 가중치 (최소 점수)", 0, 100, st.session_state.settings["filter_weight"])
        st.session_state.settings["sensing_period"] = st.slider("수집 기간", 1, 30, st.session_state.settings["sensing_period"])
        st.session_state.settings["ai_prompt"] = st.text_area("📝 분석 프롬프트", value=st.session_state.settings["ai_prompt"])

    if st.button("🚀 Apply & Sensing", use_container_width=True, type="primary"):
        st.session_state.settings["filter_prompt"] = f_prompt
        st.session_state.settings["filter_weight"] = f_weight
        save_user_settings(u_id, st.session_state.settings)
        st.cache_data.clear() # 전체 캐시 삭제로 필터 반영 보장
        st.rerun()

# --- 5. 메인 화면 ---
st.markdown("<h1 style='text-align:center;'>NGEPT Strategy Hub</h1>", unsafe_allow_html=True)

# 뉴스 데이터 로드 (프롬프트 정보를 인자로 전달하여 변경 감지)
news_list = get_filtered_news(st.session_state.settings, st.session_state.settings["filter_prompt"], st.session_state.settings["filter_weight"])

if news_list:
    cols = st.columns(3)
    for i, item in enumerate(news_list[:st.session_state.settings["max_articles"]]):
        with cols[i % 3]:
            st.markdown(f"""<div class="insta-card">
                <div style="padding:15px; display:flex; justify-content:space-between; align-items:center;">
                    <b>🌐 {item['source']}</b><span class="score-label">MATCH: {item.get('score', 50)}%</span>
                </div>
                <img src="https://s.wordpress.com/mshots/v1/{item['link']}?w=600" class="card-img">
                <div style="padding:20px;">
                    <div style="font-weight:bold; font-size:1.1rem;">{item.get('title_ko', item['title_en'])}</div>
                    <div style="font-size:0.8rem; color:gray; margin-top:5px;">{item['title_en']}</div>
                    <div style="font-size:0.85rem; color:#444; margin-top:15px;">{item.get('summary_ko', '요약 중...')[:150]}...</div>
                    <br><a href="{item['link']}" target="_blank" style="color:#007AFF; font-weight:bold; text-decoration:none;">🔗 원문 기사 읽기</a>
                </div>
            </div>""", unsafe_allow_html=True)
            if st.button("🔍 Deep Analysis", key=f"btn_{item['id']}", use_container_width=True):
                model = get_ai_model(st.session_state.settings["api_key"])
                st.info(model.generate_content(f"{st.session_state.settings['ai_prompt']}\n제목: {item['title_en']}").text)
else:
    st.info("프롬프트 기준에 맞는 뉴스가 없습니다. 가중치를 낮추거나 프롬프트를 수정해 보세요.")
