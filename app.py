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
        st.session_state.settings["sensing_period"] = st.slider("수집 기간(일)", 1, 30, st.session_state.settings["sensing_period"])
        
        if st.button("모든 설정 일괄 저장"):
            save_settings(st.session_state.settings)
            st.toast("전략 기준이 저장되었습니다! 💾")

# --- 5. 뉴스 데이터 수집 및 AI 필터링 ---
@st.cache_data(ttl=3600)
def fetch_and_filter():
    results = []
    limit = datetime.now() - timedelta(days=st.session_state.settings["sensing_period"])
    translator = GoogleTranslator(source='auto', target='ko')
    
    # 1단계: 전체 뉴스 수집
    temp_list = []
    for cat, feeds in st.session_state.settings["channels"].items():
        for f in feeds:
            if not f.get("active"): continue
            d = feedparser.parse(f["url"])
            for entry in d.entries[:10]:
                try:
                    p_date = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    if p_date < limit: continue
                    temp_list.append({
                        "title_en": entry.title,
                        "summary_en": BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:300],
                        "link": entry.link, "source": f["name"], "date": p_date.strftime("%m/%d"),
                        "raw_entry": entry
                    })
                except: continue

    # 2단계: AI 모델 로드 (필터링용)
    model = get_ai_model()
    st.write(f"🔄 AI가 {len(temp_list)}개의 뉴스를 전략적 가치로 선별 중...")
    
    # 3단계: 필터링 및 번역
    for item in temp_list:
        if model:
            # 필터 프롬프트를 사용하여 노출 여부 결정
            filter_check = model.generate_content(f"기준: {st.session_state.settings['filter_prompt']}\n\n뉴스 제목: {item['title_en']}\n위 기준에 부합하면 'Yes', 아니면 'No'라고만 답해.")
            if "yes" not in filter_check.text.lower(): continue

        # 통과된 뉴스만 번역 및 이미지 추출
        results.append({
            "title": translator.translate(item['title_en']),
            "summary": translator.translate(item['summary_en'][:150]),
            "img": get_robust_thumbnail(item['raw_entry']),
            "source": item['source'], "date": item['date'], "link": item['link']
        })
    return results

# --- 6. 메인 화면 ---
st.title("🚀 NOD Intelligence Hub")
news_data = fetch_and_filter()

model = get_ai_model()

if news_data:
    rows = [news_data[i:i + 3] for i in range(0, len(news_data), 3)]
    for row in rows:
        cols = st.columns(3)
        for j, item in enumerate(row):
            with cols[j]:
                st.markdown(f"""
                <div class="card">
                    <div class="badge">{item['source']} | {item['date']}</div>
                    <img src="{item['img']}" class="thumbnail">
                    <div class="card-title">{item['title']}</div>
                    <div style="font-size:0.85rem; color:#515458; height:60px; overflow:hidden;">{item['summary']}...</div>
                </div>
                """, unsafe_allow_html=True)
                
                if st.button("🔍 전략 Deep-dive", key=f"btn_{item['link'][-15:]}"):
                    if model:
                        with st.spinner("분석 중..."):
                            # 분석 프롬프트를 사용하여 리포트 생성
                            prompt = f"{st.session_state.settings['ai_analysis_prompt']}\n\n대상: {item['title']} - {item['summary']}"
                            res = model.generate_content(prompt)
                            st.info(res.text)
                            
                            # 슬랙 전송 (고급 설정에 URL 있을 때만)
                            if st.session_state.settings.get("slack_webhook"):
                                if st.button("📢 슬랙 공유", key=f"sl_{item['link'][-15:]}"):
                                    requests.post(st.session_state.settings["slack_webhook"], json={"text": f"*NOD 인사이트:* {item['title']}\n{res.text}"})
                                    st.toast("슬랙 전송 완료!")
                    else: st.warning("키 등록이 필요합니다.")
else:
    st.info("현재 필터 기준에 맞는 혁신적인 뉴스가 없습니다. '고급 설정'에서 필터 프롬프트를 조정해 보세요.")
