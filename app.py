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

# --- 1. 설정 저장 및 로드 로직 ---
SETTINGS_FILE = "nod_master_settings.json"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return default_settings()
    return default_settings()

def default_settings():
    return {
        "api_key": "",
        "slack_webhook": "",
        "sensing_period": 7,
        "filter_prompt": "차세대 경험 기획(NOD)에 영감을 주는 AI 하드웨어, 혁신적 UX, 로보틱스, 웨어러블 뉴스만 포함할 것.",
        "ai_prompt": "이 제품의 혁신 포인트를 분석하고 우리 팀의 전략적 적용 방향 2가지를 제안하라.",
        "channels": {
            "글로벌 (Global)": [
                {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "active": True},
                {"name": "Wired", "url": "https://www.wired.com/feed/rss", "active": True},
                {"name": "Yanko Design", "url": "https://www.yankodesign.com/feed/", "active": True}
            ],
            "중국 (China)": [
                {"name": "36Kr", "url": "https://36kr.com/feed", "active": True},
                {"name": "TechNode", "url": "https://technode.com/feed/", "active": True}
            ],
            "일본 (Japan)": [
                {"name": "The Bridge JP", "url": "https://thebridge.jp/feed", "active": True},
                {"name": "Gizmodo JP", "url": "https://www.gizmodo.jp/index.xml", "active": True}
            ]
        }
    }

def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

if "settings" not in st.session_state:
    st.session_state.settings = load_settings()

# --- 2. 썸네일 복구 로직 (The Verge 및 메타태그 대응) ---
@st.cache_data(ttl=3600)
def get_robust_thumbnail(link, entry_summary):
    # 1. RSS 자체 태그 확인
    soup_rss = BeautifulSoup(entry_summary, "html.parser")
    img_tag = soup_rss.find("img")
    if img_tag and img_tag.get("src"): return img_tag["src"]

    # 2. 웹페이지 직접 방문 (Open Graph 확인) - The Verge 등 해결
    try:
        res = requests.get(link, timeout=2)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            og_img = soup.find("meta", property="og:image")
            if og_img: return og_img["content"]
    except: pass
    
    return "https://via.placeholder.com/600x400/1a73e8/ffffff?text=NOD+Sensing"

# --- 3. 슬랙 전송 및 AI 분석 함수 ---
def send_to_slack(title, analysis):
    url = st.session_state.settings.get("slack_webhook")
    if not url:
        st.error("슬랙 웹훅 URL을 설정해 주세요.")
        return
    payload = {"text": f"📢 *NOD 인사이트 공유*\n\n*주제:* {title}\n\n*분석 내용:*\n{analysis}"}
    requests.post(url, json=payload)
    st.toast("슬랙 전송 완료!")

def get_ai_analysis(item):
    api_key = st.session_state.settings.get("api_key")
    if not api_key: return "❌ API 키를 사이드바에 먼저 등록해 주세요."
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        prompt = f"뉴스: {item['title']}\n내용: {item['summary']}\n\n지시사항: {st.session_state.settings['ai_prompt']}"
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"분석 에러: {str(e)}"

# --- 4. UI 스타일링 ---
st.set_page_config(page_title="NOD Intelligence Hub", layout="wide")
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; background-color: #f8f9fa; }
    .card { background: white; padding: 20px; border-radius: 15px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); margin-bottom: 20px; border: 1px solid #eee; }
    .thumbnail { width: 100%; height: 180px; object-fit: cover; border-radius: 10px; margin-bottom: 15px; }
    .card-title { font-size: 1.05rem; font-weight: 700; color: #1a202c; height: 50px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

# --- 5. 사이드바 (설정 관리) ---
with st.sidebar:
    st.title("🛡️ NOD 전략 센터")
    
    # API 키 상태 표시 및 수정
    if st.session_state.settings["api_key"]:
        st.success("✅ Gemini AI 연결됨")
        if st.button("API Key 수정"):
            st.session_state.settings["api_key"] = ""
            st.rerun()
    else:
        new_key = st.text_input("Gemini API Key 입력", type="password")
        if st.button("Key 저장"):
            st.session_state.settings["api_key"] = new_key
            save_settings(st.session_state.settings)
            st.rerun()

    st.divider()
    st.subheader("🌐 채널 및 카테고리")
    for cat, feeds in st.session_state.settings["channels"].items():
        with st.expander(f"📍 {cat}"):
            for i, f in enumerate(feeds):
                f["active"] = st.checkbox(f["name"], value=f["active"], key=f"ch_{cat}_{i}")
    
    st.divider()
    with st.expander("⚙️ 고급 설정"):
        st.session_state.settings["slack_webhook"] = st.
