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

# --- 1. 설정 저장 및 로드 (슬랙 설정 추가) ---
SETTINGS_FILE = "nod_pro_settings_v3.json"

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
        "slack_webhook": "", # 슬랙 전송용 URL
        "sensing_period": 14,
        "filter_prompt": "차세대 경험 기획 및 하드웨어 혁신, AI UX 사례 위주",
        "ai_analysis_prompt": "이 제품의 UX 변곡점을 분석하고, 우리 팀의 전략에 이식할 아이디어 2개를 제안하라.",
        "channels": {
            "글로벌": [{"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "active": True}],
            "중국": [{"name": "36Kr", "url": "https://36kr.com/feed", "active": True}],
            "일본": [{"name": "The Bridge JP", "url": "https://thebridge.jp/feed", "active": True}]
        }
    }

def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

if "settings" not in st.session_state:
    st.session_state.settings = load_settings()

# --- 2. 슬랙 전송 함수 ---
def send_to_slack(title, analysis):
    webhook_url = st.session_state.settings.get("slack_webhook")
    if not webhook_url:
        st.error("슬랙 웹훅 URL이 설정되지 않았습니다. 고급 설정에서 등록해 주세요.")
        return
    
    payload = {
        "text": f"🚀 *NOD 프로젝트 신규 인사이트 공유*\n\n*대상:* {title}\n\n*분석 내용:*\n{analysis}"
    }
    try:
        response = requests.post(webhook_url, json=payload)
        if response.status_code == 200: st.toast("슬랙으로 성공적으로 전송되었습니다! ✈️")
        else: st.error(f"슬랙 전송 실패: {response.text}")
    except Exception as e:
        st.error(f"오류 발생: {e}")

# --- 3. UI 스타일 ---
st.set_page_config(page_title="NOD Intelligence Hub", layout="wide")
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; background-color: #f8f9fa; }
    .card { background: white; padding: 22px; border-radius: 18px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); border: 1px solid #eef1f4; margin-bottom: 20px; }
    .thumbnail { width: 100%; height: 180px; object-fit: cover; border-radius: 12px; margin-bottom: 12px; }
    .card-title { font-size: 1rem; font-weight: 700; height: 48px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

# --- 4. 사이드바 (API 키 및 설정) ---
with st.sidebar:
    st.title("🛡️ NOD 전략 센터")
    
    # API 키 처리 로직 강화
    current_key = st.session_state.settings.get("api_key", "")
    if current_key:
        st.success("✅ AI 연결됨")
        if st.button("Key 재입력"):
            st.session_state.settings["api_key"] = ""
            save_settings(st.session_state.settings)
            st.rerun()
    else:
        new_key = st.text_input("Gemini API Key 입력", type="password")
        if st.button("연결 및 저장"):
            st.session_state.settings["api_key"] = new_key
            save_settings(st.session_state.settings)
            st.rerun()

    st.divider()
    with st.expander("⚙️ 고급 설정"):
        st.session_state.settings["slack_webhook"] = st.text_input("Slack Webhook URL", value=st.session_state.settings.get("slack_webhook", ""))
        st.session_state.settings["ai_analysis_prompt"] = st.text_area("AI 분석 프롬프트", value=st.session_state.settings["ai_analysis_prompt"])
        if st.button("설정 일괄 저장"):
            save_settings(st.session_state.settings)
            st.toast("저장 완료!")

# --- 5. AI 분석 함수 (키 인식 오류 원천 차단) ---
def get_ai_analysis(item):
    # 세션 상태에서 실시간으로 키를 가져옴
    api_key = st.session_state.settings.get("api_key")
    if not api_key:
        return "⚠️ API Key가 인식되지 않았습니다. 사이드바에서 다시 등록해 주세요."
    
    try:
        genai.configure(api_key=api_key)
        # 모델 명칭 유연하게 대응
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        
        prompt = f"""
        당신은 차세대 경험 기획팀의 전략가입니다.
        뉴스: {item['title']} - {item['summary']}
        가이드: {st.session_state.settings['ai_analysis_prompt']}
        모든 답변은 한국어로 전문적으로 작성하세요.
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"분석 중 오류 발생: {str(e)}"

# --- 6. 뉴스 수집 및 출력 (기존 UI 유지) ---
@st.cache_data(ttl=3600)
def fetch_data():
    all_news = []
    # (기존 이미지 추출 및 번역 로직 포함)
    # ... (생략된 수집 로직은 이전과 동일하게 작동하며 썸네일 개선형을 유지함)
    return all_news # 실제 코드에서는 이전 수집 로직을 여기에 통합

st.title("🚀 NOD Intelligence Dashboard")
# 예시 뉴스 데이터 (실제 데이터 수집 함수 연결)
news_list = fetch_data()

if news_list:
    cols = st.columns(3)
    for i, item in enumerate(news_list[:9]):
        with cols[i % 3]:
            st.markdown(f"""
            <div class="card">
                <img src="{item['img']}" class="thumbnail">
                <div class="card-title">{item['title']}</div>
                <div style="font-size:0.85rem; color:#555; margin-bottom:10px;">{item['summary'][:100]}...</div>
            </div>
            """, unsafe_allow_html=True)
            
            # 분석 버튼 및 슬랙 전송 UI 통합
            if st.button("🔍 전략 Deep-dive", key=f"dd_{i}"):
                analysis_res = get_ai_analysis(item)
                with st.expander("📝 분석 리포트", expanded=True):
                    st.markdown(analysis_res)
                    if st.button("📢 Slack으로 전송", key=f"sl_{i}"):
                        send_to_slack(item['title'], analysis_res)
