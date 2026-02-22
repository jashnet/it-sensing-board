import streamlit as st
import feedparser
import google.generativeai as genai
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timedelta
import time
from deep_translator import GoogleTranslator

# --- 1. 설정 저장 및 로드 ---
SETTINGS_FILE = "nod_pro_settings.json"

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
        "sensing_period": 7,
        # 핵심: AI가 뉴스를 통과시킬지 결정하는 기준
        "filter_prompt": "차세대 경험 기획(Next-Gen Experience) 및 NOD 프로젝트에 영감을 줄 수 있는가? 특히 AI 하드웨어, RTOS 워치, 스크린 없는 포켓 컴퓨팅, 혁신적 UX 시도에 해당하는 뉴스만 'True'로 판별하라. 일반적인 대기업 주가나 단순 SW 업데이트는 'False'로 판별하라.",
        "ai_analysis_prompt": "이 제품/서비스의 UX 변곡점을 분석하고, 우리 팀의 차세대 디바이스 전략에 이식할 수 있는 구체적 아이디어 2개를 제안하라.",
        "channels": {
            "글로벌 (Tech/Design)": [
                {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "active": True},
                {"name": "Wired", "url": "https://www.wired.com/feed/rss", "active": True},
                {"name": "Yanko Design", "url": "https://www.yankodesign.com/feed/", "active": True},
                {"name": "Product Hunt", "url": "https://www.producthunt.com/feed", "active": True},
                {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "active": True}
            ],
            "중국 (AI/Hardware)": [
                {"name": "36Kr", "url": "https://36kr.com/feed", "active": True},
                {"name": "TechNode", "url": "https://technode.com/feed/", "active": True},
                {"name": "Gizmochina", "url": "https://www.gizmochina.com/feed/", "active": True}
            ],
            "일본 (Innovation)": [
                {"name": "The Bridge JP", "url": "https://thebridge.jp/feed", "active": True},
                {"name": "ITmedia News", "url": "https://rss.itmedia.co.jp/rss/2.0/news_bursts.xml", "active": True},
                {"name": "Gizmodo JP", "url": "https://www.gizmodo.jp/index.xml", "active": True}
            ]
        }
    }

def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

if "settings" not in st.session_state:
    st.session_state.settings = load_settings()

# --- 2. UI 스타일 ---
st.set_page_config(page_title="NOD Intelligence Hub", layout="wide")
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; background-color: #f0f2f5; }
    .stAlert { border-radius: 12px; }
    .card {
        background: white; padding: 24px; border-radius: 20px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08); margin-bottom: 24px;
        border: 1px solid #eef0f2; height: 100%;
    }
    .card-title { font-size: 1.1rem; font-weight: 700; color: #1c1e21; margin-bottom: 12px; line-height: 1.5; }
    .card-summary { font-size: 0.9rem; color: #4b4f56; line-height: 1.6; margin-bottom: 15px; }
    .thumbnail { width: 100%; height: 200px; object-fit: cover; border-radius: 12px; margin-bottom: 16px; }
    .badge { background: #e7f3ff; color: #1877f2; padding: 4px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: 700; margin-bottom: 10px; display: inline-block; }
</style>
""", unsafe_allow_html=True)

# --- 3. 핵심 로직: AI 필터링 및 수집 ---
def get_ai_model():
    if not st.session_state.settings["api_key"]: return None
    genai.configure(api_key=st.session_state.settings["api_key"])
    for name in ['gemini-1.5-flash', 'gemini-1.5-flash-latest']:
        try:
            model = genai.GenerativeModel(name)
            return model
        except: continue
    return None

def ai_filter_news(news_list, model):
    if not model: return news_list
    
    filtered = []
    st.write(f"🔄 AI가 {len(news_list)}개의 뉴스를 전략적 기준으로 검토 중...")
    
    for item in news_list:
        prompt = f"기준: {st.session_state.settings['filter_prompt']}\n\n내용: {item['title']}\n결과를 딱 한 단어(True 또는 False)로만 답하라."
        try:
            response = model.generate_content(prompt)
            if "true" in response.text.lower():
                filtered.append(item)
        except:
            filtered.append(item) # 에러 시 일단 포함
    return filtered

@st.cache_data(ttl=3600)
def fetch_sensing_data():
    all_data = []
    limit = datetime.now() - timedelta(days=st.session_state.settings["sensing_period"])
    translator = GoogleTranslator(source='auto', target='ko')

    for cat, feeds in st.session_state.settings["channels"].items():
        for f in feeds:
            if not f["active"]: continue
            d = feedparser.parse(f["url"])
            for entry in d.entries[:8]:
                try:
                    p_date = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    if p_date < limit: continue
                    
                    # 썸네일 추출
                    img = "https://via.placeholder.com/400x250?text=Sensing+Image"
                    if 'media_content' in entry: img = entry.media_content[0]['url']
                    elif 'description' in entry:
                        soup = BeautifulSoup(entry.description, "html.parser")
                        tag = soup.find("img")
                        if tag: img = tag["src"]

                    all_data.append({
                        "title": translator.translate(entry.title),
                        "summary": translator.translate(BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:200]),
                        "img": img, "source": f["name"], "date": p_date.strftime("%m/%d"), "link": entry.link
                    })
                except: continue
    return all_data

# --- 4. 메인 UI ---
with st.sidebar:
    st.title("⚙️ NOD Config")
    if not st.session_state.settings["api_key"]:
        key = st.text_input("Gemini API Key", type="password")
        if st.button("연결 및 저장"):
            st.session_state.settings["api_key"] = key
            save_settings(st.session_state.settings)
            st.rerun()
    else:
        st.success("✅ AI 연결 상태 양호")
        if st.button("Key 재설정"):
            st.session_state.settings["api_key"] = ""
            st.rerun()

    st.divider()
    st.subheader("📁 채널 그룹")
    for cat, feeds in st.session_state.settings["channels"].items():
        with st.expander(f"{cat}"):
            for f in feeds:
                f["active"] = st.checkbox(f["name"], value=f["active"])
            if st.button(f"➕ {cat} 추가", key=f"add_{cat}"):
                st.session_state.adding = cat

    st.divider()
    with st.expander("📝 AI 전략 필터/프롬프트 설정"):
        st.session_state.settings["filter_prompt"] = st.text_area("1. 뉴스 필터링 기준", value=st.session_state.settings["filter_prompt"], height=150)
        st.session_state.settings["ai_analysis_prompt"] = st.text_area("2. Deep-dive 분석 가이드", value=st.session_state.settings["ai_analysis_prompt"], height=150)
        if st.button("설정 저장"):
            save_settings(st.session_state.settings)
            st.toast("전략 기준이 업데이트되었습니다.")

# --- 5. 대시보드 출력 ---
st.title("🚀 NOD Intelligence Dashboard")
raw_news = fetch_sensing_data()

model = get_ai_model()
if model and raw_news:
    # 필터링 수행
    filtered_news = ai_filter_news(raw_news, model)
else:
    filtered_news = raw_news

if filtered_news:
    st.subheader(f"💡 AI가 엄선한 {len(filtered_news)}개의 핵심 신호")
    
    # 3열 그리드 배치
    grid = [filtered_news[i:i + 3] for i in range(0, len(filtered_news), 3)]
    for row in grid:
        cols = st.columns(3)
        for i, item in enumerate(row):
            with cols[i]:
                st.markdown(f"""
                <div class="card">
                    <div class="badge">{item['source']}</div>
                    <img src="{item['img']}" class="thumbnail">
                    <div class="card-title">{item['title']}</div>
                    <div class="card-summary">{item['summary']}...</div>
                    <p style="font-size:0.8rem; color:#888;">{item['date']} | <a href="{item['link']}" target="_blank">원본보기</a></p>
                </div>
                """, unsafe_allow_html=True)
                if st.button("🔍 전략적 Deep-dive", key=f"dd_{item['link'][-10:]}"):
                    with st.spinner("AI 분석 리포트 생성 중..."):
                        analysis = model.generate_content(f"{st.session_state.settings['ai_analysis_prompt']}\n\n뉴스: {item['title']}\n{item['summary']}")
                        st.info(analysis.text)
else:
    st.info("현재 필터링 조건에 맞는 혁신적인 뉴스가 없습니다. 기간이나 채널을 늘려보세요.")
