import streamlit as st
import feedparser
import google.generativeai as genai
from bs4 import BeautifulSoup
import json
import os
import re
from datetime import datetime, timedelta
import time
from deep_translator import GoogleTranslator
import requests
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================
# 💎 [Gems 연동 1] 수석 전략 분석가 페르소나 (심층 분석용)
# ==========================================
GEMS_PERSONA = """
귀하는 글로벌 빅테크 기업의 '차세대 경험기획팀' 소속 수석 전략 분석가입니다.
향후 2~3년 내 상용화될 신규 스마트 디바이스와 혁신적 UX/UI를 기획하기 위해 시장의 '초기 시그널'을 센싱하는 것이 목적입니다.

[분석 필수 포함 항목]
1. 혁신성: 기존 제품 대비 경험의 변화가 얼마나 큰가?
2. 파급력: 전체 에코시스템에 어떤 변화를 주는가?
3. 기획적 가치: 우리 팀의 차세대 제품 기획(NOD 프로젝트)에 어떤 영감을 주는가?
"""

# ==========================================
# 🧠 [Gems 연동 2] 예시 학습(Few-Shot) 필터링 프롬프트 (기본값)
# ==========================================
DEFAULT_FILTER_PROMPT = """귀하는 차세대경험기획팀의 'NOD 프로젝트' 전용 뉴스 필터링 에이전트입니다.
주어진 뉴스의 제목과 요약을 보고, 우리 팀의 기획 방향과 일치하는지 0~100점으로 평가하세요.

[평가 기준]
- 90~100점: 완전히 새로운 폼팩터, 혁신적 UX, 스마트 링/AR 글래스/신경 인터페이스(EMG) 등 하드웨어 시도, 공간 컴퓨팅, 에이전틱 AI, 주요 빅테크의 핵심 특허.
- 60~89점: 기존 폼팩터의 성능 향상(AP, 배터리 등), 일반적인 웨어러블/스마트폰 신제품 출시.
- 0~59점: 단순 루머, 주식/재무 뉴스, 우리 기획과 무관한 일반 IT 가십, 단순 S/W 업데이트.

[평가 예시 (학습 데이터)]
예시 1) 뉴스: "애플, 시선 추적과 EMG 밴드를 결합한 새로운 AR 인터페이스 특허 등록" -> 답변: 100
예시 2) 뉴스: "삼성전자 갤럭시 S26, 스냅드래곤 8 Gen 4 탑재로 긱벤치 점수 소폭 상승" -> 답변: 65
예시 3) 뉴스: "테슬라 주가 5% 하락, 머스크의 새로운 트윗 영향" -> 답변: 10
"""

# --- 1. 초기 채널 데이터 ---
def get_initial_channels():
    return {
        "Global Innovation": [
            {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "active": True},
            {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "active": True},
            {"name": "Wired", "url": "https://www.wired.com/feed/rss", "active": True},
            {"name": "Engadget", "url": "https://www.engadget.com/rss.xml", "active": True},
            {"name": "9to5Google", "url": "https://9to5google.com/feed/", "active": True},
            {"name": "9to5Mac", "url": "https://9to5mac.com/feed/", "active": True},
            {"name": "MacRumors", "url": "https://feeds.macrumors.com/MacRumors-All", "active": True},
            {"name": "Android Authority", "url": "https://www.androidauthority.com/feed/", "active": True},
            {"name": "Samsung Global", "url": "https://news.samsung.com/global/feed", "active": True},
            {"name": "Apple Newsroom", "url": "https://www.apple.com/newsroom/rss-feed.rss", "active": True},
            {"name": "Bloomberg Tech", "url": "https://www.bloomberg.com/feeds/technology/index.rss", "active": True}
        ],
        "China & East Asia": [
            {"name": "36Kr", "url": "https://36kr.com/feed", "active": True},
            {"name": "IT Home", "url": "https://www.ithome.com/rss/", "active": True},
            {"name": "Gizmochina", "url": "https://www.gizmochina.com/feed/", "active": True}
        ],
        "Japan & Robotics": [
            {"name": "Nikkei Asia", "url": "https://asia.nikkei.com/rss/feed/nar", "active": True},
            {"name": "Gizmodo JP", "url": "https://www.gizmodo.jp/index.xml", "active": True}
        ]
    }

# --- 2. 설정 로직 ---
def load_user_settings(user_id):
    fn = f"nod_samsung_user_{user_id}.json"
    default = {
        "api_key": "",
        "sensing_period": 3, "max_articles": 30, "filter_weight": 80, # 퓨샷 적용으로 가중치 기본값 상향
        "filter_prompt": DEFAULT_FILTER_PROMPT,
        "ai_prompt": "위 기사를 우리 팀의 'NOD 프로젝트' 관점에서 심층 분석해줘.",
        "category_active": {"Global Innovation": True, "China & East Asia": True, "Japan & Robotics": True},
        "channels": get_initial_channels()
    }
    if os.path.exists(fn):
        with open(fn, "r", encoding="utf-8") as f:
            saved = json.load(f)
            for k, v in default.items():
                if k not in saved: saved[k] = v
            return saved
    return default

def save_user_settings(user_id, settings):
    with open(f"nod_samsung_user_{user_id}.json", "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

# --- 3. 정밀 AI 엔진 (모드 분리) ---
def get_ai_model(api_key, mode="filter"):
    try:
        genai.configure(api_key=api_key.strip())
        if mode == "analyze":
            # 심층 분석 버튼 클릭 시 발동하는 수석 분석가 모드
            return genai.GenerativeModel('gemini-1.5-flash', system_instruction=GEMS_PERSONA)
        else:
            # 필터링 시에는 프롬프트 창의 예시(Few-shot)를 따르는 기본 모드
            return genai.GenerativeModel('gemini-1.5-flash')
    except: return None

@st.cache_data(ttl=3600)
def safe_translate(text):
    if not text: return ""
    try: return GoogleTranslator(source='auto', target='ko').translate(text)
    except: return text

def fetch_raw_news(args):
    cat, f, limit = args
    articles = []
    try:
        d = feedparser.parse(f["url"])
        for entry in d.entries[:15]:
            dt = entry.get('published_parsed') or entry.get('updated_parsed')
            if not dt: continue
            p_date = datetime.fromtimestamp(time.mktime(dt))
            if p_date < limit: continue
            articles.append({
                "id": hashlib.md5(entry.link.encode()).hexdigest()[:12],
                "title_en": entry.title, "link": entry.link, "source": f["name"],
                "category": cat, "date_obj": p_date, "date": p_date.strftime("%Y.%m.%d"),
                "summary_en": BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:300]
            })
    except: pass
    return articles

@st.cache_data(ttl=600) 
def get_filtered_news(settings, _prompt, _weight):
    limit = datetime.now() - timedelta(days=settings["sensing_period"])
    active_tasks = [(cat, f, limit) for cat, feeds in settings["channels"].items() 
                    if settings["category_active"].get(cat, True) for f in feeds if f["active"]]
    
    if not active_tasks: return []

    raw_news = []
    with ThreadPoolExecutor(max_workers=25) as executor:
        futures = [executor.submit(fetch_raw_news, t) for t in active_tasks]
        for f in as_completed(futures): raw_news.extend(f.result())
    
    raw_news = sorted(raw_news, key=lambda x: x['date_obj'], reverse=True)[:150]
    
    # mode="filter"로 빠르고 객관적인 평가 모델 호출
    model = get_ai_model(settings["api_key"], mode="filter")
    filtered_list = []
    
    if not model or not _prompt: 
        for item in raw_news[:settings["max_articles"]]:
            item["score"] = 100
            item["title_ko"] = safe_translate(item["title_en"])
            item["summary_ko"] = safe_translate(item["summary_en"])
            filtered_list.append(item)
        return filtered_list

    pb = st.progress(0)
    st_text = st.empty()
    
    for i, item in enumerate(raw_news):
        st_text.caption(f"🎯 AI가 학습된 기준으로 기사 평가 중... ({i+1}/{len(raw_news)})")
        pb.progress((i + 1) / len(raw_news))
        
        try:
            # 퓨샷 프롬프트 + 실제 기사 데이터 조합
            score_query = f"{_prompt}\n\n[실제 평가 대상]\n뉴스제목: {item['title_en']}\n뉴스요약: {item['summary_en'][:200]}\n\n위 뉴스를 평가하여 0에서 100 사이의 숫자만 답하세요."
            res = model.generate_content(score_query).text.strip()
            match = re.search(r'\d+', res)
            score = int(match.group()) if match else 50 
        except: score = 50 
        
        if score >= _weight:
            item["score"] = score
            item["title_ko"] = safe_translate(item["title_en"])
            item["summary_ko"] = safe_translate(item["summary_en"])
            filtered_list.append(item)
            
    st_text.empty()
    pb.empty()
    return sorted(filtered_list, key=lambda x: x.get('score', 0), reverse=True)

# --- 4. UI 렌더링 ---
st.set_page_config(page_title="NGEPT Hub v14.6 (Few-Shot & Gems)", layout="wide")
st.markdown("""<style>
    .insta-card { background: white; border-radius: 20px; border: 1px solid #efefef; margin-bottom: 40px; box-shadow: 0 10px 20px rgba(0,0,0,0.03); }
    .card-img { width: 100%; height: 300px; object-fit: cover; }
</style>""", unsafe_allow_html=True)

with st.sidebar:
    st.title("👤 Strategy Profile")
    u_id = st.radio("사용자", ["1", "2", "3", "4"], horizontal=True)
    if "current_user" not in st.session_state or st.session_state.current_user != u_id:
        st.session_state.current_user = u_id
        st.session_state.settings = load_user_settings(u_id)
        st.session_state.editing_key = False
        st.rerun()

    st.divider()
    curr_key = st.session_state.settings.get("api_key", "").strip()
    if not st.session_state.get("editing_key", False) and curr_key:
        st.success("✅ API 인증 완료")
        if st.button("🔑 키 수정"):
            st.session_state.editing_key = True; st.rerun()
    else:
        new_key = st.text_input("Gemini API Key", value=curr_key, type="password")
        if st.button("💾 저장"):
            st.session_state.settings["api_key"] = new_key
            save_user_settings(u_id, st.session_state.settings)
            st.session_state.editing_key = False; st.rerun()

    st.divider()
    st.subheader("📂 카테고리 관리")
    for cat in list(st.session_state.settings["channels"].keys()):
        ch_list = st.session_state.settings["channels"][cat]
        st.session_state.settings["category_active"][cat] = st.toggle(f"{cat} ({len(ch_list)})", value=st.session_state.settings["category_active"].get(cat, True))
        if st.session_state.settings["category_active"][cat]:
            with st.expander(f"📌 {cat} 상세"):
                with st.form(f"add_{cat}", clear_on_submit=True):
                    n, u = st.text_input("채널명"), st.text_input("URL")
                    if st.form_submit_button("➕ 추가") and n and u:
                        st.session_state.settings["channels"][cat].append({"name": n, "url": u, "active": True})
                        save_user_settings(u_id, st.session_state.settings); st.rerun()
                for idx, f in enumerate(ch_list):
                    c1, c2 = st.columns([4, 1])
                    f["active"] = c1.checkbox(f["name"], value=f.get("active", True), key=f"cb_{u_id}_{cat}_{idx}")
                    if c2.button("🗑️", key=f"del_{u_id}_{cat}_{idx}"):
                        st.session_state.settings["channels"][cat].pop(idx)
                        save_user_settings(u_id, st.session_state.settings); st.rerun()

    st.divider()
    with st.expander("⚙️ 고급 필터 및 프롬프트", expanded=False):
        f_prompt = st.text_area("🔍 예시 학습(Few-Shot) 필터 프롬프트", value=st.session_state.settings["filter_prompt"], height=250)
        f_weight = st.slider("🎯 필터 가중치 (최소 점수)", 0, 100, st.session_state.settings["filter_weight"])
        st.session_state.settings["sensing_period"] = st.slider("수집 기간", 1, 30, st.session_state.settings["sensing_period"])
        st.session_state.settings["ai_prompt"] = st.text_area("📝 분석 프롬프트 (Gems용)", value=st.session_state.settings["ai_prompt"])

    if st.button("🚀 Apply & Sensing Start", use_container_width=True, type="primary"):
        st.session_state.settings["filter_prompt"] = f_prompt
        st.session_state.settings["filter_weight"] = f_weight
        save_user_settings(u_id, st.session_state.settings)
        st.cache_data.clear() 
        st.rerun()

# --- 5. 메인 화면 ---
st.markdown("<h1 style='text-align:center;'>NGEPT Strategy Hub</h1>", unsafe_allow_html=True)
st.caption(f"<div style='text-align:center;'>25명의 팀원을 위한 차세대 경험 기획 데이터 보드입니다.</div>", unsafe_allow_html=True)

news_list = get_filtered_news(st.session_state.settings, st.session_state.settings["filter_prompt"], st.session_state.settings["filter_weight"])

if news_list:
    cols = st.columns(3)
    for i, item in enumerate(news_list[:st.session_state.settings["max_articles"]]):
        with cols[i % 3]:
            st.markdown(f"""<div class="insta-card">
                <div style="padding:15px; display:flex; justify-content:space-between; align-items:center;">
                    <b>🌐 {item['source']}</b><span style="background:#E3F2FD; color:#1976D2; padding:2px 10px; border-radius:10px; font-weight:bold; font-size:0.8rem;">MATCH: {item.get('score', 0)}%</span>
                </div>
                <img src="https://s.wordpress.com/mshots/v1/{item['link']}?w=600" class="card-img">
                <div style="padding:20px;">
                    <div style="font-weight:bold; font-size:1.1rem;">{item.get('title_ko', item['title_en'])}</div>
                    <div style="font-size:0.8rem; color:gray; margin-top:5px;">{item['title_en']}</div>
                    <div style="font-size:0.85rem; color:#444; margin-top:15px;">{item.get('summary_ko', '내용 확인 중...')[:150]}...</div>
                    <br><a href="{item['link']}" target="_blank" style="color:#007AFF; font-weight:bold; text-decoration:none;">🔗 원문 기사 읽기</a>
                </div>
            </div>""", unsafe_allow_html=True)
            
            # 💎 Deep Analysis 버튼 (mode="analyze" 호출)
            if st.button("🔍 Gems Deep Analysis", key=f"btn_{item['id']}", use_container_width=True):
                model = get_ai_model(st.session_state.settings["api_key"], mode="analyze")
                if model:
                    with st.spinner("💎 전략 기획 Gems가 리포트를 도출 중입니다..."):
                        analysis_prompt = f"{st.session_state.settings['ai_prompt']}\n\n[기사 정보]\n제목: {item['title_en']}\n본문요약: {item['summary_en']}"
                        response = model.generate_content(analysis_prompt)
                        st.info(response.text)
else:
    st.info("데이터가 없습니다. 사이드바 설정을 확인한 후 'Apply & Sensing Start' 버튼을 눌러보세요.")
