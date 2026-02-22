import streamlit as st
import feedparser
import google.generativeai as genai
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timedelta
import time

# --- 1. 환경 설정 및 데이터 저장 로직 ---
SETTINGS_FILE = "settings.json"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "api_key": "",
        "pick_filter": "혁신적인 UI/UX, 하드웨어 혁신, AI 에이전트 결합 사례",
        "ai_prompt": "당신은 차세대 경험 기획팀의 수석 전략가입니다. 이 제품의 핵심을 한국어로 요약하고, 우리 회사의 RTOS 워치나 포켓 디바이스 프로젝트에 적용할 구체적 아이디어 2개를 제안하세요.",
        "sensing_period": 14,
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

# --- 2. Material Design 스타일 정의 ---
st.set_page_config(page_title="NOD Sensing Dashboard", layout="wide")
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; background-color: #f8f9fa; }
    .card {
        background: white; padding: 20px; border-radius: 16px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05); margin-bottom: 20px;
        border: 1px solid #efefef;
    }
    .card-title { font-size: 1.1rem; font-weight: 700; color: #1a1b1f; margin-bottom: 10px; }
    .card-summary { font-size: 0.9rem; color: #4e525a; line-height: 1.6; margin-bottom: 15px; }
    .thumbnail { width: 100%; height: 160px; object-fit: cover; border-radius: 10px; margin-bottom: 15px; background: #f0f0f0; }
    .status-tag { padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: bold; }
    .stButton>button { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# --- 3. 사이드바 구성 (Key 관리 & 채널 관리) ---
with st.sidebar:
    st.title("🛡️ NOD 전략 센터")
    
    # API Key Management
    st.subheader("AI 연결 상태")
    if st.session_state.settings["api_key"]:
        st.success("✅ Gemini Key 등록 완료")
        if st.button("Key 수정"):
            st.session_state.settings["api_key"] = ""
            save_settings(st.session_state.settings)
            st.rerun()
    else:
        st.error("❌ Key 미등록")
        new_key = st.text_input("Gemini API Key 입력", type="password")
        if st.button("저장하기"):
            st.session_state.settings["api_key"] = new_key
            save_settings(st.session_state.settings)
            st.rerun()

    st.divider()

    # 계층형 채널 관리
    st.subheader("🌐 센싱 채널 설정")
    for cat, feeds in st.session_state.settings["channels"].items():
        with st.expander(f"📍 {cat}"):
            # 전체 선택/해제
            cat_active = st.checkbox(f"{cat} 전체 선택", value=True, key=f"cat_{cat}")
            
            for i, f in enumerate(feeds):
                f["active"] = st.checkbox(f["name"], value=f["active"] if cat_active else False, key=f"check_{cat}_{i}")
            
            st.markdown("---")
            if st.button(f"➕ {cat}에 채널 추가", key=f"add_{cat}"):
                st.session_state.add_mode = cat

    # 채널 추가 폼 (팝업 형태 시뮬레이션)
    if "add_mode" in st.session_state:
        with st.form("add_channel_form"):
            st.write(f"**[{st.session_state.add_mode}] 새 채널 추가**")
            n_name = st.text_input("사이트 이름")
            n_url = st.text_input("RSS 또는 링크 URL")
            if st.form_submit_button("추가 완료"):
                st.session_state.settings["channels"][st.session_state.add_mode].append({"name": n_name, "url": n_url, "active": True})
                save_settings(st.session_state.settings)
                del st.session_state.add_mode
                st.rerun()

    # 설정 메뉴 (하단)
    st.markdown("<br><br>", unsafe_allow_html=True)
    with st.expander("⚙️ 고급 설정"):
        st.write("🎯 **Pick 필터 기준**")
        st.session_state.settings["pick_filter"] = st.text_area("필터 키워드", value=st.session_state.settings["pick_filter"])
        
        st.write("🤖 **AI 분석 프롬프트**")
        st.session_state.settings["ai_prompt"] = st.text_area("프롬프트 문구", value=st.session_state.settings["ai_prompt"])
        
        st.write("📅 **수집 기간 설정**")
        st.session_state.settings["sensing_period"] = st.slider("최근 며칠간?", 1, 60, st.session_state.settings["sensing_period"])
        
        if st.button("모든 설정 저장"):
            save_settings(st.session_state.settings)
            st.toast("설정이 저장되었습니다!")

# --- 4. 뉴스 수집 및 번역 처리 로직 ---
def fetch_and_process():
    all_news = []
    limit_date = datetime.now() - timedelta(days=st.session_state.settings["sensing_period"])
    
    active_sources = []
    for cat, feeds in st.session_state.settings["channels"].items():
        for f in feeds:
            if f.get("active"): active_sources.append(f)

    for src in active_sources:
        feed = feedparser.parse(src["url"])
        for entry in feed.entries:
            # 날짜 필터링
            pub_date = datetime.fromtimestamp(time.mktime(entry.published_parsed)) if 'published_parsed' in entry else datetime.now()
            if pub_date < limit_date: continue

            # 이미지 추출
            soup = BeautifulSoup(entry.get("summary", ""), "html.parser")
            img = soup.find("img")
            img_url = img["src"] if img else "https://via.placeholder.com/400x250?text=No+Image"
            
            all_news.append({
                "title": entry.title,
                "link": entry.link,
                "summary": BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:150],
                "img": img_url,
                "source": src["name"],
                "date": pub_date.strftime("%Y-%m-%d")
            })
    return all_news

# --- 5. AI 분석 엔진 (한글 번역 및 인사이트) ---
def get_ai_insight(news_item):
    if not st.session_state.settings["api_key"]:
        return "API Key를 먼저 등록해 주세요."
    
    genai.configure(api_key=st.session_state.settings["api_key"])
    model = genai.GenerativeModel('models/gemini-1.5-flash')
    
    prompt = f"""
    내용: 제목({news_item['title']}), 요약({news_item['summary']})
    작업:
    1. 위 내용을 한국어로 번역하고 핵심을 1문장으로 요약할 것.
    2. {st.session_state.settings['ai_prompt']}
    모든 답변은 한국어로 정중하게 작성하세요.
    """
    response = model.generate_content(prompt)
    return response.text

# --- 6. 메인 화면 구성 ---
st.markdown(f"### 🚀 NOD 글로벌 IT 센싱 대시보드")
st.caption(f"기준: 최근 {st.session_state.settings['sensing_period']}일 이내 | 필터: {st.session_state.settings['pick_filter']}")

with st.spinner("최신 뉴스를 가져오는 중..."):
    news_list = fetch_and_process()

if not news_list:
    st.info("조건에 맞는 뉴스가 없습니다. 기간 설정을 조절해 보세요.")
else:
    # 🌟 Best Pick Section
    st.subheader("🔥 Today's Best Pick (AI 추천 기반)")
    top_cols = st.columns(3)
    for i, item in enumerate(news_list[:3]):
        with top_cols[i]:
            st.markdown(f"""
            <div class="card">
                <img src="{item['img']}" class="thumbnail">
                <div class="card-title">{item['title']}</div>
                <div class="card-summary">{item['summary']}...</div>
                <p style='font-size:0.8rem; color:blue;'>Source: {item['source']} | {item['date']}</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"전략 분석 보고서 보기", key=f"btn_top_{i}"):
                with st.expander("📝 AI 인사이트 결과", expanded=True):
                    st.write(get_ai_insight(item))

    st.divider()

    # 📂 전체 스트림 카드뷰
    st.subheader("📋 실시간 센싱 스트림")
    rows = [news_list[i:i + 3] for i in range(3, min(len(news_list), 15), 3)]
    for row in rows:
        cols = st.columns(3)
        for i, item in enumerate(row):
            with cols[i]:
                st.markdown(f"""
                <div class="card">
                    <img src="{item['img']}" class="thumbnail">
                    <div class="card-title" style="font-size:0.95rem;">{item['title']}</div>
                    <a href="{item['link']}" target="_blank" style="text-decoration:none; font-size:0.8rem; color:#1a73e8;">원문 링크 보기</a>
                </div>
                """, unsafe_allow_html=True)
                if st.button(f"AI 분석", key=f"btn_list_{item['link']}"):
                    st.info(get_ai_insight(item))
