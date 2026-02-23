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

# --- 1. 설정 및 로드 (프롬프트 이원화) ---
SETTINGS_FILE = "nod_v4_settings.json"

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
        # 프롬프트 1: 뉴스 노출 여부를 결정하는 필터 기준
        "filter_prompt": "차세대 경험 기획(NOD)에 영감을 주는 AI 하드웨어, 혁신적 UX, 웨어러블 뉴스만 포함할 것. 단순 주식 뉴스나 일반 SW 업데이트는 제외.",
        # 프롬프트 2: Deep-dive 분석의 형식을 결정하는 기준
        "ai_analysis_prompt": "이 제품의 UX 변곡점을 분석하고, 우리 팀의 전략에 이식할 수 있는 구체적 아이디어 2개를 제안하라.",
        "channels": {
            "글로벌": [{"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "active": True},
                     {"name": "Wired", "url": "https://www.wired.com/feed/rss", "active": True}],
            "중국": [{"name": "36Kr", "url": "https://36kr.com/feed", "active": True}],
            "일본": [{"name": "The Bridge JP", "url": "https://thebridge.jp/feed", "active": True}]
        }
    }

def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

if "settings" not in st.session_state:
    st.session_state.settings = load_settings()

# --- 2. 썸네일 및 유틸리티 함수 ---
def get_robust_thumbnail(entry):
    if 'media_content' in entry: return entry.media_content[0]['url']
    link = entry.get('link')
    if link:
        try:
            res = requests.get(link, timeout=1.0)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                og_img = soup.find("meta", property="og:image")
                if og_img: return og_img["content"]
        except: pass
    return f"https://via.placeholder.com/600x400/1a73e8/ffffff?text=NOD+Sensing"

def get_ai_model():
    api_key = st.session_state.settings.get("api_key")
    if not api_key: return None
    try:
        genai.configure(api_key=api_key)
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        target = next((m for m in available_models if "1.5-flash" in m), available_models[0])
        return genai.GenerativeModel(target)
    except: return None

# --- 3. UI 및 스타일링 ---
st.set_page_config(page_title="NOD Intelligence Hub", layout="wide")
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; background-color: #f8f9fa; }
    .card { background: white; padding: 22px; border-radius: 18px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); border: 1px solid #eef1f4; margin-bottom: 20px; }
    .thumbnail { width: 100%; height: 180px; object-fit: cover; border-radius: 12px; margin-bottom: 12px; }
    .card-title { font-size: 1rem; font-weight: 700; height: 48px; overflow: hidden; color: #1a1c1e; }
    .badge { background: #f0f4ff; color: #1a73e8; padding: 4px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: 700; margin-bottom: 10px; display: inline-block; }
</style>
""", unsafe_allow_html=True)

# --- 4. 사이드바 (개편된 프롬프트 설정) ---
with st.sidebar:
    st.title("🛡️ NOD 전략 센터")
    
    if st.session_state.settings.get("api_key"):
        st.success("✅ AI 가동 중")
        if st.button("Key 변경"): st.session_state.settings["api_key"] = ""; st.rerun()
    else:
        new_key = st.text_input("Gemini API Key 입력", type="password")
        if st.button("연결"): 
            st.session_state.settings["api_key"] = new_key
            save_settings(st.session_state.settings); st.rerun()

    st.divider()
    st.subheader("🌐 채널 관리")
    for cat, feeds in st.session_state.settings["channels"].items():
        with st.expander(cat):
            for f in feeds:
                f["active"] = st.checkbox(f["name"], value=f["active"], key=f"ch_{f['name']}")

    st.divider()
    with st.expander("⚙️ 고급 프롬프트 설정"):
        st.markdown("### 1️⃣ 뉴스 필터 프롬프트")
        st.caption("어떤 뉴스를 대시보드에 노출할지 결정합니다.")
        st.session_state.settings["filter_prompt"] = st.text_area("필터 기준", value=st.session_state.settings["filter_prompt"], height=100)
        
        st.markdown("### 2️⃣ AI 분석 프롬프트")
        st.caption("Deep-dive 리포트의 분석 관점을 결정합니다.")
        st.session_state.settings["ai_analysis_prompt"] = st.text_area("분석 가이드", value=st.session_state.settings["ai_analysis_prompt"], height=100)
        
        st.markdown("### 📅 수집 환경")
        st.session_state.settings["slack_webhook"] = st.text_input("Slack Webhook URL", value=st.session_state.settings.get("slack_webhook", ""))
        st.session_state.settings["sensing_period"] = st.slider("수집 기간(일)", 1, 30, st.session_state.settings["
