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

# --- 1. 설정 및 기본값 (개선된 필터 및 개수 설정 포함) ---
SETTINGS_FILE = "nod_samsung_v7_settings.json"
DEFAULT_API_KEY = "AIzaSyCW7kwkCqCSN-usKFG9gwcPzYlHwtQW_DQ"

def default_settings():
    return {
        "api_key": DEFAULT_API_KEY,
        "slack_webhook": "",
        "sensing_period": 7,
        "filter_prompt": "삼성전자의 차세대 경험기획에 영감을 주는 혁신 기술 및 UX 사례.",
        "additional_filter": "",
        "filter_strength": 3,
        "max_articles": 20,
        "category_active": {"Global Innovation (23)": True, "China AI/HW (11)": True, "Japan Innovation (11)": True},
        "channels": {
            "Global Innovation (23)": [
                {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "active": True},
                {"name": "Wired", "url": "https://www.wired.com/feed/rss", "active": True}
            ],
            "China AI/HW (11)": [{"name": "36Kr (CN)", "url": "https://36kr.com/feed", "active": True}],
            "Japan Innovation (11)": [{"name": "The Bridge JP", "url": "https://thebridge.jp/feed", "active": True}]
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

# --- 2. 유틸리티 함수 (이미지, 번역, AI 모델) ---
def get_bulletproof_thumbnail(link):
    if not link: return "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=600&q=80"
    # 썸네일 없으면 실시간 스크린샷 서비스 이용
    return f"https://s.wordpress.com/mshots/v1/{link}?w=600"

def natural_translate(text):
    if not text: return ""
    try: return GoogleTranslator(source='auto', target='ko').translate(text)
    except: return text

def get_ai_model():
    try:
        genai.configure(api_key=st.session_state.settings["api_key"])
        return genai.GenerativeModel('gemini-1.5-flash-latest')
    except: return None

# --- 3. UI 스타일 ---
st.set_page_config(page_title="Samsung NOD Hub v7", layout="wide")
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap');
    body { font-family: 'Noto Sans KR', sans-serif; background-color: #f4f7fa; }
    .stButton>button { border-radius: 8px; width: 100%; }
    .card { background: white; padding: 22px; border-radius: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); height: 100%; border-top: 5px solid #034EA2; }
    .thumbnail { width: 100%; height: 180px; object-fit: cover; border-radius: 12px; margin-bottom: 12px; border: 1px solid #eee; }
</style>
""", unsafe_allow_html=True)

# --- 4. 사이드바 (필터링 및 채널 관리 고도화) ---
with st.sidebar:
    st.title("🛡️ NOD 전략 관제")
    
    # API 키 관리
    if "edit_key" not in st.session_state: st.session_state.edit_key = False
    if st.session_state.settings["api_key"] and not st.session_state.edit_key:
        st.success("AI 연결됨")
        if st.button("키 수정"): st.session_state.edit_key = True; st.rerun()
    else:
        new_key = st.text_input("Gemini API Key", value=st.session_state.settings["api_key"], type="password")
        if st.button("저장"): st.session_state.settings["api_key"] = new_key; st.session_state.edit_key = False; save_settings(st.session_state.settings); st.rerun()

    st.divider()
    
    # 채널 그룹 On/Off 및 추가
    st.subheader("🌐 채널 그룹 관리")
    for cat in list(st.session_state.settings["channels"].keys()):
        is_on = st.toggle(f"{cat} 활성화", value=st.session_state.settings["category_active"].get(cat, True), key=f"tg_{cat}")
        st.session_state.settings["category_active"][cat] = is_on
        
        if is_on:
            with st.expander(f"{cat} 채널 목록"):
                for f in st.session_state.settings["channels"][cat]:
                    f["active"] = st.checkbox(f["name"], value=f["active"], key=f"ch_{f['name']}")
                
                st.markdown("---")
                st.caption("➕ 채널 추가")
                with st.form(key=f"add_form_{cat}"):
                    n_name = st.text_input("이름")
                    n_url = st.text_input("RSS URL")
                    if st.form_submit_button("추가"):
                        st.session_state.settings["channels"][cat].append({"name": n_name, "url": n_url, "active": True})
                        save_settings(st.session_state.settings); st.rerun()

    st.divider()
    
    # 고급 필터 설정
    st.subheader("⚙️ 필터 시스템")
    st.session_state.settings["filter_prompt"] = st.text_area("기본 뉴스 필터", value=st.session_state.settings["filter_prompt"])
    st.session_state.settings["additional_filter"] = st.text_area("Additional Filter (가중치 키워드)", value=st.session_state.settings.get("additional_filter", ""), help="여기에 적힌 내용을 중심으로 한 번 더 필터링합니다.")
    
    st.session_state.settings["filter_strength"] = st.slider("Filter 강도 (1:낮음 ~ 5:엄격)", 1, 5, st.session_state.settings["filter_strength"])
    st.session_state.settings["max_articles"] = st.selectbox("표시 기사 개수", [10, 20, 30, 50], index=[10, 20, 30, 50].index(st.session_state.settings.get("max_articles", 20)))
    
    if st.button("🚀 Apply & Refresh", use_container_width=True):
        save_settings(st.session_state.settings)
        st.cache_data.clear() # 캐시 삭제 후 리프레시
        st.rerun()

# --- 5. 데이터 엔진 (Sorting/Filtering 로직 포함) ---
@st.cache_data(ttl=3600)
def fetch_sensing_data(settings):
    all_news = []
    limit = datetime.now() - timedelta(days=settings["sensing_period"])
    model = get_ai_model()
    
    # 강도에 따른 AI 지시문 조절
    strength_map = {1: "관련이 조금이라도 있다면 포함", 2: "적당히 포함", 3: "관련성 위주로 필터", 4: "엄격하게 필터", 5: "매우 밀접한 뉴스만 엄선"}
    
    for cat, feeds in settings["channels"].items():
        if not settings["category_active"].get(cat): continue
        for f in feeds:
            if not f.get("active"): continue
            d = feedparser.parse(f["url"])
            for entry in d.entries[:15]: # 수집은 넉넉하게
                try:
                    p_date = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    if p_date < limit: continue
                    
                    relevance_score = 5 # 기본 점수
                    if model:
                        # 필터링 + 관련도 점수 측정
                        filter_query = f"""
                        [기준] {settings['filter_prompt']} 
                        [추가 가중치] {settings['additional_filter']}
                        [강도] {strength_map[settings['filter_strength']]}
                        [뉴스 제목] {entry.title}
                        결과를 '유효여부(True/False),관련점수(1-10)' 형식으로만 답해. 예: True,8
                        """
                        check = model.generate_content(filter_query).text.strip()
                        if "true" not in check.lower(): continue
                        try: relevance_score = int(check.split(",")[1])
                        except: relevance_score = 5

                    all_news.append({
                        "id": hashlib.md5(entry.link.encode()).hexdigest()[:12],
                        "title_en": entry.title,
                        "title_ko": natural_translate(entry.title),
                        "summary": natural_translate(BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:250]),
                        "img": get_bulletproof_thumbnail(entry.link),
                        "source": f["name"], "category": cat,
                        "date": p_date, "score": relevance_score, "link": entry.link
                    })
                except: continue
    return all_news

# --- 6. 대시보드 메인 제어 ---
st.title("🚀 Samsung NOD Strategy Hub v7")
data = fetch_sensing_data(st.session_state.settings)

if data:
    # 상단 컨트롤 바 (본문 내 정렬/필터)
    c1, c2, c3 = st.columns([2, 2, 2])
    with c1:
        sort_option = st.selectbox("📅 정렬 기준", ["최신순", "과거순", "AI 관련도 높은 순"])
    with c2:
        filter_cat = st.multiselect("📂 카테고리 필터", list(st.session_state.settings["channels"].keys()), default=list(st.session_state.settings["channels"].keys()))
    with c3:
        search_query = st.text_input("🔍 결과 내 검색", "")

    # 정렬 및 필터 적용
    filtered_data = [d for d in data if d["category"] in filter_cat]
    if search_query:
        filtered_data = [d for d in filtered_data if search_query.lower() in d["title_ko"].lower() or search_query.lower() in d["title_en"].lower()]
    
    if sort_option == "최신순": filtered_data.sort(key=lambda x: x["date"], reverse=True)
    elif sort_option == "과거순": filtered_data.sort(key=lambda x: x["date"])
    else: filtered_data.sort(key=lambda x: x["score"], reverse=True)

    # 개수 제한 적용
    display_data = filtered_data[:st.session_state.settings["max_articles"]]

    # 결과 출력
    st.subheader(f"📊 검색 결과: {len(display_data)}개 기사")
    
    # Top 6 (최상단)
    top_6 = display_data[:6]
    grid = [top_6[i:i+3] for i in range(0, len(top_6), 3)]
    for row in grid:
        cols = st.columns(3)
        for j, item in enumerate(row):
            with cols[j]:
                st.markdown(f"""
                <div class="card">
                    <div style="font-size:0.75rem; color:#034EA2; font-weight:700;">{item['category']} | {item['source']}</div>
                    <img src="{item['img']}" class="thumbnail">
                    <div style="font-weight:700; margin-bottom:5px;">{item['title_ko']}</div>
                    <div style="font-size:0.85rem; color:#555; height:60px; overflow:hidden;">{item['summary']}...</div>
                    <p style="font-size:0.75rem; margin-top:10px;"><a href="{item['link']}" target="_blank">🔗 원본 보기</a></p>
                </div>
                """, unsafe_allow_html=True)
                if st.button("🔍 전략 Deep-dive", key=f"btn_{item['id']}"):
                    model = get_ai_model()
                    with st.spinner("분석 중..."):
                        res = model.generate_content(f"{st.session_state.settings['ai_prompt']}\n내용: {item['title_en']}")
                        st.info(res.text)

    st.divider()

    # Sensing Stream (하단 리스트)
    for item in display_data[6:]:
        with st.container():
            c_img, c_txt = st.columns([1, 4])
            with c_img: st.image(item['img'])
            with c_txt:
                st.markdown(f"**{item['title_ko']}** ({item['date'].strftime('%m/%d')})")
                st.caption(f"Source: {item['source']} | AI Score: {item['score']}")
                st.write(f"{item['summary']}...")
                st.markdown(f"[🔗 원본 링크]({item['link']})")
                if st.button("Quick View", key=f"q_{item['id']}"):
                    st.success(get_ai_model().generate_content(f"요약해줘: {item['title_en']}").text)
            st.markdown("---")
else:
    st.info("조건에 맞는 혁신 뉴스가 없습니다. 사이드바 설정을 확인해 주세요.")
