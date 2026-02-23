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
import socket # 타임아웃 설정을 위해 추가

# --- 1. 설정 및 기본값 ---
SETTINGS_FILE = "nod_samsung_pro_v7.json"
DEFAULT_API_KEY = "AIzaSyCW7kwkCqCSN-usKFG9gwcPzYlHwtQW_DQ"

def default_settings():
    return {
        "api_key": DEFAULT_API_KEY,
        "slack_webhook": "",
        "sensing_period": 7,
        "max_articles": 20,
        "filter_strength": 3,
        "additional_filter": "",
        "filter_prompt": """당신은 삼성전자의 차세대 경험기획(Next-Gen UX) 전문가입니다. 
        혁신적 인터페이스, 파괴적 AI 기능, 스타트업의 신규 디바이스 시도에 해당하는 뉴스 위주로 판별하세요.""",
        "ai_prompt": """삼성전자(Samsung) 기획자 관점에서 3단계 분석을 수행하라:
        a) Fact Summary: 핵심 사실 요약 (한국어로 자연스럽게)
        b) 3-Year Future Impact: 향후 3년 내 에코시스템 변화 예측
        c) Samsung Takeaway: 삼성 제품 혁신을 위한 시사점""",
        "category_active": {"Global Innovation (23)": True, "China AI/HW (11)": True, "Japan Innovation (11)": True},
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

# --- 2. 유틸리티 함수 ---
def natural_translate(text):
    if not text: return ""
    try: return GoogleTranslator(source='auto', target='ko').translate(text)
    except: return text

def get_rescue_thumbnail(entry):
    link = entry.get('link')
    if 'media_content' in entry: return entry.media_content[0]['url']
    if link:
        try:
            res = requests.get(link, timeout=1.0)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                og_img = soup.find("meta", property="og:image")
                if og_img: return og_img["content"]
        except: pass
    return f"https://s.wordpress.com/mshots/v1/{link}?w=600" if link else "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=600&q=80"

# --- 3. 데이터 엔진 (에러 방어 로직 강화) ---
def get_ai_model():
    try:
        genai.configure(api_key=st.session_state.settings["api_key"])
        available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        target = next((m for m in available if "1.5-flash" in m), available[0])
        return genai.GenerativeModel(target)
    except: return None

def fetch_sensing_data(settings):
    all_news = []
    limit = datetime.now() - timedelta(days=settings["sensing_period"])
    model = get_ai_model()
    strength_desc = ["매우 완화됨", "완화됨", "보통", "엄격함", "매우 엄격함"]
    
    # 서버 연결 끊김 방지용 User-Agent
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    socket.setdefaulttimeout(10) # 10초 내 응답 없으면 다음으로

    active_feeds = []
    for cat, feeds in settings["channels"].items():
        if settings["category_active"].get(cat, True):
            for f in feeds:
                if f["active"]: active_feeds.append((cat, f))
    
    total_feeds = len(active_feeds)
    if total_feeds == 0: return []

    progress_bar = st.progress(0)
    status_text = st.empty()
    processed_count = 0

    for cat, f in active_feeds:
        processed_count += 1
        percent = int((processed_count / total_feeds) * 100)
        status_text.caption(f"📡 {cat} - {f['name']} 센싱 중... ({percent}%)")
        progress_bar.progress(processed_count / total_feeds)
        
        try:
            # [수정 지점] agent를 설정하여 차단 방지 및 try-except로 Disconnected 대응
            d = feedparser.parse(f["url"], agent=USER_AGENT)
            
            for entry in d.entries[:10]:
                try:
                    p_date = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    if p_date < limit: continue
                    
                    relevance_score = 5
                    if model:
                        filter_query = f"[제목] {entry.title}\n{settings['filter_prompt']}\n{settings['additional_filter']}\n강도: {strength_desc[settings['filter_strength']-1]}\nTrue/False,점수(1-10) 형식으로 답해."
                        res = model.generate_content(filter_query).text.strip()
                        if "true" not in res.lower(): continue
                        try: relevance_score = int(res.split(",")[-1])
                        except: relevance_score = 5

                    all_news.append({
                        "id": hashlib.md5(entry.link.encode()).hexdigest()[:12],
                        "title_en": entry.title,
                        "title_ko": natural_translate(entry.title),
                        "summary_ko": natural_translate(BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:300]),
                        "img": get_rescue_thumbnail(entry),
                        "source": f["name"], "category": cat,
                        "date_obj": p_date, "date": p_date.strftime("%m/%d"), "link": entry.link,
                        "score": relevance_score
                    })
                except: continue
        except Exception as e:
            # 특정 사이트 연결 실패 시 경고창 대신 로그만 남기고 다음으로 진행
            print(f"Error fetching {f['name']}: {e}")
            continue
    
    status_text.empty()
    progress_bar.empty()
    all_news.sort(key=lambda x: x['date_obj'], reverse=True)
    return all_news

# --- (이후 메인 UI 및 사이드바 로직은 동일) ---
# --- 4. UI 스타일 ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;700&display=swap');
    body { font-family: 'Noto Sans KR', sans-serif; background-color: #f4f7fa; }
    .top-card { background: white; padding: 24px; border-radius: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); border-top: 6px solid #034EA2; height: 100%; display: flex; flex-direction: column; }
    .thumbnail { width: 100%; height: 190px; object-fit: cover; border-radius: 14px; margin-bottom: 12px; }
    .title-ko { font-size: 1.1rem; font-weight: 700; color: #1a1c1e; line-height: 1.4; margin-bottom: 6px; }
    .badge { background: #eef2ff; color: #034EA2; padding: 4px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: 700; display: inline-block; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.title("🛡️ NOD Control")
    if "show_api_input" not in st.session_state: st.session_state.show_api_input = False
    current_key = st.session_state.settings.get("api_key", "")
    if current_key and not st.session_state.show_api_input:
        st.success("✅ Gemini Key 등록됨")
        if st.button("키 수정"): st.session_state.show_api_input = True; st.rerun()
    else:
        new_key = st.text_input("Gemini API Key", value=current_key, type="password")
        if st.button("저장 및 적용"):
            st.session_state.settings["api_key"] = new_key
            st.session_state.show_api_input = False
            save_settings(st.session_state.settings); st.rerun()

    st.divider()
    st.subheader("🌐 Sensing Channels")
    for cat in list(st.session_state.settings["channels"].keys()):
        is_cat_on = st.toggle(f"{cat} 활성화", value=st.session_state.settings["category_active"].get(cat, True), key=f"tog_{cat}")
        st.session_state.settings["category_active"][cat] = is_cat_on
        if is_cat_on:
            with st.expander(f"{cat} 관리"):
                for f in st.session_state.settings["channels"][cat]:
                    f["active"] = st.checkbox(f["name"], value=f["active"], key=f"ch_{f['name']}")
                st.caption("➕ 새 채널 추가")
                with st.form(key=f"add_{cat}", clear_on_submit=True):
                    n_name = st.text_input("이름")
                    n_url = st.text_input("RSS URL")
                    if st.form_submit_button("추가"):
                        if n_name and n_url:
                            st.session_state.settings["channels"][cat].append({"name": n_name, "url": n_url, "active": True})
                            save_settings(st.session_state.settings); st.rerun()

    st.divider()
    with st.expander("⚙️ Advanced Setup", expanded=True):
        st.session_state.settings["filter_prompt"] = st.text_area("News Filter", value=st.session_state.settings["filter_prompt"])
        st.session_state.settings["additional_filter"] = st.text_area("Additional Filter", value=st.session_state.settings.get("additional_filter", ""))
        st.session_state.settings["ai_prompt"] = st.text_area("AI 전략 분석 가이드", value=st.session_state.settings.get("ai_prompt", ""))
        st.session_state.settings["filter_strength"] = st.slider("Filter 강도", 1, 5, st.session_state.settings["filter_strength"])
        st.session_state.settings["max_articles"] = st.selectbox("기사 개수", [10, 20, 30, 50], index=[10, 20, 30, 50].index(st.session_state.settings.get("max_articles", 20)))

    if st.button("🚀 Apply & Sensing Start", use_container_width=True):
        save_settings(st.session_state.settings)
        if "news_data" in st.session_state: del st.session_state.news_data
        st.rerun()

st.title("🚀 NGEPT NOD Sensing Dashboard")
if "news_data" not in st.session_state:
    st.session_state.news_data = fetch_sensing_data(st.session_state.settings)

raw_data = st.session_state.news_data

if raw_data:
    c1, c2, c3 = st.columns([2, 2, 2])
    with c1: sort_mode = st.selectbox("정렬", ["최신순", "과거순", "AI 관련도순"])
    with c2: cat_filter = st.multiselect("카테고리", list(st.session_state.settings["channels"].keys()), default=list(st.session_state.settings["channels"].keys()))
    with c3: search_q = st.text_input("결과 내 검색", "")

    filtered = [d for d in raw_data if d["category"] in cat_filter]
    if search_q: filtered = [d for d in filtered if search_q.lower() in d["title_ko"].lower()]
    if sort_mode == "최신순": filtered.sort(key=lambda x: x["date_obj"], reverse=True)
    elif sort_mode == "과거순": filtered.sort(key=lambda x: x["date_obj"])
    else: filtered.sort(key=lambda x: x["score"], reverse=True)
    
    display_data = filtered[:st.session_state.settings["max_articles"]]

    st.subheader("🌟 Strategic Top Picks")
    top_6 = display_data[:6]
    rows = [top_6[i:i+3] for i in range(0, len(top_6), 3)]
    for row in rows:
        cols = st.columns(3)
        for j, item in enumerate(row):
            with cols[j]:
                st.markdown(f"""<div class="top-card">
                    <div class="badge">{item['source']} | {item['date']}</div>
                    <img src="{item['img']}" class="thumbnail"><div class="title-ko">{item['title_ko']}</div>
                    <a href="{item['link']}" target="_blank" style="font-size:0.8rem; color:#034EA2;">🔗 원본 읽기</a>
                </div>""", unsafe_allow_html=True)
                if st.button("🔍 Deep-dive", key=f"top_{item['id']}"):
                    model = get_ai_model()
                    if model:
                        with st.spinner("Samsung 전략 분석 중..."):
                            try:
                                res = model.generate_content(f"{st.session_state.settings['ai_prompt']}\n내용: {item['title_en']}")
                                st.info(res.text)
                            except Exception as e: st.error(f"분석 오류: {e}")
                    else: st.error("API Key를 확인해주세요.")

    st.divider()
    st.subheader("📋 Sensing Stream")
    for item in display_data[6:]:
        col_img, col_txt = st.columns([1, 4])
        with col_img: st.image(item['img'], use_container_width=True)
        with col_txt:
            st.markdown(f"**{item['title_ko']}**")
            if st.button("Quick Analysis", key=f"list_{item['id']}"):
                model = get_ai_model()
                if model:
                    res = model.generate_content(f"{st.session_state.settings['ai_prompt']}\n내용: {item['title_en']}")
                    st.success(res.text)
        st.markdown("---")
else: st.info("조건에 맞는 뉴스가 없습니다. 설정을 변경하고 Apply 버튼을 눌러보세요.")
