import streamlit as st
import feedparser
import google.generativeai as genai
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timedelta
import time
from deep_translator import GoogleTranslator

# --- 1. 설정 및 로드 ---
SETTINGS_FILE = "nod_pro_settings_v2.json"

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
        "sensing_period": 14,
        "filter_prompt": "차세대 경험 기획(Next-Gen Experience) 및 NOD 프로젝트에 영감을 줄 수 있는가? 특히 AI 하드웨어, RTOS 워치, 스크린 없는 포켓 컴퓨팅, 혁신적 UX 시도에 해당하는 뉴스만 'True'로 판별하라.",
        "ai_analysis_prompt": "이 제품/서비스의 UX 변곡점을 분석하고, 우리 팀의 차세대 디바이스 전략에 이식할 수 있는 구체적 아이디어 2개를 제안하라.",
        "channels": {
            "글로벌 (Tech/Design)": [
                {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "active": True},
                {"name": "Wired", "url": "https://www.wired.com/feed/rss", "active": True},
                {"name": "Yanko Design", "url": "https://www.yankodesign.com/feed/", "active": True},
                {"name": "Product Hunt", "url": "https://www.producthunt.com/feed", "active": True}
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

# --- 2. 강화된 썸네일 추출 로직 (The Image Rescue) ---
def get_robust_thumbnail(entry):
    """5단계에 걸쳐 이미지를 탐색하여 최선의 결과를 반환합니다."""
    # 1단계: 표준 media_content 태그 확인
    if 'media_content' in entry and len(entry.media_content) > 0:
        return entry.media_content[0]['url']
    
    # 2단계: media_thumbnail 또는 media_image 확인
    if 'media_thumbnail' in entry and len(entry.media_thumbnail) > 0:
        return entry.media_thumbnail[0]['url']
    if 'media_image' in entry:
        return entry.media_image

    # 3단계: enclosure(파일 첨부) 확인
    if 'enclosures' in entry and len(entry.enclosures) > 0:
        for enc in entry.enclosures:
            if enc.get('type', '').startswith('image/'):
                return enc.get('href')

    # 4단계: HTML 본문(summary 또는 description) 내부 <img> 태그 파싱
    content_html = entry.get("summary", "") or entry.get("description", "")
    if content_html:
        soup = BeautifulSoup(content_html, "html.parser")
        img_tag = soup.find("img")
        if img_tag and img_tag.get("src"):
            src = img_tag["src"]
            # 1x1 픽셀 같은 트래킹용 이미지는 제외
            if "tracker" not in src and "stat" not in src:
                return src

    # 5단계: 최종 실패 시 - 깔끔한 테크 디자인 플레이스홀더 반환
    # (제목의 첫 글자를 따서 생성하는 placeholder 서비스 이용)
    return f"https://via.placeholder.com/600x400/1a73e8/ffffff?text=NOD+Sensing"

# --- 3. UI 및 스타일 ---
st.set_page_config(page_title="NOD Intelligence Hub", layout="wide")
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; background-color: #f4f6f9; }
    .card {
        background: white; padding: 22px; border-radius: 20px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.06); margin-bottom: 24px;
        border: 1px solid #eef1f4; height: 100%; display: flex; flex-direction: column;
    }
    .card-title { font-size: 1.1rem; font-weight: 700; color: #1a1c1e; margin-bottom: 12px; line-height: 1.4; height: 50px; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
    .card-summary { font-size: 0.9rem; color: #515458; line-height: 1.6; margin-bottom: 15px; flex-grow: 1; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; }
    .thumbnail { width: 100%; height: 190px; object-fit: cover; border-radius: 14px; margin-bottom: 16px; background-color: #eee; }
    .badge { background: #f0f4ff; color: #1a73e8; padding: 4px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: 700; margin-bottom: 10px; display: inline-block; }
</style>
""", unsafe_allow_html=True)

# --- 4. 데이터 처리 엔진 ---
def get_ai_model():
    if not st.session_state.settings["api_key"]: return None
    genai.configure(api_key=st.session_state.settings["api_key"])
    for name in ['gemini-1.5-flash', 'gemini-1.5-flash-latest']:
        try:
            model = genai.GenerativeModel(name)
            model.generate_content("test", generation_config={"max_output_tokens": 1})
            return model
        except: continue
    return None

@st.cache_data(ttl=3600)
def fetch_sensing_data():
    all_data = []
    limit = datetime.now() - timedelta(days=st.session_state.settings["sensing_period"])
    translator = GoogleTranslator(source='auto', target='ko')

    for cat, feeds in st.session_state.settings["channels"].items():
        for f in feeds:
            if not f["active"]: continue
            d = feedparser.parse(f["url"])
            for entry in d.entries[:10]:
                try:
                    p_date = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    if p_date < limit: continue
                    
                    # 제목/요약 한글 번역
                    title_ko = translator.translate(entry.title)
                    summary_raw = BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:250]
                    summary_ko = translator.translate(summary_raw)

                    all_data.append({
                        "title": title_ko,
                        "summary": summary_ko,
                        "img": get_robust_thumbnail(entry), # 개선된 로직 적용
                        "source": f["name"],
                        "date": p_date.strftime("%m/%d"),
                        "link": entry.link
                    })
                except: continue
    all_data.sort(key=lambda x: x['date'], reverse=True)
    return all_data

# --- 5. 사이드바 및 메인 화면 ---
with st.sidebar:
    st.title("🛡️ NOD 전략 센터")
    if st.session_state.settings["api_key"]:
        st.success("✅ AI 가동 중")
        if st.button("Key 변경"): st.session_state.settings["api_key"] = ""; st.rerun()
    else:
        new_key = st.text_input("Gemini API Key", type="password")
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
    with st.expander("⚙️ 고급 설정"):
        st.session_state.settings["filter_prompt"] = st.text_area("필터 기준", value=st.session_state.settings["filter_prompt"])
        st.session_state.settings["ai_analysis_prompt"] = st.text_area("분석 프롬프트", value=st.session_state.settings["ai_analysis_prompt"])
        if st.button("설정 저장"):
            save_settings(st.session_state.settings)
            st.toast("저장되었습니다.")

st.title("🚀 NOD Intelligence Dashboard")
news_data = fetch_sensing_data()

model = get_ai_model()
if news_data:
    # 3열 배치
    rows = [news_data[i:i + 3] for i in range(0, len(news_data), 3)]
    for row in rows:
        cols = st.columns(3)
        for i, item in enumerate(row):
            with cols[i]:
                st.markdown(f"""
                <div class="card">
                    <div class="badge">{item['source']} | {item['date']}</div>
                    <img src="{item['img']}" class="thumbnail">
                    <div class="card-title">{item['title']}</div>
                    <div class="card-summary">{item['summary']}...</div>
                    <p style="font-size:0.8rem;"><a href="{item['link']}" target="_blank">원본 기사 보기</a></p>
                </div>
                """, unsafe_allow_html=True)
                if st.button("🔍 전략 Deep-dive", key=f"btn_{item['link'][-10:]}"):
                    if model:
                        with st.spinner("AI 분석 중..."):
                            res = model.generate_content(f"{st.session_state.settings['ai_analysis_prompt']}\n\n내용: {item['title']} - {item['summary']}")
                            st.info(res.text)
                    else: st.warning("API Key를 등록해주세요.")
else:
    st.info("뉴스를 수집 중이거나 조건에 맞는 데이터가 없습니다.")
