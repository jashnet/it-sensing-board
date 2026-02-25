import streamlit as st
import feedparser
from google import genai
from google.genai import types
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
귀하는 삼성전자 '차세대경험기획팀' 소속 최고 수준의 수석 전략 분석가입니다.
우리의 목표는 2~3년 이후 상용화될 신규 스마트 디바이스, 혁신적 폼팩터, 그리고 AI가 결합된 차세대 UX/UI를 선제적으로 발굴하는 'NOD 프로젝트'의 성공입니다.

주어진 기사를 분석할 때 다음 항목을 반드시 포함하여 전문가적인 통찰력을 제공하세요.

[심층 분석 리포트 구조]
1. 핵심 요약 및 숨은 의도: 
   - 표면적인 뉴스 내용을 넘어, 이 기술/제품을 발표한 기업(또는 국가)의 진짜 전략적 의도가 무엇인지 분석하세요.
2. 파급력 및 생태계 영향 (AI 가중치): 
   - 이 소식이 다수의 디바이스 생태계나 소비자의 행동 양식(Behavior)에 어떤 거대한 변화를 가져올지 분석하세요. 
   - 특히 AI 발전이 수반된 경험의 변화라면 그 폭발력을 강조하세요.
3. NOD 프로젝트(삼성전자)를 위한 Implication:
   - 경쟁사(Apple, Meta, OpenAI 등 메이저 또는 파괴적 혁신 스타트업/중국 기업)의 행보가 우리에게 미치는 위협과 기회는 무엇인가?
   - 이 시그널을 바탕으로 우리가 당장 연구하거나 대응해야 할 제품적, UX적 방향성은 무엇인가?
"""

DEFAULT_FILTER_PROMPT = """귀하는 삼성전자 차세대경험기획팀의 뉴스 필터링 AI 에이전트입니다.
주어진 뉴스의 제목과 요약을 보고, 2~3년 뒤 출시할 '소비자 중심의 차세대 스마트 디바이스 및 UX 기획'에 얼마나 중요한 시그널인지 0~100점으로 평가하세요.

[우선순위 가중치 규칙]
- +가중치: AI 기술이 결합된 경험 변화, 생태계 전반을 흔드는 파급력, 주요 빅테크(Apple, MS, Meta, Google, OpenAI 등)의 핵심 동향, 미국에 도전하는 중국의 극단적 하드웨어/AI 변형 시도.
- -감점/배제: 단순 실적/재무 발표, 정책/법률/특허 소송, 기업 인사 동정, 광고성 이벤트, 순수 B2B/산업용 기술.
- 조건부 허용: 자동차, 이동수단, 스마트홈은 그 자체로는 점수가 낮으나, '스마트 디바이스(폰, 웨어러블)와의 연동을 통한 새로운 UX 창출' 내용이라면 높은 점수를 부여함.

[점수 평가 기준]
- 90~100점 (핵심 시그널): 스마트폰/웨어러블(워치, 링, 글래스, 이어버즈)/XR/로봇/AI Pin 등의 새로운 폼팩터 등장. 기존 하드웨어에 신규 센서를 결합한 혁신. 빅테크나 파괴적 스타트업의 판도를 바꿀 AI 서비스/UX 발표.
- 60~89점 (참고 동향): 모바일 기기와 연동되는 모빌리티/스마트홈의 새로운 가치. 메이저 플레이어들의 일반적인 신제품 루머 및 스펙 업그레이드. 소비자 행동에 영향을 줄 수 있는 신규 앱/서비스.
- 0~59점 (노이즈): 산업용(B2B) 로봇/AI, 순수 자동차 스펙 뉴스, 단순 매출 발표, 법적 규제, 광고.

[평가 예시]
예시 1) "애플, 비전프로와 연동되는 시선 추적 및 AI 기반의 새로운 스마트 링 특허 출원" -> 95
예시 2) "중국 스타트업, LLM을 하드웨어에 직접 심어 통신 없이 작동하는 초소형 웨어러블 AI 공개" -> 92
예시 3) "테슬라, 새로운 자율주행 택시 로보택시 공개 및 주행 테스트 완료" -> 40 (모바일 기기 연동이나 UX 혁신 내용이 없다면 우선순위 낮음)
예시 4) "메타, 3분기 실적 예상치 상회... 광고 매출 전년 대비 20% 증가" -> 10 (재무 뉴스 배제)

위 기준을 엄격하게 적용하여, 주어진 뉴스를 평가하고 오직 0에서 100 사이의 '숫자'만 출력하세요.
"""

# ==========================================
# 📂 [데이터 관리] 채널 파일 입출력 로직
# ==========================================
CHANNELS_FILE = "channels.json"

def load_channels_from_file():
    if os.path.exists(CHANNELS_FILE):
        try:
            with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            st.error(f"채널 파일을 읽는 중 오류 발생: {e}")
            return {}
    return {}

def save_channels_to_file(channels_data):
    try:
        with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
            json.dump(channels_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        st.error(f"채널 파일 저장 실패: {e}")

# ==========================================
# ⚙️ [설정 관리] 사용자 설정 로직
# ==========================================
def load_user_settings(user_id):
    fn = f"nod_samsung_user_{user_id}.json"
    default_settings = {
        "api_key": "",
        "sensing_period": 14,
        "max_articles": 30,
        "filter_weight": 70,
        "filter_prompt": DEFAULT_FILTER_PROMPT,
        "ai_prompt": "위 기사를 우리 팀의 'NOD 프로젝트' 관점에서 심층 분석해줘.",
        "category_active": {"Global Innovation": True, "China & East Asia": True, "Japan & Robotics": True}
    }
    
    if os.path.exists(fn):
        with open(fn, "r", encoding="utf-8") as f:
            saved = json.load(f)
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
def get_ai_client(api_key):
    if not api_key or len(api_key.strip()) < 10:
        return None
    try:
        return genai.Client(api_key=api_key.strip())
    except: 
        return None

@st.cache_data(ttl=3600)
def safe_translate(text):
    if not text: return ""
    try: return GoogleTranslator(source='auto', target='ko').translate(text)
    except: return text

# ==========================================
# 📡 [수집 엔진] 뉴스 크롤링 및 초고속 병렬 필터링
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
    
    active_tasks = []
    for cat, feeds in channels_data.items():
        if settings["category_active"].get(cat, True):
            for f in feeds:
                if f.get("active", True):
                    active_tasks.append((cat, f, limit))
    
    if not active_tasks: return []

    raw_news = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(fetch_raw_news, t) for t in active_tasks]
        for f in as_completed(futures): raw_news.extend(f.result())
    
    raw_news = sorted(raw_news, key=lambda x: x['date_obj'], reverse=True)[:150]
    
    client = get_ai_client(settings["api_key"])
    filtered_list = []
    
    if not client or not _prompt: 
        for item in raw_news[:settings["max_articles"]]:
            item["score"] = 100
            item["title_ko"] = safe_translate(item["title_en"])
            item["summary_ko"] = safe_translate(item["summary_en"])
            filtered_list.append(item)
        return filtered_list

    pb = st.progress(0)
    st_text = st.empty()
    
    def ai_scoring_worker(item):
        try:
            score_query = f"{_prompt}\n\n[평가 대상]\n제목: {item['title_en']}\n요약: {item['summary_en'][:200]}\n\n점수(0-100) 숫자만 출력:"
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=score_query
            )
            res = response.text.strip()
            match = re.search(r'\d+', res)
            score = int(match.group()) if match else 50 
        except Exception:
            score = 50 
        return item, score

    with ThreadPoolExecutor(max_workers=15) as executor:
        future_to_item = {executor.submit(ai_scoring_worker, item): item for item in raw_news}
        
        for i, future in enumerate(as_completed(future_to_item)):
            st_text.caption(f"⚡ AI 초고속 다중 스레드 필터링 진행 중... ({i+1}/{len(raw_news)})")
            pb.progress((i + 1) / len(raw_news))
            
            item, score = future.result()
            
            if score >= _weight:
                item["score"] = score
                item["title_ko"] = safe_translate(item["title_en"])
                item["summary_ko"] = safe_translate(item["summary_en"])
                filtered_list.append(item)
                
    st_text.empty()
    pb.empty()
    return sorted(filtered_list, key=lambda x: x.get('score', 0), reverse=True)

# ==========================================
# 🖥️ [UI] 메인 화면 렌더링 (Instagram 스타일)
# ==========================================
st.set_page_config(page_title="NGEPT Strategy Hub", layout="wide")

# 💡 모던 인스타그램 스타일 CSS 적용
st.markdown("""<style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
    .insta-card { 
        background: #ffffff; 
        border: 1px solid #dbdbdb; 
        border-radius: 12px; 
        margin-bottom: 40px; 
        overflow: hidden;
    }
    .card-header { 
        padding: 14px 16px; 
        display: flex; 
        justify-content: space-between; 
        align-items: center; 
        border-bottom: 1px solid #efefef;
    }
    .source-info { 
        display: flex; 
        align-items: center; 
        gap: 12px; 
    }
    .source-icon {
        width: 32px; height: 32px; 
        background: #f0f2f5; 
        border-radius: 50%; 
        display: flex; 
        align-items: center; 
        justify-content: center; 
        font-size: 14px;
    }
    .source-name { 
        font-weight: 600; 
        font-size: 0.95rem; 
        color: #262626; 
    }
    .score-badge { 
        background-color: #0095f6; 
        color: white; 
        padding: 4px 10px; 
        border-radius: 12px; 
        font-size: 0.75rem; 
        font-weight: 700; 
    }
    .card-img { 
        width: 100%; 
        aspect-ratio: 4/3; 
        object-fit: cover; 
        display: block; 
    }
    .card-body { 
        padding: 16px; 
    }
    .card-title { 
        font-weight: 700; 
        font-size: 1.1rem; 
        line-height: 1.4; 
        color: #262626; 
        margin-bottom: 4px; 
    }
    .card-subtitle { 
        font-size: 0.85rem; 
        color: #8e8e8e; 
        margin-bottom: 12px; 
        line-height: 1.3; 
    }
    .card-text { 
        font-size: 0.95rem; 
        color: #262626; 
        line-height: 1.5; 
        margin-bottom: 16px; 
    }
    .read-more { 
        color: #0095f6; 
        font-weight: 600; 
        text-decoration: none; 
        font-size: 0.9rem; 
    }
</style>""", unsafe_allow_html=True)

if "channels" not in st.session_state:
    st.session_state.channels = load_channels_from_file()

with st.sidebar:
    st.title("👤 NOD Leader Profile")
    u_id = st.radio("사용자 프로필", ["1", "2", "3", "4"], horizontal=True)

    if "current_user" not in st.session_state or st.session_state.current_user != u_id:
        st.session_state.current_user = u_id
        st.session_state.settings = load_user_settings(u_id)
        st.session_state.channels = load_channels_from_file()
        st.rerun()

    st.divider()
    
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
    
    st.subheader("📂 채널 관리 (Channels.json)")
    
    for cat in st.session_state.channels.keys():
        if cat not in st.session_state.settings["category_active"]:
            st.session_state.settings["category_active"][cat] = True

    for cat in list(st.session_state.channels.keys()):
        is_active = st.session_state.settings["category_active"].get(cat, True)
        st.session_state.settings["category_active"][cat] = st.toggle(f"{cat} ({len(st.session_state.channels[cat])})", value=is_active)
        
        if st.session_state.settings["category_active"][cat]:
            with st.expander(f"📌 {cat} 목록 편집"):
                with st.form(f"add_{cat}", clear_on_submit=True):
                    c1, c2 = st.columns([2, 3])
                    new_name = c1.text_input("이름", placeholder="예: Verge")
                    new_url = c2.text_input("RSS URL", placeholder="https://...")
                    if st.form_submit_button("➕ 채널 추가"):
                        if new_name and new_url:
                            st.session_state.channels[cat].append({"name": new_name, "url": new_url, "active": True})
                            save_channels_to_file(st.session_state.channels)
                            st.rerun()
                
                for idx, f in enumerate(st.session_state.channels[cat]):
                    c1, c2 = st.columns([4, 1])
                    prev_state = f.get("active", True)
                    new_state = c1.checkbox(f["name"], value=prev_state, key=f"cb_{cat}_{idx}")
                    if prev_state != new_state:
                        f["active"] = new_state
                        save_channels_to_file(st.session_state.channels)
                    
                    if c2.button("🗑️", key=f"del_{cat}_{idx}"):
                        st.session_state.channels[cat].pop(idx)
                        save_channels_to_file(st.session_state.channels)
                        st.rerun()

    st.divider()
    
    # 💡 [요청사항 1] 자주 쓰는 설정들을 밖으로 빼고 이름 변경
    st.subheader("🎛️ 기본 필터 설정")
    f_weight = st.slider("🎯 최소 매칭 점수", 0, 100, st.session_state.settings["filter_weight"])
    st.session_state.settings["sensing_period"] = st.slider("최근 N일 기사만 수집", 1, 30, st.session_state.settings["sensing_period"])

    # 프롬프트들만 고급 설정 박스 안에 유지
    with st.expander("⚙️ 고급 프롬프트 설정", expanded=False):
        f_prompt = st.text_area("🔍 필터 프롬프트 (Few-Shot)", value=st.session_state.settings["filter_prompt"], height=200)
        st.session_state.settings["ai_prompt"] = st.text_area("📝 분석 프롬프트", value=st.session_state.settings["ai_prompt"], height=100)

    if st.button("🚀 Sensing Start", use_container_width=True, type="primary"):
        st.session_state.settings["filter_prompt"] = f_prompt
        st.session_state.settings["filter_weight"] = f_weight
        save_user_settings(u_id, st.session_state.settings)
        st.cache_data.clear()
        st.rerun()
        
    st.divider()
    
    if st.button("🔍 내 API 키 허용 모델 확인하기"):
        test_key = st.session_state.settings.get("api_key", "").strip()
        if not test_key:
            st.error("⚠️ 위젯에서 API Key를 먼저 입력하고 [💾 저장]을 눌러주세요.")
        else:
            try:
                temp_client = get_ai_client(test_key)
                models = temp_client.models.list()
                model_names = [m.name for m in models]
                st.success(f"✅ 사용 가능한 모델 목록: {model_names}")
            except Exception as e:
                st.error(f"🚨 조회 실패: {e}")

# 2. 메인 컨텐츠 영역
st.markdown("<h1 style='text-align:center;'>NOD Strategy Hub</h1>", unsafe_allow_html=True)
st.caption(f"<div style='text-align:center;'>차세대 경험기획팀을 위한 Gems 통합 인사이트 보드</div><br>", unsafe_allow_html=True)

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
            score = item.get('score', 0)
            title_ko = item.get('title_ko', item['title_en'])
            summary_ko = item.get('summary_ko', '')[:120]
            
            # 💡 [요청사항 2] 인스타그램 피드 스타일의 깔끔한 카드 UI 렌더링
            html_card = f"""
            <div class="insta-card">
                <div class="card-header">
                    <div class="source-info">
                        <div class="source-icon">📰</div>
                        <div class="source-name">{item['source']}</div>
                    </div>
                    <span class="score-badge">MATCH {score}%</span>
                </div>
                <img src="https://s.wordpress.com/mshots/v1/{item['link']}?w=600" class="card-img" loading="lazy">
                <div class="card-body">
                    <div class="card-title">{title_ko}</div>
                    <div class="card-subtitle">{item['title_en']}</div>
                    <div class="card-text">{summary_ko}...</div>
                    <a href="{item['link']}" target="_blank" class="read-more">원문 기사 읽기 ↗</a>
                </div>
            </div>
            """
            st.markdown(html_card, unsafe_allow_html=True)
            
            if st.button("🔍 Gems Deep Analysis", key=f"btn_{item['id']}", use_container_width=True):
                current_api_key = st.session_state.settings.get("api_key", "").strip()
                
                if not current_api_key:
                    st.warning("⚠️ 좌측 사이드바에서 Gemini API Key를 입력하고 [💾 저장]을 눌러주세요.")
                else:
                    client = get_ai_client(current_api_key)
                    if client:
                        with st.spinner("💎 수석 전략가가 분석 중입니다..."):
                            try:
                                config = types.GenerateContentConfig(
                                    system_instruction=GEMS_PERSONA,
                                )
                                prompt = f"{st.session_state.settings['ai_prompt']}\n\n[기사]\n제목: {item['title_en']}\n요약: {item['summary_en']}"
                                
                                response = client.models.generate_content(
                                    model="gemini-2.5-flash",
                                    contents=prompt,
                                    config=config
                                )
                                st.info(response.text)
                            except Exception as e:
                                st.error(f"🚨 구글 API 연결 오류입니다. API 키가 정확한지 확인해 주세요.\n\n상세 에러 내역: {e}")
                    else:
                        st.error("⚠️ API Key 형식이 올바르지 않습니다.")
