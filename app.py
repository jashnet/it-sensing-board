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
# 🧠 [AI 엔진] Gemini API 연동 (유료 Tier 1 최적화)
# ==========================================
def get_ai_model(api_key, mode="filter"):
    # API 키가 없거나 비정상적이면 실행 차단
    if not api_key or len(api_key.strip()) < 10:
        return None
        
    try:
        genai.configure(api_key=api_key.strip())
        
        # 💡 [핵심 수정] 꼬리표를 모두 떼고 가장 표준적인 정식 명칭만 사용합니다.
        MODEL_NAME = "gemini-1.5-flash"
        
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
    
    # 활성화된 채널
