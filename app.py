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

# --- 1. 설정 및 기본값 (완화된 필터 프롬프트 포함) ---
SETTINGS_FILE = "nod_samsung_v6_settings.json"
DEFAULT_API_KEY = "AIzaSyCW7kwkCqCSN-usKFG9gwcPzYlHwtQW_DQ"

def default_settings():
    return {
        "api_key": DEFAULT_API_KEY,
        "slack_webhook": "",
        "sensing_period": 7,
        # 필터 조건 완화: '가급적 수집' 방향으로 수정
        "filter_prompt": """당신은 삼성전자의 차세대 경험기획 전문가입니다. 
        글로벌 테크 산업의 흐름을 폭넓게 파악하기 위해, 새로운 기술 시도, 스타트업의 신제품, 대기업의 전략적 움직임, UX/UI 디자인 트렌드에 해당하는 뉴스를 가급적 수집하세요. 
        완전히 무관한 주식 지표나 일반적인 인물 동정, 단순 홍보성 기사만 제외하고 '혁신'의 실마리가 있다면 'True'로 판별하세요.""",
        "ai_prompt": """삼성전자(Samsung) 기획자 관점에서 3단계 분석을 수행하라:
        a) Fact Summary: 핵심 요약.
        b) 3-Year Future Impact: 향후 3년 내 스마트폰/웨어러블 시장 및 사용자 행태에 미칠 변화 예측.
        c) Samsung Takeaway: 삼성 제품/경험 혁신을 위한 제언.""",
        "channels": {
            "Global Innovation": [
                {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "active": True},
                {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "active": True},
                {"name": "Wired", "url": "https://www.wired.com/feed/rss", "active": True},
                {"name": "Product Hunt", "url": "https://www.producthunt.com/feed", "active": True},
                {"name": "Yanko Design", "url": "https://www.yankodesign.com/feed/", "active": True}
            ],
            "China/Japan Hardware": [
                {"name": "36Kr (CN)", "url": "https://36kr.com/feed", "active": True},
                {"name": "Gizmochina", "url": "https://www.gizmochina.com/feed/", "active": True},
                {"name": "The Bridge (JP)", "url": "https://thebridge.jp/feed", "active": True}
            ]
        }
    }

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return default_settings()
    return default_settings()

def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

if "settings" not in st.session_state:
    st.session_state.settings = load_settings()

# --- 2. 강력한 이미지 엔진 (Screenshot API 연동) ---
def get_bulletproof_thumbnail(entry):
    link = entry.get('link')
    
    # 1. RSS 표준 태그
    if 'media_content' in entry: return entry.media_content[0]['url']
    if 'media_thumbnail' in entry: return entry.media_thumbnail[0]['url']
    
    # 2. Open Graph 추출
    if link:
        try:
            res = requests.get(link, timeout=1.0)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                og_img = soup.find("meta", property="og:image")
                if og_img: return og_img["content"]
        except: pass

    # 3. 썸네일이 없을 경우 웹사이트 실시간 스크린샷 서비스 이용 (WordPress mshot API)
    # 이미지 누락 시 해당 기사 페이지의 첫 화면을 보여줍니다.
    if link:
        return f"https://s.wordpress.com/mshots/v1/{link}?w=600"

    return "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=600&q=80"

def natural_translate(text):
    if not text: return ""
    try: return GoogleTranslator(source='auto', target='ko').translate(text)
    except: return text

# --- 3. UI 스타일 ---
st.set_page_config(page_title="Samsung NOD Center", layout="wide")
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap');
    body { font-family: 'Noto Sans KR', sans-serif; background-color: #f4f7fa; }
    .top-card { background: white; padding: 22px; border-radius: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); border-top: 5px solid #034EA2; height: 100%; display: flex; flex-direction: column; }
    .thumbnail { width: 100%; height: 190px; object-fit: cover; border-radius: 14px; margin-bottom: 12px; background-color: #eee; }
    .title-ko { font-size: 1.05rem; font-weight: 700; color: #1a1c1e; line-height: 1.4; margin-bottom: 6px; }
    .title-en { font-size: 0.8rem; color: #888; font-style: italic; margin-bottom: 12px; }
    .badge { background: #eef2ff; color: #034EA2; padding: 4px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: 700; margin-bottom: 10px; display: inline-block; }
</style>
""", unsafe_allow_html=True)

# --- 4. 사이드바 (API 키 UI 개선) ---
with st.sidebar:
    st.title("🛡️ NOD Control")
    
    # API 키 관리 UI: 입력된 경우 버튼만 표시
    if "edit_key" not in st.session_state: st.session_state.edit_key = False
    
    if st.session_state.settings["api_key"] and not st.session_state.edit_key:
        st.success("✅ Gemini Key 등록됨")
        if st.button("키 수정"):
            st.session_state.edit_key = True
            st.rerun()
    else:
        new_key = st.text_input("Gemini API Key 입력", value=st.session_state.settings["api_key"], type="password")
        if st.button("저장 및 적용"):
            st.session_state.settings["api_key"] = new_key
            st.session_state.edit_key = False
            save_settings(st.session_state.settings)
            st.rerun()

    st.divider()
    # 채널 관리 및 고급 설정
    for cat, feeds in st.session_state.settings["channels"].items():
        with st.expander(cat):
            for f in feeds:
                f["active"] = st.checkbox(f["name"], value=f["active"], key=f"ch_{f['name']}")

    st.divider()
    with st.expander("⚙️ 고급 설정"):
        st.session_state.settings["filter_prompt"] = st.text_area("필터 기준", value=st.session_state.settings["filter_prompt"], height=100)
        st.session_state.settings["ai_prompt"] = st.text_area("분석 가이드", value=st.session_state.settings["ai_prompt"], height=100)
        st.session_state.settings["sensing_period"] = st.slider("수집 기간(일)", 1, 30, st.session_state.settings["sensing_period"])
        if st.button("설정 일괄 저장"):
            save_settings(st.session_state.settings)
            st.toast("저장되었습니다.")

# --- 5. 데이터 엔진 (중복 키 에러 방지 포함) ---
def get_ai_model():
    try:
        genai.configure(api_key=st.session_state.settings["api_key"])
        return genai.GenerativeModel('gemini-1.5-flash-latest')
    except: return None

@st.cache_data(ttl=3600)
def fetch_sensing_data():
    all_news = []
    limit = datetime.now() - timedelta(days=st.session_state.settings["sensing_period"])
    model = get_ai_model()

    for cat, feeds in st.session_state.settings["channels"].items():
        for f in feeds:
            if not f.get("active"): continue
            d = feedparser.parse(f["url"])
            for entry in d.entries[:10]:
                try:
                    p_date = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    if p_date < limit: continue
                    
                    if model:
                        check = model.generate_content(f"기준: {st.session_state.settings['filter_prompt']}\n제목: {entry.title}\n부합하면 'True', 아니면 'False'만 답해.")
                        if "true" not in check.text.lower(): continue

                    # 중복 에러 방지를 위한 고유 ID 생성 (링크 해싱)
                    unique_id = hashlib.md5(entry.link.encode()).hexdigest()[:12]

                    all_news.append({
                        "id": unique_id,
                        "title_en": entry.title,
                        "title_ko": natural_translate(entry.title),
                        "summary_ko": natural_translate(BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:250]),
                        "img": get_bulletproof_thumbnail(entry),
                        "source": f["name"], "category": cat,
                        "date": p_date.strftime("%m/%d"), "link": entry.link
                    })
                except: continue
    all_news.sort(key=lambda x: x['date'], reverse=True)
    return all_news

# --- 6. 대시보드 메인 ---
st.title("🚀 Samsung NOD Strategy Center")
news_data = fetch_sensing_data()

if news_data:
    # 🌟 Top Pick 6 (Card View)
    st.subheader("🌟 Top Strategic Picks")
    top_6 = news_data[:6]
    grid = [top_6[i:i+3] for i in range(0, len(top_6), 3)]
    for row_idx, row in enumerate(grid):
        cols = st.columns(3)
        for col_idx, item in enumerate(row):
            with cols[col_idx]:
                st.markdown(f"""
                <div class="top-card">
                    <div class="badge">{item['source']} | {item['date']}</div>
                    <img src="{item['img']}" class="thumbnail">
                    <div class="title-ko">{item['title_ko']}</div>
                    <div class="title-en">{item['title_en']}</div>
                    <div style="font-size:0.85rem; color:#515458; height:60px; overflow:hidden; margin-bottom:10px;">{item['summary_ko']}...</div>
                    <p style="font-size:0.75rem; margin-top:auto;"><a href="{item['link']}" target="_blank">🔗 원본 기사 읽기</a></p>
                </div>
                """, unsafe_allow_html=True)
                # 고유 해시 ID를 키로 사용하여 중복 에러 해결
                if st.button("🔍 Deep-dive", key=f"top_btn_{item['id']}"):
                    model = get_ai_model()
                    with st.spinner("분석 중..."):
                        res = model.generate_content(f"{st.session_state.settings['ai_prompt']}\n내용: {item['title_en']} - {item['summary_ko']}")
                        st.info(res.text)

    st.divider()

    # 📋 Sensing Stream
    st.subheader("📋 Sensing Stream")
    for item in news_data[6:]:
        with st.container():
            col_img, col_txt = st.columns([1, 4])
            with col_img:
                st.image(item['img'], use_container_width=True)
            with col_txt:
                st.markdown(f"""
                <div class="badge">{item['category']} | {item['source']} | {item['date']}</div>
                <div class="title-ko">{item['title_ko']}</div>
                <div class="title-en">{item['title_en']}</div>
                <div style="font-size:0.85rem; margin-bottom:10px;">{item['summary_ko']}...</div>
                <a href="{item['link']}" target="_blank" style="font-size:0.8rem; color:#034EA2; text-decoration:none;">🔗 원본 기사 보기</a>
                """, unsafe_allow_html=True)
                if st.button("Quick Analysis", key=f"list_btn_{item['id']}"):
                    model = get_ai_model()
                    res = model.generate_content(f"{st.session_state.settings['ai_prompt']}\n내용: {item['title_en']} - {item['summary_ko']}")
                    st.success(res.text)
            st.markdown("---")
else:
    st.info("조건에 맞는 혁신 뉴스가 없습니다.")
