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

# --- 1. 설정 및 고도화된 채널 리스트 (글로벌 20+, 중국 10+, 일본 10+) ---
SETTINGS_FILE = "nod_samsung_pro_v5.json"
DEFAULT_API_KEY = "AIzaSyCW7kwkCqCSN-usKFG9gwcPzYlHwtQW_DQ"

def default_settings():
    return {
        "api_key": DEFAULT_API_KEY,
        "slack_webhook": "",
        "sensing_period": 7,
        "filter_prompt": """당신은 삼성전자의 차세대 경험기획(Next-Gen UX) 전문가입니다. 
        향후 2~3년 내의 미래 신규 제품(Mobile/Wearable), 혁신적 인터페이스(HCI), 파괴적 AI 기능, 스타트업의 신규 디바이스 시도에 해당하는 뉴스만 'True'로 판별하세요. 
        단순 기업 실적, 일반 앱 업데이트, 단순 주식 정보는 제외하세요.""",
        "ai_prompt": """삼성전자(Samsung) 기획자 관점에서 3단계 분석을 수행하라:
        a) Fact Summary: 핵심 사실 요약 (한국어로 자연스럽게)
        b) 3-Year Future Impact: 향후 3년 내 스마트폰/웨어러블 에코시스템 및 사용자 행태에 미칠 변화 예측.
        c) Samsung Takeaway: 삼성 제품/경험 혁신을 위한 구체적 제언 및 시사점.""",
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

# --- 2. 자연스러운 번역 및 강력한 썸네일 엔진 ---
def natural_translate(text):
    if not text: return ""
    try:
        # 자연스러운 한국어 구사를 위해 문맥 유지 번역 시도
        return GoogleTranslator(source='auto', target='ko').translate(text)
    except: return text

def get_rescue_thumbnail(entry):
    link = entry.get('link')
    # 1. RSS 표준 태그
    if 'media_content' in entry: return entry.media_content[0]['url']
    if 'media_thumbnail' in entry: return entry.media_thumbnail[0]['url']
    
    # 2. Open Graph 직접 추출 (기본 requests 사용)
    if link:
        try:
            res = requests.get(link, timeout=1.0)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                og_img = soup.find("meta", property="og:image")
                if og_img: return og_img["content"]
        except: pass
    
    # 3. 고품질 테크 이미지 플레이스홀더
    return "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=600&q=80"

# --- 3. UI 스타일 정의 (Samsung One 컨셉) ---
st.set_page_config(page_title="Samsung NOD Center", layout="wide")
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;700&display=swap');
    body { font-family: 'Noto Sans KR', sans-serif; background-color: #f4f7fa; }
    .top-card { background: white; padding: 24px; border-radius: 24px; box-shadow: 0 10px 40px rgba(0,0,0,0.05); border-top: 6px solid #034EA2; height: 100%; transition: 0.3s; }
    .top-card:hover { transform: translateY(-5px); }
    .list-item { background: white; padding: 18px; border-radius: 16px; margin-bottom: 12px; border-left: 5px solid #034EA2; box-shadow: 0 2px 10px rgba(0,0,0,0.02); }
    .thumbnail { width: 100%; height: 200px; object-fit: cover; border-radius: 16px; margin-bottom: 16px; }
    .title-ko { font-size: 1.15rem; font-weight: 700; color: #1a1c1e; line-height: 1.4; margin-bottom: 6px; }
    .title-en { font-size: 0.85rem; color: #777; font-style: italic; margin-bottom: 12px; }
    .badge { background: #eef2ff; color: #034EA2; padding: 4px 12px; border-radius: 8px; font-size: 0.75rem; font-weight: 700; margin-bottom: 10px; display: inline-block; }
</style>
""", unsafe_allow_html=True)

# --- 4. 데이터 엔진 ---
def get_ai_model():
    try:
        genai.configure(api_key=st.session_state.settings["api_key"])
        # 사용 가능한 모델 실시간 탐색
        available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        target = next((m for m in available if "1.5-flash" in m), available[0])
        return genai.GenerativeModel(target)
    except: return None

@st.cache_data(ttl=3600)
def fetch_sensing_data():
    all_news = []
    limit = datetime.now() - timedelta(days=st.session_state.settings["sensing_period"])
    model = get_ai_model()

    # Progress bar 표시
    progress_text = st.empty()
    p_bar = st.progress(0)
    
    total_feeds = sum(len(feeds) for feeds in st.session_state.settings["channels"].values())
    processed = 0

    for cat, feeds in st.session_state.settings["channels"].items():
        for f in feeds:
            if not f["active"]: 
                processed += 1
                continue
            d = feedparser.parse(f["url"])
            for entry in d.entries[:5]: # 각 소스별 최신 5개
                try:
                    p_date = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    if p_date < limit: continue
                    
                    # AI 뉴스 필터 (필터 프롬프트 적용)
                    if model:
                        check = model.generate_content(f"기준: {st.session_state.settings['filter_prompt']}\n뉴스제목: {entry.title}\n부합하면 'True', 아니면 'False'로만 답해.")
                        if "true" not in check.text.lower(): continue

                    all_news.append({
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

# --- 5. 사이드바 및 메인 대시보드 ---
with st.sidebar:
    st.title("🛡️ NOD Control")
    st.session_state.settings["api_key"] = st.text_input("Gemini API Key", value=st.session_state.settings["api_key"], type="password")
    
    st.divider()
    st.subheader("🌐 Sensing Channels")
    for cat, feeds in st.session_state.settings["channels"].items():
        with st.expander(f"{cat}"):
            for f in feeds:
                f["active"] = st.checkbox(f"{f['name']}", value=f["active"], key=f"ch_{f['name']}")

    st.divider()
    with st.expander("⚙️ Advanced Setup"):
        st.session_state.settings["filter_prompt"] = st.text_area("News Filter", value=st.session_state.settings["filter_prompt"], height=120)
        st.session_state.settings["ai_prompt"] = st.text_area("Strategy Analysis", value=st.session_state.settings["ai_prompt"], height=120)
        st.session_state.settings["sensing_period"] = st.slider("Period", 1, 30, st.session_state.settings["sensing_period"])
        if st.button("Save Configuration"):
            save_settings(st.session_state.settings)
            st.toast("저장되었습니다! 🚀")

st.title("🚀 Samsung Next-Gen Experience Sensing")
st.caption(f"전 세계 45개 핵심 소스에서 차세대 혁신 신호를 감지합니다.")

news_data = fetch_sensing_data()

if news_data:
    # Top 6 Picks (Card View)
    st.subheader("🌟 Top Strategic Picks")
    top_6 = news_data[:6]
    grid = [top_6[i:i+3] for i in range(0, len(top_6), 3)]
    for row in grid:
        cols = st.columns(3)
        for j, item in enumerate(row):
            with cols[j]:
                st.markdown(f"""
                <div class="top-card">
                    <div class="badge">{item['source']} | {item['date']}</div>
                    <img src="{item['img']}" class="thumbnail">
                    <div class="title-ko">{item['title_ko']}</div>
                    <div class="title-en">{item['title_en']}</div>
                    <div style="font-size:0.85rem; color:#555; height:60px; overflow:hidden;">{item['summary_ko']}...</div>
                </div>
                """, unsafe_allow_html=True)
                if st.button("🔍 Strategic Deep-dive", key=f"top_{item['link'][-10:]}"):
                    model = get_ai_model()
                    with st.spinner("Samsung 전략 분석 리포트 생성 중..."):
                        res = model.generate_content(f"{st.session_state.settings['ai_prompt']}\n내용: {item['title_en']} - {item['summary_ko']}")
                        st.info(res.text)

    st.divider()

    # Full Stream (List View)
    st.subheader("📋 Sensing Stream")
    for item in news_data[6:]:
        with st.container():
            col_img, col_txt = st.columns([1, 4])
            with col_img:
                st.image(item['img'], use_container_width=True)
            with col_txt:
                st.markdown(f"""<div class="list-item">
                    <div class="badge">{item['category']} | {item['source']}</div>
                    <div class="title-ko">{item['title_ko']}</div>
                    <div class="title-en">{item['title_en']}</div>
                    <div style="font-size:0.85rem;">{item['summary_ko'][:200]}...</div>
                </div>""", unsafe_allow_html=True)
                if st.button("Quick Analysis", key=f"list_{item['link'][-10:]}"):
                    model = get_ai_model()
                    res = model.generate_content(f"{st.session_state.settings['ai_prompt']}\n내용: {item['title_en']} - {item['summary_ko']}")
                    st.success(res.text)
            st.markdown("---")
else:
    st.info("현재 필터 조건에 부합하는 혁신 뉴스가 없습니다. 기간이나 필터 기준을 조정해 보세요.")
