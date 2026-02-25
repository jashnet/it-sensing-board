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
# 💎 [GEMS 설정] 페르소나 및 프롬프트
# ==========================================
GEMS_PERSONA = """
귀하는 글로벌 빅테크 기업의 '차세대 경험기획팀' 소속 수석 전략 분석가입니다.
향후 2~3년 내 상용화될 신규 스마트 디바이스와 혁신적 UX/UI를 기획하기 위해 시장의 '초기 시그널'을 센싱하는 것이 목적입니다.

[분석 필수 포함 항목]
1. 혁신성: 기존 제품 대비 경험의 변화가 얼마나 큰가?
2. 파급력: 전체 에코시스템에 어떤 변화를 주는가?
3. 기획적 가치: 우리 팀의 차세대 제품 기획(NOD 프로젝트)에 어떤 영감을 주는가?
"""

DEFAULT_FILTER_PROMPT = """귀하는 차세대경험기획팀의 'NOD 프로젝트' 전용 뉴스 필터링 에이전트입니다.
주어진 뉴스의 제목과 요약을 보고, 우리 팀의 기획 방향과 일치하는지 0~100점으로 평가하세요.

[평가 기준]
- 90~100점: 완전히 새로운 폼팩터, 혁신적 UX, 스마트 링/AR 글래스/신경 인터페이스(EMG) 등 하드웨어 시도, 공간 컴퓨팅, 에이전틱 AI, 주요 빅테크의 핵심 특허.
- 60~89점: 기존 폼팩터의 성능 향상(AP, 배터리 등), 일반적인 웨어러블/스마트폰 신제품 출시.
- 0~59점: 단순 루머, 주식/재무 뉴스, 우리 기획과 무관한 일반 IT 가십, 단순 S/W 업데이트.

[평가 예시 (학습 데이터)]
예시 1) "애플, 시선 추적과 EMG 밴드를 결합한 새로운 AR 인터페이스 특허 등록" -> 100
예시 2) "삼성전자 갤럭시 S26, 스냅드래곤 8 Gen 4 탑재로 긱벤치 점수 소폭 상승" -> 65
예시 3) "테슬라 주가 5% 하락, 머스크의 새로운 트윗 영향" -> 10
"""

# ==========================================
# 📂 [데이터 관리] 채널 파일 입출력 로직
# ==========================================
CHANNELS_FILE = "channels.json"

def load_channels_from_file():
    """channels.json 파일에서 채널 리스트를 읽어옵니다."""
    if os.path.exists(CHANNELS_FILE):
        try:
            with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            st.error(f"채널 파일을 읽는 중 오류 발생: {e}")
            return {}
    return {} # 파일이 없으면 빈 딕셔너리 반환

def save_channels_to_file(channels_data):
    """채널 리스트 변경사항을 channels.json 파일에 저장합니다."""
    try:
        with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
            json.dump(channels_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        st.error(f"채널 파일 저장 실패: {e}")

# ==========================================
# ⚙️ [설정 관리] 사용자 설정 로직
# ==========================================
def load_user_settings(user_id):
    """사용자별 설정(API키, 프롬프트 등)을 로드합니다. 채널은 별도 파일에서 관리합니다."""
    fn = f"nod_samsung_user_{user_id}.json"
    default_settings = {
        "api_key": "",
        "sensing_period": 3,
        "max_articles": 30,
        "filter_weight": 80,
        "filter_prompt": DEFAULT_FILTER_PROMPT,
        "ai_prompt": "위 기사를 우리 팀의 'NOD 프로젝트' 관점에서 심층 분석해줘.",
        "category_active": {"Global Innovation": True, "China & East Asia": True, "Japan & Robotics": True}
    }
    
    # 1. 사용자 설정 파일 로드
    if os.path.exists(fn):
        with open(fn, "r", encoding="utf-8") as f:
            saved = json.load(f)
            # 누락된 키가 있으면 기본값으로 채움
            for k, v in default_settings.items():
                if k not in saved: saved[k] = v
            return saved
    return default_settings

def save_user_settings(user_id, settings):
    with open(f"nod_samsung_user_{user_id}.json", "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

# ==========================================
# 🧠 [AI 엔진] Gemini API 연동
# ==========================================
def get_ai_model(api_key, mode="filter"):
    # API 키가 없거나 너무 짧으면(유효하지 않으면) 모델 실행 차단
    if not api_key or len(api_key.strip()) < 10:
        return None
        
    try:
        genai.configure(api_key=api_key.strip())
        
        # 'models/'를 빼고, 가장 안정적인 latest 태그를 붙여줍니다.
        MODEL_NAME = "gemini-1.5-flash-latest"
        
        if mode == "analyze":
            return genai.GenerativeModel(MODEL_NAME, system_instruction=GEMS_PERSONA)
        else:
            return genai.GenerativeModel(MODEL_NAME)
    except: 
        return None

@st.cache_data(ttl=3600)
def safe_translate(text):
    if not text: return ""
    try: return GoogleTranslator(source='auto', target='ko').translate(text)
    except: return text

# ==========================================
# 📡 [수집 엔진] 뉴스 크롤링 및 필터링
# ==========================================
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
def get_filtered_news(settings, channels_data, _prompt, _weight):
    limit = datetime.now() - timedelta(days=settings["sensing_period"])
    
    # 활성화된 채널만 수집 대상으로 선정 (channels.json 데이터 사용)
    active_tasks = []
    for cat, feeds in channels_data.items():
        if settings["category_active"].get(cat, True): # 카테고리가 켜져 있으면
            for f in feeds:
                if f.get("active", True): # 개별 채널이 켜져 있으면
                    active_tasks.append((cat, f, limit))
    
    if not active_tasks: return []

    raw_news = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(fetch_raw_news, t) for t in active_tasks]
        for f in as_completed(futures): raw_news.extend(f.result())
    
    raw_news = sorted(raw_news, key=lambda x: x['date_obj'], reverse=True)[:150]
    
    # AI 모델 로드 (필터링 모드)
    model = get_ai_model(settings["api_key"], mode="filter")
    filtered_list = []
    
    if not model or not _prompt: 
        # API 키 없으면 필터링 없이 번역만 해서 반환
        for item in raw_news[:settings["max_articles"]]:
            item["score"] = 100
            item["title_ko"] = safe_translate(item["title_en"])
            item["summary_ko"] = safe_translate(item["summary_en"])
            filtered_list.append(item)
        return filtered_list

# AI 필터링 진행 (초고속 모드)
    pb = st.progress(0)
    st_text = st.empty()
    
    for i, item in enumerate(raw_news):
        st_text.caption(f"⚡ AI 초고속 필터링 진행 중... ({i+1}/{len(raw_news)})")
        pb.progress((i + 1) / len(raw_news))
        
        try:
            score_query = f"{_prompt}\n\n[평가 대상]\n제목: {item['title_en']}\n요약: {item['summary_en'][:200]}\n\n점수(0-100) 숫자만 출력:"
            res = model.generate_content(score_query).text.strip()
            match = re.search(r'\d+', res)
            score = int(match.group()) if match else 50 
            
            # 유료 Tier 1이므로 time.sleep() 대기 시간 삭제 완료! 🚀
            
        except Exception as e:
            score = 50 
            # 진짜 에러가 날 경우에만 화면에 원인을 표시
            st.warning(f"기사 평가 중 일시적 오류 발생: {e}")
        
        if score >= _weight:
            item["score"] = score
            item["title_ko"] = safe_translate(item["title_en"])
            item["summary_ko"] = safe_translate(item["summary_en"])
            filtered_list.append(item)
            
    st_text.empty()
    pb.empty()
    return sorted(filtered_list, key=lambda x: x.get('score', 0), reverse=True)

# ==========================================
# 🖥️ [UI] 메인 화면 렌더링
# ==========================================
st.set_page_config(page_title="NGEPT Strategy Hub", layout="wide")
st.markdown("""<style>
    .insta-card { background: white; border-radius: 15px; border: 1px solid #e0e0e0; margin-bottom: 30px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
    .card-img { width: 100%; height: 250px; object-fit: cover; border-bottom: 1px solid #f0f0f0; border-radius: 15px 15px 0 0; }
    .score-badge { background-color: #E3F2FD; color: #1565C0; padding: 4px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: bold; }
</style>""", unsafe_allow_html=True)

# 1. 초기 데이터 로드 (세션 관리)
if "channels" not in st.session_state:
    st.session_state.channels = load_channels_from_file()

with st.sidebar:
    st.title("👤 NOD Leader Profile")
    u_id = st.radio("사용자 프로필", ["1", "2", "3", "4"], horizontal=True)
    
    # 사용자 변경 시 설정 다시 로드
    if "current_user" not in st.session_state or st.session_state.current_user != u_id:
        st.session_state.current_user = u_id
        st.session_state.settings = load_user_settings(u_id)
        # 채널 데이터도 파일에서 최신본 로드
        st.session_state.channels = load_channels_from_file()
        st.rerun()

    st.divider()
    
    # API Key 설정
    curr_key = st.session_state.settings.get("api_key", "").strip()
    if not st.session_state.get("editing_key", False) and curr_key:
        st.success("✅ API Key 연동됨")
        if st.button("🔑 키 변경"):
            st.session_state.editing_key = True; st.rerun()
    else:
        new_key = st.text_input("Gemini API Key", value=curr_key, type="password")
        if st.button("💾 저장"):
            st.session_state.settings["api_key"] = new_key
            save_user_settings(u_id, st.session_state.settings)
            st.session_state.editing_key = False; st.rerun()

    st.divider()
    
    # 채널 관리 (channels.json 연동)
    st.subheader("📂 채널 관리 (Channels.json)")
    
    # 파일에 없는 카테고리가 설정에 있다면 추가 (동기화)
    for cat in st.session_state.channels.keys():
        if cat not in st.session_state.settings["category_active"]:
            st.session_state.settings["category_active"][cat] = True

    for cat in list(st.session_state.channels.keys()):
        # 카테고리 토글
        is_active = st.session_state.settings["category_active"].get(cat, True)
        st.session_state.settings["category_active"][cat] = st.toggle(f"{cat} ({len(st.session_state.channels[cat])})", value=is_active)
        
        if st.session_state.settings["category_active"][cat]:
            with st.expander(f"📌 {cat} 목록 편집"):
                # 채널 추가 폼
                with st.form(f"add_{cat}", clear_on_submit=True):
                    c1, c2 = st.columns([2, 3])
                    new_name = c1.text_input("이름", placeholder="예: Verge")
                    new_url = c2.text_input("RSS URL", placeholder="https://...")
                    if st.form_submit_button("➕ 채널 추가"):
                        if new_name and new_url:
                            st.session_state.channels[cat].append({"name": new_name, "url": new_url, "active": True})
                            save_channels_to_file(st.session_state.channels) # 파일 저장
                            st.rerun()
                
                # 채널 삭제/활성 UI
                for idx, f in enumerate(st.session_state.channels[cat]):
                    c1, c2 = st.columns([4, 1])
                    # 활성 상태 변경 시 바로 저장
                    prev_state = f.get("active", True)
                    new_state = c1.checkbox(f["name"], value=prev_state, key=f"cb_{cat}_{idx}")
                    if prev_state != new_state:
                        f["active"] = new_state
                        save_channels_to_file(st.session_state.channels)
                    
                    # 삭제 버튼
                    if c2.button("🗑️", key=f"del_{cat}_{idx}"):
                        st.session_state.channels[cat].pop(idx)
                        save_channels_to_file(st.session_state.channels) # 파일 저장
                        st.rerun()

    st.divider()
    
    # 고급 설정 (프롬프트 등)
    with st.expander("⚙️ 고급 필터 설정", expanded=False):
        f_prompt = st.text_area("🔍 필터 프롬프트 (Few-Shot)", value=st.session_state.settings["filter_prompt"], height=200)
        f_weight = st.slider("🎯 최소 일치 점수", 0, 100, st.session_state.settings["filter_weight"])
        st.session_state.settings["sensing_period"] = st.slider("최근 N일 기사만 수집", 1, 30, st.session_state.settings["sensing_period"])
        st.session_state.settings["ai_prompt"] = st.text_area("📝 분석 프롬프트", value=st.session_state.settings["ai_prompt"])

    if st.button("🚀 Sensing Start", use_container_width=True, type="primary"):
        st.session_state.settings["filter_prompt"] = f_prompt
        st.session_state.settings["filter_weight"] = f_weight
        save_user_settings(u_id, st.session_state.settings)
        st.cache_data.clear()
        st.rerun()

# 2. 메인 컨텐츠 영역
st.markdown("<h1 style='text-align:center;'>NOD Strategy Hub</h1>", unsafe_allow_html=True)
st.caption(f"<div style='text-align:center;'>차세대 경험기획팀을 위한 Gems 통합 인사이트 보드</div>", unsafe_allow_html=True)

# 뉴스 데이터 가져오기 (channels.json 데이터 전달)
news_list = get_filtered_news(
    st.session_state.settings, 
    st.session_state.channels, 
    st.session_state.settings["filter_prompt"], 
    st.session_state.settings["filter_weight"]
)

if news_list:
    cols = st.columns(3)
    for i, item in enumerate(news_list[:st.session_state.settings["max_articles"]]):
        with cols[i % 3]:
            st.markdown(f"""<div class="insta-card">
                <div style="padding:15px; display:flex; justify-content:space-between; align-items:center;">
                    <b>🌐 {item['source']}</b>
                    <span class="score-badge">MATCH {item.get('score', 0)}%</span>
                </div>
                <img src="https://s.wordpress.com/mshots/v1/{item['link']}?w=600" class="card-img">
                <div style="padding:20px;">
                    <div style="font-weight:bold; font-size:1.1rem; line-height:1.4;">{item.get('title_ko', item['title_en'])}</div>
                    <div style="font-size:0.8rem; color:gray; margin-top:8px;">{item['title_en']}</div>
                    <div style="font-size:0.85rem; color:#444; margin-top:15px;">{item.get('summary_ko', '')[:120]}...</div>
                    <br><a href="{item['link']}" target="_blank" style="color:#007AFF; font-weight:bold; text-decoration:none;">🔗 원문 보기</a>
                </div>
            </div>""", unsafe_allow_html=True)
            
            # Gems 심층 분석 버튼
            if st.button("🔍 Gems Deep Analysis", key=f"btn_{item['id']}", use_container_width=True):
                current_api_key = st.session_state.settings.get("api_key", "").strip()
                
                if not current_api_key:
                    st.warning("⚠️ 좌측 사이드바에서 Gemini API Key를 입력하고 [💾 저장]을 눌러주세요.")
                else:
                    model = get_ai_model(current_api_key, mode="analyze")
                    if model:
                        with st.spinner("💎 수석 전략가가 분석 중입니다..."):
                            try:
                                prompt = f"{st.session_state.settings['ai_prompt']}\n\n[기사]\n제목: {item['title_en']}\n요약: {item['summary_en']}"
                                response = model.generate_content(prompt)
                                st.info(response.text)
                            except Exception as e:
                                # Streamlit이 가려버린 진짜 에러 메시지를 화면에 강제 출력합니다.
                                st.error(f"🚨 구글 API 연결 오류입니다. API 키가 정확한지 확인해 주세요.\n\n상세 에러 내역: {e}")
                    else:
                        st.error("⚠️ API Key 형식이 올바르지 않습니다.")
