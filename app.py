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

# --- 1. 설정 및 기본값 (채널 리스트 유지 및 필터 완화) ---
SETTINGS_FILE = "nod_samsung_pro_v6.json"
DEFAULT_API_KEY = "AIzaSyCW7kwkCqCSN-usKFG9gwcPzYlHwtQW_DQ"

def default_settings():
    return {
        "api_key": DEFAULT_API_KEY,
        "slack_webhook": "",
        "sensing_period": 7,
        # 필터 조건 완화: '혁신'의 단서가 있다면 가급적 수집하도록 수정
        "filter_prompt": """당신은 삼성전자의 차세대 경험기획 전문가입니다. 
        글로벌 테크 산업의 흐름을 폭넓게 파악하기 위해, 새로운 기술 시도, 스타트업의 신제품, 대기업의 전략적 움직임, UX/UI 디자인 트렌드에 해당하는 뉴스를 가급적 수집하세요. 
        완전히 무관한 단순 주식 정보나 단순 홍보 기사만 제외하고 '혁신'의 실마리가 있다면 'True'로 판별하세요.""",
        "ai_prompt": """삼성전자(Samsung) 기획자 관점에서 3단계 분석을 수행하라:
        a) Fact Summary: 핵심 사실 요약.
        b) 3-Year Future Impact: 향후 3년 내 스마트폰/웨어러블 시장 및 사용자 행태에 미칠 변화 예측.
        c) Samsung Takeaway: 삼성 제품/경험 혁신을 위한 제언.""",
        "channels": {
            "Global Innovation (23)": [
                {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "active": True},
                {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "active": True},
                {"name": "Wired", "url": "https://www.wired.com/feed/rss", "active": True},
                {"name": "Engadget", "url": "https://www.engadget.com/rss.xml", "active": True},
                {"name": "Gizmodo", "url": "https://gizmodo.com/rss", "active": True},
                {"name": "Product Hunt", "url": "https://www.producthunt.com/feed", "active": True},
                {"name": "Yanko Design", "url": "https://www.yankodesign.com/feed/", "active": True},
                {"name": "Fast Company Design", "url": "https://www.fastcompany.com/design/rss", "active": True},
                {"name": "IEEE Spectrum", "url": "https://spectrum.ieee.org/rss/fulltext", "active": True},
                {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/", "active": True},
                {"name": "9to5Google", "url": "https://9to5google.com/feed/", "active": True},
                {"name": "9to5Mac", "url": "https://9to5mac.com/feed/", "active": True},
                {"name": "Android Authority", "url": "https://www.androidauthority.com/feed/", "active": True},
                {"name": "MacRumors", "url": "https://feeds.macrumors.com/MacRumors-All", "active": True},
                {"name": "Android Central", "url": "https://www.androidcentral.com/feed", "active": True},
                {"name": "SlashGear", "url": "https://www.slashgear.com/feed/", "active": True},
                {"name": "Digital Trends", "url": "https://www.digitaltrends.com/feed/", "active": True},
                {"name": "VentureBeat", "url": "https://venturebeat.com/feed/", "active": True},
                {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "active": True},
                {"name": "Mashable", "url": "https://mashable.com/feeds/rss/all", "active": True},
                {"name": "The Next Web", "url": "https://thenextweb.com/feed", "active": True},
                {"name": "ReadWrite", "url": "https://readwrite.com/feed/", "active": True},
                {"name": "ZDNet", "url": "https://www.zdnet.com/news/rss.xml", "active": True}
            ],
            "China AI/HW (11)": [
                {"name": "36Kr (CN)", "url": "https://36kr.com/feed", "active": True},
                {"name": "TechNode", "url": "https://technode.com/feed/", "active": True},
                {"name": "Gizmochina", "url": "https://www.gizmochina.com/feed/", "active": True},
                {"name": "SCMP Tech", "url": "https://www.scmp.com/rss/318206/feed.xml", "active": True},
                {"name": "Pandaily", "url": "https://pandaily.com/feed/", "active": True},
                {"name": "KrASIA", "url": "https://kr-asia.com/feed", "active": True},
                {"name": "Huxiu (虎嗅)", "url": "https://www.huxiu.com/rss/0.xml", "active": True},
                {"name": "CnBeta", "url": "https://www.cnbeta.com.tw/backend.php", "active": True},
                {"name": "IT Home", "url": "https://www.ithome.com/rss/", "active": True},
                {"name": "Sina Tech", "url": "https://tech.sina.com.cn/rss/all.xml", "active": True},
                {"name": "Leiphone", "url": "https://www.leiphone.com/feed", "active": True}
            ],
            "Japan Innovation (11)": [
                {"name": "The Bridge JP", "url": "https://thebridge.jp/feed", "active": True},
                {"name": "ITmedia News", "url": "https://rss.itmedia.co.jp/rss/2.0/news_bursts.xml", "active": True},
                {"name": "Gizmodo JP", "url": "https://www.gizmodo.jp/index.xml", "active": True},
                {"name": "CNET Japan", "url": "https://japan.cnet.com/rss/index.rdf", "active": True},
                {"name": "Nikkei Asia Tech", "url": "https://asia.nikkei.com/rss/feed/nar", "active": True},
                {"name": "ASCII.jp", "url": "https://ascii.jp/rss.xml", "active": True},
                {"name": "PC Watch", "url": "https://pc.watch.impress.co.jp/data/rss/1.0/pcw/feed.rdf", "active": True},
                {"name": "Impress Watch", "url": "https://www.watch.impress.co.jp/data/rss/1.0/ipw/feed.rdf", "active": True},
                {"name": "Mynavi Tech", "url": "https://news.mynavi.jp/rss/digital/it/", "active": True},
                {"name": "Techable JP", "url": "https://techable.jp/feed", "active": True},
                {"name": "Yahoo JP Tech", "url": "https://news.yahoo.co.jp/rss/categories/it.xml", "active": True}
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

# --- 2. 자연스러운 번역 및 지능형 스크린샷 썸네일 엔진 ---
def natural_translate(text):
    if not text: return ""
    try: return GoogleTranslator(source='auto', target='ko').translate(text)
    except: return text

def get_rescue_thumbnail(entry):
    link = entry.get('link')
    # 1. RSS 표준 태그 시도
    if 'media_content' in entry: return entry.media_content[0]['url']
    if 'media_thumbnail' in entry: return entry.media_thumbnail[0]['url']
    
    # 2. Open Graph 직접 추출
    if link:
        try:
            res = requests.get(link, timeout=1.0)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                og_img = soup.find("meta", property="og:image")
                if og_img: return og_img["content"]
        except: pass

    # 3. 썸네일 부재 시 웹사이트 실시간 스크린샷 서비스 이용 (WordPress mshot API)
    if link:
        return f"https://s.wordpress.com/mshots/v1/{link}?w=600"
    
    return "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=600&q=80"

# --- 3. UI 스타일 정의 ---
st.set_page_config(page_title="Samsung NOD Center", layout="wide")
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;700&display=swap');
    body { font-family: 'Noto Sans KR', sans-serif; background-color: #f4f7fa; }
    .top-card { background: white; padding: 24px; border-radius: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); border-top: 6px solid #034EA2; height: 100%; display: flex; flex-direction: column; }
    .thumbnail { width: 100%; height: 190px; object-fit: cover; border-radius: 14px; margin-bottom: 12px; }
    .title-ko { font-size: 1.1rem; font-weight: 700; color: #1a1c1e; line-height: 1.4; margin-bottom: 6px; }
    .title-en { font-size: 0.8rem; color: #888; font-style: italic; margin-bottom: 10px; }
    .badge { background: #eef2ff; color: #034EA2; padding: 4px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: 700; margin-bottom: 10px; display: inline-block; }
</style>
""", unsafe_allow_html=True)

# --- 4. 데이터 엔진 ---
def get_ai_model():
    try:
        genai.configure(api_key=st.session_state.settings["api_key"])
        available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        target = next((m for m in available if "1.5-flash" in m), available[0])
        return genai.GenerativeModel(target)
    except: return None

@st.cache_data(ttl=3600)
def fetch_sensing_data():
    all_news = []
    limit = datetime.now() - timedelta(days=st.session_state.settings["sensing_period"])
    model = get_ai_model()
    
    total_feeds = sum(len(feeds) for feeds in st.session_state.settings["channels"].values())
    processed = 0
    p_bar = st.progress(0)

    for cat, feeds in st.session_state.settings["channels"].items():
        for f in feeds:
            if not f["active"]: 
                processed += 1
                continue
            d = feedparser.parse(f["url"])
            for entry in d.entries[:5]:
                try:
                    p_date = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    if p_date < limit: continue
                    
                    if model:
                        check = model.generate_content(f"기준: {st.session_state.settings['filter_prompt']}\n제목: {entry.title}\n부합하면 'True', 아니면 'False'만 답해.")
                        if "true" not in check.text.lower(): continue

                    # 중복 에러 방지를 위한 고유 ID 생성 (URL 해싱)
                    unique_id = hashlib.md5(entry.link.encode()).hexdigest()[:12]

                    all_news.append({
                        "id": unique_id,
                        "title_en": entry.title,
                        "title_ko": natural_translate(entry.title),
                        "summary_ko": natural_translate(BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:300]),
                        "img": get_rescue_thumbnail(entry),
                        "source": f["name"], "category": cat,
                        "date": p_date.strftime("%m/%d"), "link": entry.link
                    })
                except: continue
            processed += 1
            p_bar.progress(processed / total_feeds)
    
    p_bar.empty()
    all_news.sort(key=lambda x: x['date'], reverse=True)
    return all_news

# --- 5. 사이드바 (API 키 UI 개선) ---
with st.sidebar:
    st.title("🛡️ NOD Control")
    
    # API 키 입력창 가변 처리
    if "show_api_input" not in st.session_state: st.session_state.show_api_input = False
    
    current_key = st.session_state.settings.get("api_key", "")
    
    if current_key and not st.session_state.show_api_input:
        st.success("✅ Gemini Key 등록됨")
        if st.button("키 수정"):
            st.session_state.show_api_input = True
            st.rerun()
    else:
        new_key = st.text_input("Gemini API Key", value=current_key, type="password")
        if st.button("저장 및 적용"):
            st.session_state.settings["api_key"] = new_key
            st.session_state.show_api_input = False
            save_settings(st.session_state.settings)
            st.rerun()

    st.divider()
    st.subheader("🌐 Sensing Channels")
    for cat, feeds in st.session_state.settings["channels"].items():
        with st.expander(cat):
            for f in feeds:
                f["active"] = st.checkbox(f["name"], value=f["active"], key=f"ch_{f['name']}")

    st.divider()
    with st.expander("⚙️ Advanced Setup"):
        st.session_state.settings["filter_prompt"] = st.text_area("News Filter", value=st.session_state.settings["filter_prompt"], height=120)
        st.session_state.settings["ai_prompt"] = st.text_area("Strategy Analysis", value=st.session_state.settings["ai_prompt"], height=120)
        st.session_state.settings["sensing_period"] = st.slider("Period", 1, 30, st.session_state.settings["sensing_period"])
        if st.button("Save Configuration"):
            save_settings(st.session_state.settings)
            st.toast("저장되었습니다!")

# --- 6. 메인 화면 (Top 6 + Stream View) ---
st.title("🚀 Samsung NOD Strategy Hub")
news_data = fetch_sensing_data()

if news_data:
    # 🌟 Top 6 Picks
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
                    <a href="{item['link']}" target="_blank" style="font-size:0.8rem; color:#034EA2; text-decoration:none; margin-top:auto;">🔗 원본 기사 읽기</a>
                </div>
                """, unsafe_allow_html=True)
                # 고유 해시 ID를 키로 사용하여 중복 에러 방지
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
                # hashlib 기반 ID로 중복 에러 해결
                if st.button("Quick Analysis", key=f"list_btn_{item['id']}"):
                    model = get_ai_model()
                    res = model.generate_content(f"{st.session_state.settings['ai_prompt']}\n내용: {item['title_en']} - {item['summary_ko']}")
                    st.success(res.text)
            st.markdown("---")
else:
    st.info("조건에 맞는 혁신 뉴스가 없습니다.")
