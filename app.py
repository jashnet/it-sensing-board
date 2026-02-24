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
import socket

# --- 1. 기본 채널 데이터 (최초 1회 로드용) ---
def get_default_channels():
    return {
        "Global Innovation": [
            {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "active": True},
            {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "active": True},
            {"name": "Wired", "url": "https://www.wired.com/feed/rss", "active": True},
            {"name": "Engadget", "url": "https://www.engadget.com/rss.xml", "active": True},
            {"name": "Gizmodo", "url": "https://gizmodo.com/rss", "active": True},
            {"name": "Product Hunt", "url": "https://www.producthunt.com/feed", "active": True},
            {"name": "Yanko Design", "url": "https://www.yankodesign.com/feed/", "active": True},
            {"name": "Fast Company", "url": "https://www.fastcompany.com/design/rss", "active": True},
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
        "China AI/HW": [
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
        "Japan Innovation": [
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

# --- 2. 설정 및 데이터베이스 로드/저장 ---
def get_user_settings(user_id):
    filename = f"nod_user_{user_id}_db.json"
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        # 최초 실행 시 기본값 생성
        new_settings = {
            "api_key": "AIzaSyCW7kwkCqCSN-usKFG9gwcPzYlHwtQW_DQ",
            "sensing_period": 7,
            "max_articles": 30,
            "filter_prompt": "기술적 도약(AI/HCI), 시장 파괴력, 사용자 행태 변화 중심의 혁신 뉴스.",
            "ai_prompt": "삼성전자 기획자 관점에서 Fact/Impact/Takeaway 3단계 분석 수행.",
            "channels": get_default_channels(),
            "category_active": {"Global Innovation": True, "China AI/HW": True, "Japan Innovation": True}
        }
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(new_settings, f, ensure_ascii=False, indent=4)
        return new_settings

def save_user_settings(user_id, data):
    filename = f"nod_user_{user_id}_db.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- 3. 유틸리티 함수 ---
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
    return f"https://s.wordpress.com/mshots/v1/{link}?w=600" if link else ""

def get_ai_model():
    api_key = st.session_state.settings.get("api_key", "").strip()
    if not api_key: return None
    try:
        genai.configure(api_key=api_key)
        return genai.GenerativeModel('gemini-1.5-flash')
    except: return None

# --- 4. 데이터 엔진 (전략적 필터 로직 포함) ---
def fetch_sensing_data(settings):
    all_news = []
    limit = datetime.now() - timedelta(days=settings["sensing_period"])
    model = get_ai_model()
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/110.0.0.0 Safari/537.36"
    socket.setdefaulttimeout(15)

    active_feeds = []
    for cat, feeds in settings["channels"].items():
        if settings["category_active"].get(cat, True):
            for f in feeds:
                if f.get("active", True): active_feeds.append((cat, f))
    
    if not active_feeds: return []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    processed = 0

    for cat, f in active_feeds:
        processed += 1
        status_text.caption(f"📡 {cat} - {f['name']} 센싱 중... ({int(processed/len(active_feeds)*100)}%)")
        progress_bar.progress(processed/len(active_feeds))
        
        try:
            d = feedparser.parse(f["url"], agent=USER_AGENT)
            for entry in d.entries[:8]:
                try:
                    p_date = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    if p_date < limit: continue
                    
                    relevance_score = 5
                    if model:
                        filter_query = f"뉴스제목: {entry.title}\n가이드: {settings['filter_prompt']}\n혁신적이면 'True,점수(1-10)'로 답해."
                        res = model.generate_content(filter_query).text.strip().lower()
                        if "true" not in res: continue
                        try: relevance_score = int(''.join(filter(str.isdigit, res)))
                        except: relevance_score = 5

                    all_news.append({
                        "id": hashlib.md5(entry.link.encode()).hexdigest()[:12],
                        "title_en": entry.title, "title_ko": natural_translate(entry.title),
                        "summary_ko": natural_translate(BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:250]),
                        "img": get_rescue_thumbnail(entry),
                        "source": f["name"], "category": cat, "date_obj": p_date, "date": p_date.strftime("%Y.%m.%d"),
                        "link": entry.link, "score": relevance_score
                    })
                except: continue
        except: continue
    
    progress_bar.empty(); status_text.empty()
    all_news.sort(key=lambda x: x['date_obj'], reverse=True)
    return all_news

# --- 5. 사이드바 (사용자/채널/필터 관리) ---
st.set_page_config(page_title="NOD Intelligence Hub", layout="wide")

with st.sidebar:
    st.title("👤 User Profile")
    user_id = st.radio("사용자 선택", ["1", "2", "3", "4"], horizontal=True)
    
    # 세션에 설정 로드
    if "current_user" not in st.session_state or st.session_state.current_user != user_id:
        st.session_state.current_user = user_id
        st.session_state.settings = get_user_settings(user_id)
        if "news_data" in st.session_state: del st.session_state.news_data
        st.rerun()

    st.divider()
    st.title("🛡️ NOD Controller")
    
    # API 키 관리
    if "show_api" not in st.session_state: st.session_state.show_api = False
    if not st.session_state.show_api:
        if st.button("🔑 API Key 수정"): st.session_state.show_api = True; st.rerun()
    else:
        new_key = st.text_input("Gemini API Key", value=st.session_state.settings["api_key"], type="password")
        if st.button("✅ 적용"): 
            st.session_state.settings["api_key"] = new_key; st.session_state.show_api = False
            save_user_settings(user_id, st.session_state.settings); st.rerun()

    st.divider()
    st.subheader("🌐 Channel Management")
    for cat in list(st.session_state.settings["channels"].keys()):
        st.session_state.settings["category_active"][cat] = st.toggle(f"{cat} 그룹 활성화", value=st.session_state.settings["category_active"].get(cat, True))
        if st.session_state.settings["category_active"][cat]:
            with st.expander(f"{cat} 상세"):
                # 채널 리스트 및 삭제
                for idx, f in enumerate(st.session_state.settings["channels"][cat]):
                    col_ch, col_del = st.columns([4, 1])
                    f["active"] = col_ch.checkbox(f["name"], value=f.get("active", True), key=f"ch_{user_id}_{cat}_{idx}")
                    if col_del.button("❌", key=f"del_{user_id}_{cat}_{idx}"):
                        st.session_state.settings["channels"][cat].pop(idx)
                        save_user_settings(user_id, st.session_state.settings); st.rerun()
                
                # 채널 추가 폼
                st.markdown("---")
                st.caption("➕ 새 채널 추가")
                with st.form(f"add_{cat}_{user_id}", clear_on_submit=True):
                    add_name = st.text_input("채널명")
                    add_url = st.text_input("RSS URL")
                    if st.form_submit_button("채널 저장"):
                        if add_name and add_url:
                            st.session_state.settings["channels"][cat].append({"name": add_name, "url": add_url, "active": True})
                            save_user_settings(user_id, st.session_state.settings); st.rerun()

    st.divider()
    with st.expander("⚙️ 고급 필터 설정"):
        st.session_state.settings["sensing_period"] = st.slider("수집 기간 (일)", 1, 30, st.session_state.settings["sensing_period"])
        st.session_state.settings["filter_prompt"] = st.text_area("필터 프롬프트", value=st.session_state.settings["filter_prompt"])
        st.session_state.settings["ai_prompt"] = st.text_area("분석 가이드", value=st.session_state.settings["ai_prompt"])

    if st.button("🚀 Apply & Sensing Start", use_container_width=True):
        save_user_settings(user_id, st.session_state.settings)
        if "news_data" in st.session_state: del st.session_state.news_data
        st.rerun()

# --- 6. 메인 렌더링 ---
st.markdown("""<div style='padding: 40px; text-align: center; background: linear-gradient(135deg, #034EA2 0%, #007AFF 100%); border-radius: 0 0 40px 40px; color: white; margin-bottom: 40px;'>
    <h1 style='margin:0;'>Samsung NOD Intelligence Hub</h1>
    <p style='opacity:0.8;'>User {} Profile - Strategic Technology Sensing</p>
</div>""".format(user_id), unsafe_allow_html=True)

if "news_data" not in st.session_state:
    st.session_state.news_data = fetch_sensing_data(st.session_state.settings)

raw_data = st.session_state.news_data

if raw_data:
    st.subheader("🌟 Strategic Top Picks")
    top_6 = raw_data[:6]
    rows = [top_6[i:i+3] for i in range(0, len(top_6), 3)]
    for row in rows:
        cols = st.columns(3)
        for j, item in enumerate(row):
            with cols[j]:
                st.markdown(f"""<div style='background: white; padding: 25px; border-radius: 28px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); border: 1px solid #edf2f7; height: 100%;'>
                    <div style='background: #eef2ff; color: #034EA2; padding: 4px 12px; border-radius: 100px; font-size: 0.7rem; font-weight: 700; display: inline-block; margin-bottom: 12px;'>{item['source']} | {item['date']}</div>
                    <img src="{item['img']}" style='width:100%; height:180px; object-fit:cover; border-radius:20px; margin-bottom:15px;'>
                    <div style='font-weight:700; font-size:1.1rem; line-height:1.4;'>{item['title_ko']}</div>
                    <div style='font-size:0.8rem; color:#888; font-style:italic; margin-bottom:10px;'>{item['title_en']}</div>
                    <div style='font-size:0.85rem; color:#4a5568; line-height:1.6;'>{item['summary_ko'][:150]}...</div>
                    <a href="{item['link']}" target="_blank" style='font-size:0.8rem; color:#034EA2; text-decoration:none; margin-top:10px; display:block;'>🔗 원본 기사 읽기</a>
                </div>""", unsafe_allow_html=True)
                if st.button("🔍 Deep-dive", key=f"dd_{item['id']}"):
                    st.info(get_ai_model().generate_content(f"{st.session_state.settings['ai_prompt']}\n내용: {item['title_en']}").text)

    st.divider()
    st.subheader("📋 Sensing Stream")
    with st.container():
        c1, c2, c3 = st.columns([2, 2, 2])
        with c1: sort_val = st.selectbox("📅 정렬", ["최신순", "AI 관련도순"])
        with c2: cat_val = st.multiselect("📂 카테고리", list(st.session_state.settings["channels"].keys()), default=list(st.session_state.settings["channels"].keys()))
        with c3: search_val = st.text_input("🔍 검색")

    stream_data = [d for d in raw_data[6:] if d["category"] in cat_val]
    if search_val: stream_data = [d for d in stream_data if search_val.lower() in d["title_ko"].lower()]
    if sort_val == "최신순": stream_data.sort(key=lambda x: x["date_obj"], reverse=True)
    else: stream_data.sort(key=lambda x: x["score"], reverse=True)

    for item in stream_data[:st.session_state.settings["max_articles"]]:
        col_img, col_txt = st.columns([1, 4])
        with col_img: st.image(item['img'], use_container_width=True)
        with col_txt:
            st.markdown(f"**{item['title_ko']}**")
            st.caption(f"{item['source']} | {item['date']} | {item['category']}")
            if st.button("Quick View", key=f"qa_{item['id']}"):
                st.success(get_ai_model().generate_content(f"요약: {item['title_en']}").text)
        st.markdown("---")
else:
    st.info("조건에 맞는 뉴스가 없습니다. 기간을 늘리거나 필터를 조정해 보세요.")
