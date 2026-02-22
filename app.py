import streamlit as st
import feedparser
import google.generativeai as genai
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timedelta
import time
from deep_translator import GoogleTranslator

# --- 1. 환경 설정 및 데이터 저장 로직 ---
SETTINGS_FILE = "settings.json"

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
        height: 100%; dplsay: flex; flex-direction: column;
    }
    .card-title { font-size: 1.0rem; font-weight: 700; color: #1a1b1f; margin-bottom: 10px; line-height: 1.4; height: 45px; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
    .card-summary { font-size: 0.85rem; color: #4e525a; line-height: 1.5; margin-bottom: 15px; height: 65px; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;}
    .thumbnail { width: 100%; height: 160px; object-fit: cover; border-radius: 10px; margin-bottom: 15px; background: #f0f0f0; }
    .source-tag { font-size: 0.75rem; color: #888; margin-bottom: 10px; }
    .stButton>button { border-radius: 8px; width: 100%; }
</style>
""", unsafe_allow_html=True)

# --- 3. 사이드바 구성 ---
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
            cat_active = st.checkbox(f"{cat} 전체 선택", value=True, key=f"cat_{cat}")
            for i, f in enumerate(feeds):
                f["active"] = st.checkbox(f["name"], value=f["active"] if cat_active else False, key=f"check_{cat}_{i}")
            st.markdown("---")
            if st.button(f"➕ {cat}에 채널 추가", key=f"add_{cat}"):
                st.session_state.add_mode = cat

    # 채널 추가 폼
    if "add_mode" in st.session_state:
        with st.form("add_channel_form"):
            st.write(f"**[{st.session_state.add_mode}] 새 채널 추가**")
            n_name = st.text_input("사이트 이름")
            n_url = st.text_input("RSS URL")
            if st.form_submit_button("추가 완료"):
                st.session_state.settings["channels"][st.session_state.add_mode].append({"name": n_name, "url": n_url, "active": True})
                save_settings(st.session_state.settings)
                del st.session_state.add_mode
                st.rerun()

    # 설정 메뉴
    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("⚙️ 고급 설정"):
        st.write("🎯 **Pick 필터 기준**")
        st.session_state.settings["pick_filter"] = st.text_area("필터 키워드", value=st.session_state.settings["pick_filter"], height=70)
        st.write("🤖 **AI 분석 프롬프트**")
        st.session_state.settings["ai_prompt"] = st.text_area("프롬프트 문구", value=st.session_state.settings["ai_prompt"], height=100)
        st.write("📅 **수집 기간 설정**")
        st.session_state.settings["sensing_period"] = st.slider("최근 며칠간?", 1, 60, st.session_state.settings["sensing_period"])
        if st.button("모든 설정 저장"):
            save_settings(st.session_state.settings)
            st.toast("설정이 저장되었습니다!")

# --- 4. 헬퍼 함수: 썸네일 추출 및 번역 ---
def get_safe_thumbnail(entry):
    # 1. media_content 확인 (가장 현대적인 표준)
    if 'media_content' in entry and len(entry.media_content) > 0:
        return entry.media_content[0]['url']
    # 2. media_thumbnail 확인
    if 'media_thumbnail' in entry and len(entry.media_thumbnail) > 0:
        return entry.media_thumbnail[0]['url']
    # 3. enclosure 확인 (팟캐스트 등)
    if 'enclosures' in entry and len(entry.enclosures) > 0:
         for enclosure in entry.enclosures:
            if enclosure.get('type', '').startswith('image/'):
                return enclosure.get('href')
    # 4. 본문 내 이미지 태그 검색
    content_html = entry.get("summary", "") or entry.get("description", "")
    soup = BeautifulSoup(content_html, "html.parser")
    img = soup.find("img")
    if img and img.get("src"):
        return img["src"]
    # 5. 대체 이미지
    return "https://via.placeholder.com/400x250?text=No+Image+Found"

def quick_translate(text):
    # 너무 짧거나 비어있으면 번역 스킵
    if not text or len(text) < 5: return text
    try:
        # auto -> korean 번역 시도
        translated = GoogleTranslator(source='auto', target='ko').translate(text)
        return translated
    except:
        return text # 실패시 원문 반환

# --- 5. 뉴스 수집 및 처리 로직 ---
@st.cache_data(ttl=3600) # 1시간 캐시 적용 (속도 향상)
def fetch_and_process():
    all_news = []
    limit_date = datetime.now() - timedelta(days=st.session_state.settings["sensing_period"])
    active_sources = []
    for cat, feeds in st.session_state.settings["channels"].items():
        for f in feeds:
            if f.get("active"): active_sources.append(f)

    progress_bar = st.progress(0)
    total_sources = len(active_sources)
    
    for i, src in enumerate(active_sources):
        try:
            feed = feedparser.parse(src["url"])
            # 각 소스당 최신 5개만 처리 (속도 고려)
            for entry in feed.entries[:5]:
                pub_date = datetime.fromtimestamp(time.mktime(entry.published_parsed)) if 'published_parsed' in entry else datetime.now()
                if pub_date < limit_date: continue

                # 썸네일 추출 (개선된 로직)
                img_url = get_safe_thumbnail(entry)

                # 요약문 정제 및 번역 (개선된 로직)
                raw_summary = entry.get("summary", "") or entry.get("description", "")
                clean_text = BeautifulSoup(raw_summary, "html.parser").get_text()[:250] # 일단 좀 길게 가져옴
                translated_summary = quick_translate(clean_text)
                final_summary = translated_summary[:130] + "..." if len(translated_summary) > 130 else translated_summary
                
                all_news.append({
                    "title": entry.title,
                    "link": entry.link,
                    "summary": final_summary, # 번역된 요약 적용
                    "img": img_url,
                    "source": src["name"],
                    "date": pub_date.strftime("%Y-%m-%d"),
                    "raw_entry": entry # AI 분석용 원본 데이터 저장
                })
        except Exception as e:
            print(f"Error fetching {src['name']}: {e}")
        progress_bar.progress((i + 1) / total_sources)
    
    progress_bar.empty()
    # 최신순 정렬
    all_news.sort(key=lambda x: x['date'], reverse=True)
    return all_news

# --- 6. AI 분석 엔진 (에러 방지 강화 버전) ---
def get_ai_insight(news_item):
    if not st.session_state.settings["api_key"]:
        return "API Key를 먼저 등록해 주세요."
    
    try:
        genai.configure(api_key=st.session_state.settings["api_key"])
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            model.generate_content("test")
        except:
            model = genai.GenerativeModel('models/gemini-1.5-flash')

        # AI에게는 더 풍부한 정보를 제공 (원본 제목 + 번역된 요약)
        prompt = f"""
        당신은 차세대 경험 기획팀의 수석 전략가입니다.
        [대상 뉴스]
        제목: {news_item['title']}
        출처: {news_item['source']}
        내용 요약(한글): {news_item['summary']}
        
        [지시사항]
        1. 이 뉴스의 핵심 내용을 한국어로 명확하게 다시 한번 요약하세요.
        2. {st.session_state.settings['ai_prompt']}
        
        모든 답변은 한국어로 전문적이고 정중하게 작성하며, 마크다운 형식을 사용하여 가독성을 높이세요.
        """
        
        with st.spinner("AI가 전략을 분석 중입니다..."):
            response = model.generate_content(prompt)
        return response.text
        
    except Exception as e:
        return f"AI 분석 중 오류가 발생했습니다. (원인: {str(e)})\n잠시 후 다시 시도하거나 API 키를 확인해 주세요."

# --- 7. 메인 화면 구성 ---
st.markdown(f"### 🚀 NOD 글로벌 IT 센싱 대시보드")
st.caption(f"기준: 최근 {st.session_state.settings['sensing_period']}일 이내 | 자동 한글 번역 적용됨")

news_list = fetch_and_process()

if not news_list:
    st.info("조건에 맞는 뉴스가 없습니다. 기간 설정을 조절하거나 채널을 확인해 주세요.")
else:
    # 🌟 Best Pick Section (상위 3개)
    st.subheader("🔥 Today's Best Pick")
    top_cols = st.columns(3)
    for i, item in enumerate(news_list[:3]):
        with top_cols[i]:
            st.markdown(f"""
            <div class="card">
                <img src="{item['img']}" class="thumbnail">
                <div class="source-tag">{item['source']} | {item['date']}</div>
                <div class="card-title">{item['title']}</div>
                <div class="card-summary">{item['summary']}</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"✨ 전략 분석 보고서", key=f"btn_top_{i}"):
                with st.expander("📝 AI 인사이트 결과", expanded=True):
                    st.markdown(get_ai_insight(item))

    st.divider()

    # 📂 전체 스트림 카드뷰 (그리드)
    st.subheader("📋 실시간 센싱 스트림")
    rows = [news_list[i:i + 4] for i in range(3, len(news_list), 4)] # 한 줄에 4개씩
    for row in rows:
        cols = st.columns(4)
        for i, item in enumerate(row):
            with cols[i]:
                st.markdown(f"""
                <div class="card">
                    <img src="{item['img']}" class="thumbnail">
                    <div class="source-tag">{item['source']}</div>
                    <div class="card-title" style="font-size:0.9rem;">{item['title']}</div>
                    <div class="card-summary" style="-webkit-line-clamp: 2;">{item['summary']}</div>
                    <a href="{item['link']}" target="_blank" style="text-decoration:none; font-size:0.8rem; color:#1a73e8; margin-top:auto;">원문 링크 보기</a>
                </div>
                """, unsafe_allow_html=True)
                if st.button(f"AI 분석", key=f"btn_list_{i}_{item['link'][-10:]}"):
                   with st.expander("AI 분석 결과", expanded=True):
                       st.markdown(get_ai_insight(item))
