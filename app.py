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

# --- 1. 설정 저장 및 로드 ---
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
        "sensing_period": 14,
        "ai_analysis_prompt": "이 제품/서비스의 UX 변곡점을 분석하고, 우리 팀의 차세대 디바이스 전략에 이식할 수 있는 구체적 아이디어 2개를 제안하라.",
        "channels": {
            "글로벌 (Tech/Design)": [
                {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "active": True},
                {"name": "Wired", "url": "https://www.wired.com/feed/rss", "active": True},
                {"name": "Yanko Design", "url": "https://www.yankodesign.com/feed/", "active": True}
            ],
            "중국 (AI/Hardware)": [
                {"name": "36Kr", "url": "https://36kr.com/feed", "active": True},
                {"name": "TechNode", "url": "https://technode.com/feed/", "active": True}
            ],
            "일본 (Innovation)": [
                {"name": "The Bridge JP", "url": "https://thebridge.jp/feed", "active": True},
                {"name": "ITmedia News", "url": "https://rss.itmedia.co.jp/rss/2.0/news_bursts.xml", "active": True}
            ]
        }
    }

def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

if "settings" not in st.session_state:
    st.session_state.settings = load_settings()

# --- 2. 썸네일 완벽 복구 (The Verge 등 메타데이터 대응) ---
def get_robust_thumbnail(entry):
    if 'media_content' in entry: return entry.media_content[0]['url']
    link = entry.get('link')
    if link:
        try:
            res = requests.get(link, timeout=1.5)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                og_img = soup.find("meta", property="og:image")
                if og_img: return og_img["content"]
        except: pass
    return f"https://via.placeholder.com/600x400/1a73e8/ffffff?text=NOD+Sensing"

# --- 3. 슬랙 전송 함수 ---
def send_to_slack(title, analysis):
    url = st.session_state.settings.get("slack_webhook")
    if not url:
        st.error("슬랙 웹훅 URL을 설정해 주세요.")
        return
    payload = {"text": f"📢 *NOD 인사이트 공유*\n\n*주제:* {title}\n\n*분석 리포트:*\n{analysis}"}
    requests.post(url, json=payload)
    st.toast("슬랙 전송 완료! 🚀")

# --- 4. UI 스타일 정의 ---
st.set_page_config(page_title="NOD Intelligence Hub", layout="wide")
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; background-color: #f8f9fa; }
    .card { background: white; padding: 22px; border-radius: 18px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); border: 1px solid #eef1f4; margin-bottom: 20px; }
    .thumbnail { width: 100%; height: 190px; object-fit: cover; border-radius: 12px; margin-bottom: 12px; }
    .card-title { font-size: 1rem; font-weight: 700; height: 48px; overflow: hidden; color: #1a1c1e; }
    .card-summary { font-size: 0.85rem; color: #515458; height: 60px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

# --- 5. 사이드바 (설정 관리) ---
with st.sidebar:
    st.title("🛡️ NOD 전략 센터")
    
    # API 키 처리
    if st.session_state.settings.get("api_key"):
        st.success("✅ AI 연결됨")
        if st.button("Key 수정"):
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
    st.subheader("🌐 채널 관리")
    for cat, feeds in st.session_state.settings["channels"].items():
        with st.expander(cat):
            for f in feeds:
                f["active"] = st.checkbox(f["name"], value=f["active"], key=f"ch_{f['name']}")

    st.divider()
    with st.expander("⚙️ 고급 설정"):
        st.session_state.settings["slack_webhook"] = st.text_input("Slack Webhook URL", value=st.session_state.settings.get("slack_webhook", ""))
        st.session_state.settings["ai_analysis_prompt"] = st.text_area("분석 프롬프트", value=st.session_state.settings["ai_analysis_prompt"])
        if st.button("일괄 저장"):
            save_settings(st.session_state.settings)
            st.toast("저장 완료!")

# --- 6. 뉴스 수집 및 메인 화면 ---
@st.cache_data(ttl=3600)
def fetch_news():
    results = []
    limit = datetime.now() - timedelta(days=st.session_state.settings["sensing_period"])
    translator = GoogleTranslator(source='auto', target='ko')

    for cat, feeds in st.session_state.settings["channels"].items():
        for f in feeds:
            if not f.get("active"): continue
            d = feedparser.parse(f["url"])
            for entry in d.entries[:7]:
                try:
                    p_date = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    if p_date < limit: continue
                    results.append({
                        "title": translator.translate(entry.title),
                        "summary": translator.translate(BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:150]),
                        "img": get_robust_thumbnail(entry),
                        "source": f["name"],
                        "date": p_date.strftime("%m/%d"),
                        "link": entry.link
                    })
                except: continue
    results.sort(key=lambda x: x['date'], reverse=True)
    return results

# --- 7. AI 분석 모델 호출 (에러 해결 핵심 로직) ---
def get_ai_response(prompt):
    api_key = st.session_state.settings.get("api_key")
    if not api_key: return "API Key가 없습니다."
    
    genai.configure(api_key=api_key)
    
    # NotFound 에러를 방지하기 위해 사용 가능한 모델 명칭을 순차적으로 시도합니다.
    model_variants = ["models/gemini-1.5-flash", "gemini-1.5-flash"]
    
    for model_name in model_variants:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            if "not_found" in str(e).lower() or "404" in str(e):
                continue # 다음 모델 이름으로 시도
            return f"에러 발생: {str(e)}"
    
    return "지원되는 Gemini 모델을 찾을 수 없습니다. API 설정을 확인해주세요."

st.title("🚀 NOD Intelligence Dashboard")
news_data = fetch_news()

if news_data:
    rows = [news_data[i:i + 3] for i in range(0, len(news_data), 3)]
    for row in rows:
        cols = st.columns(3)
        for i, item in enumerate(row):
            with cols[i]:
                st.markdown(f"""
                <div class="card">
                    <div style="font-size:0.75rem; color:#1a73e8; font-weight:700; margin-bottom:8px;">{item['source']} | {item['date']}</div>
                    <img src="{item['img']}" class="thumbnail">
                    <div class="card-title">{item['title']}</div>
                    <div class="card-summary">{item['summary']}...</div>
                </div>
                """, unsafe_allow_html=True)
                
                if st.button("🔍 전략 Deep-dive", key=f"btn_{item['link'][-15:]}"):
                    with st.spinner("AI 분석 리포트 생성 중..."):
                        prompt = f"{st.session_state.settings['ai_analysis_prompt']}\n\n내용: {item['title']} - {item['summary']}"
                        analysis_text = get_ai_response(prompt)
                        st.info(analysis_text)
                        
                        # 슬랙 전송 버튼
                        if st.button("📢 슬랙으로 공유", key=f"sl_{item['link'][-15:]}"):
                            send_to_slack(item['title'], analysis_text)
else:
    st.info("뉴스를 수집 중이거나 조건에 맞는 데이터가 없습니다.")
