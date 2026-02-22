import streamlit as st
import feedparser
import google.generativeai as genai
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timedelta
import time
from deep_translator import GoogleTranslator

# --- 1. 설정 저장 및 로드 로직 ---
SETTINGS_FILE = "nod_settings.json"

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
        "pick_filter": "혁신적인 UI/UX, 하드웨어 혁신, AI 에이전트 결합 사례",
        "ai_prompt": "이 제품의 핵심을 한국어로 요약하고, 우리 회사의 RTOS 워치나 포켓 디바이스 프로젝트에 적용할 구체적 아이디어 2개를 제안하세요.",
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

# --- 2. UI 스타일 (Material Design) ---
st.set_page_config(page_title="NOD Sensing Dashboard", layout="wide")
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; background-color: #f4f7f9; }
    .card {
        background: white; padding: 20px; border-radius: 16px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05); margin-bottom: 20px;
        border: 1px solid #e1e4e8; height: 100%; display: flex; flex-direction: column;
    }
    .card-title { font-size: 1.05rem; font-weight: 700; color: #1a202c; margin-bottom: 12px; line-height: 1.4; }
    .card-summary { font-size: 0.9rem; color: #4a5568; line-height: 1.6; margin-bottom: 15px; flex-grow: 1; }
    .thumbnail { width: 100%; height: 180px; object-fit: cover; border-radius: 12px; margin-bottom: 15px; background: #edf2f7; }
    .source-info { font-size: 0.8rem; color: #718096; margin-bottom: 8px; font-weight: 500; }
    .stButton>button { width: 100%; border-radius: 10px; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# --- 3. 헬퍼 함수 (이미지 & 번역) ---
def get_thumbnail(entry):
    # 다양한 RSS 이미지 태그 시도
    if 'media_content' in entry: return entry.media_content[0]['url']
    if 'media_thumbnail' in entry: return entry.media_thumbnail[0]['url']
    soup = BeautifulSoup(entry.get("summary", "") or entry.get("description", ""), "html.parser")
    img = soup.find("img")
    if img and img.get("src"): return img["src"]
    return "https://via.placeholder.com/400x250?text=No+Image"

def translate_ko(text):
    if not text: return ""
    try: return GoogleTranslator(source='auto', target='ko').translate(text)
    except: return text

# --- 4. 사이드바 (Key 관리 & 드롭다운 채널) ---
with st.sidebar:
    st.title("🛡️ NOD 전략 센터")
    
    # API Key Management (수정/저장 로직)
    if st.session_state.settings["api_key"]:
        st.success("✅ AI 연결됨")
        if st.button("🔑 API Key 수정"):
            st.session_state.settings["api_key"] = ""
            st.rerun()
    else:
        st.warning("🔑 Gemini Key가 필요합니다")
        new_key = st.text_input("Key 입력", type="password")
        if st.button("Key 저장"):
            st.session_state.settings["api_key"] = new_key
            save_settings(st.session_state.settings)
            st.rerun()

    st.divider()

    # 드롭다운 채널 관리
    st.subheader("🌐 센싱 채널")
    for cat, feeds in st.session_state.settings["channels"].items():
        with st.expander(f"📍 {cat}"):
            for i, f in enumerate(feeds):
                f["active"] = st.checkbox(f["name"], value=f["active"], key=f"ch_{cat}_{i}")
            
            # 채널 추가 항목
            if st.button(f"➕ {cat} 채널 추가", key=f"btn_add_{cat}"):
                st.session_state.add_target = cat

    if "add_target" in st.session_state:
        with st.form("add_form"):
            st.info(f"{st.session_state.add_target} 카테고리에 추가")
            n_name = st.text_input("이름 (예: 인스타그램 IT리뷰)")
            n_url = st.text_input("RSS URL (또는 소스 링크)")
            if st.form_submit_button("추가 완료"):
                st.session_state.settings["channels"][st.session_state.add_target].append({"name": n_name, "url": n_url, "active": True})
                save_settings(st.session_state.settings)
                del st.session_state.add_target
                st.rerun()

    st.divider()
    with st.expander("⚙️ 고급 설정"):
        st.session_state.settings["pick_filter"] = st.text_area("필터 기준", value=st.session_state.settings["pick_filter"])
        st.session_state.settings["ai_prompt"] = st.text_area("AI 프롬프트", value=st.session_state.settings["ai_prompt"])
        st.session_state.settings["sensing_period"] = st.slider("기간(일)", 1, 60, st.session_state.settings["sensing_period"])
        if st.button("설정 일괄 저장"):
            save_settings(st.session_state.settings)
            st.toast("저장 완료!")

# --- 5. AI 분석 엔진 (에러 완전 방어형) ---
def get_ai_analysis(item):
    if not st.session_state.settings["api_key"]: return "키를 입력해주세요."
    
    try:
        genai.configure(api_key=st.session_state.settings["api_key"])
        
        # 404 에러 방지를 위해 가장 확실한 모델 명칭 순차 시도
        model_names = ['gemini-1.5-flash', 'gemini-1.5-flash-latest', 'models/gemini-1.5-flash']
        model = None
        for name in model_names:
            try:
                model = genai.GenerativeModel(name)
                # 모델 연결 테스트
                model.generate_content("test", generation_config={"max_output_tokens": 1})
                break
            except: continue
        
        if not model: return "지원되는 AI 모델을 찾을 수 없습니다. API 키 권한을 확인해 주세요."

        prompt = f"""
        당신은 IT 전략 분석가입니다. 아래 뉴스를 한국어로 상세 분석하세요.
        제목: {item['title']}
        요약: {item['summary']}
        
        지시사항:
        1. 전체 내용을 한국어로 3문장 요약.
        2. {st.session_state.settings['ai_prompt']}
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"분석 실패: {str(e)}"

# --- 6. 뉴스 처리 및 메인 UI ---
@st.cache_data(ttl=3600)
def get_news():
    news_data = []
    limit = datetime.now() - timedelta(days=st.session_state.settings["sensing_period"])
    
    for cat, feeds in st.session_state.settings["channels"].items():
        for f in feeds:
            if not f["active"]: continue
            d = feedparser.parse(f["url"])
            for entry in d.entries[:5]:
                try:
                    p_date = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    if p_date < limit: continue
                    
                    # 제목/요약 한글화
                    title_ko = translate_ko(entry.title)
                    summary_ko = translate_ko(BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:200])
                    
                    news_data.append({
                        "title": title_ko,
                        "summary": summary_ko,
                        "img": get_thumbnail(entry),
                        "source": f["name"],
                        "date": p_date.strftime("%Y-%m-%d"),
                        "link": entry.link
                    })
                except: continue
    return news_data

st.title("🚀 NOD Global IT Sensing")
with st.spinner("뉴스를 번역하고 수집하는 중..."):
    data = get_news()

if data:
    # Best Pick (Top 3)
    st.subheader("⭐ Today's Best Pick")
    b_cols = st.columns(3)
    for i, item in enumerate(data[:3]):
        with b_cols[i]:
            st.markdown(f'<div class="card"><img src="{item["img"]}" class="thumbnail"><div class="source-info">{item["source"]} | {item["date"]}</div><div class="card-title">{item["title"]}</div><div class="card-summary">{item["summary"][:120]}...</div></div>', unsafe_allow_html=True)
            if st.button("📝 전략 분석", key=f"b_{i}"):
                st.info(get_ai_analysis(item))

    st.divider()
    
    # Stream Grid
    st.subheader("📋 실시간 센싱 스트림")
    grid = [data[i:i+4] for i in range(3, len(data), 4)]
    for row in grid:
        cols = st.columns(4)
        for i, item in enumerate(row):
            with cols[i]:
                st.markdown(f'<div class="card"><img src="{item["img"]}" class="thumbnail"><div class="source-info">{item["source"]}</div><div class="card-title" style="font-size:0.9rem;">{item["title"]}</div><div class="card-summary" style="font-size:0.8rem;">{item["summary"][:80]}...</div><a href="{item["link"]}" target="_blank" style="font-size:0.75rem; color:#1a73e8;">원문보기</a></div>', unsafe_allow_html=True)
                if st.button("분석", key=f"s_{item['link'][-10:]}"):
                    st.write(get_ai_analysis(item))
else:
    st.info("조건에 맞는 뉴스가 없습니다.")
