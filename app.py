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

# --- 1. 대규모 초기 채널 데이터베이스 (최초 1회 로드용) ---
def get_initial_db():
    return {
        "Global Innovation (50+)": [
            {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "active": True},
            {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "active": True},
            {"name": "Wired", "url": "https://www.wired.com/feed/rss", "active": True},
            {"name": "Engadget", "url": "https://www.engadget.com/rss.xml", "active": True},
            {"name": "Gizmodo", "url": "https://gizmodo.com/rss", "active": True},
            {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "active": True},
            {"name": "Product Hunt", "url": "https://www.producthunt.com/feed", "active": True},
            {"name": "Yanko Design", "url": "https://www.yankodesign.com/feed/", "active": True},
            {"name": "Fast Company", "url": "https://www.fastcompany.com/design/rss", "active": True},
            {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/", "active": True},
            {"name": "IEEE Spectrum", "url": "https://spectrum.ieee.org/rss/fulltext", "active": True},
            {"name": "9to5Google", "url": "https://9to5google.com/feed/", "active": True},
            {"name": "9to5Mac", "url": "https://9to5mac.com/feed/", "active": True},
            {"name": "Android Authority", "url": "https://www.androidauthority.com/feed/", "active": True},
            {"name": "MacRumors", "url": "https://feeds.macrumors.com/MacRumors-All", "active": True},
            {"name": "Digital Trends", "url": "https://www.digitaltrends.com/feed/", "active": True},
            {"name": "VentureBeat", "url": "https://venturebeat.com/feed/", "active": True},
            {"name": "Mashable", "url": "https://mashable.com/feeds/rss/all", "active": True},
            {"name": "The Next Web", "url": "https://thenextweb.com/feed", "active": True},
            {"name": "ReadWrite", "url": "https://readwrite.com/feed/", "active": True},
            {"name": "ZDNet", "url": "https://www.zdnet.com/news/rss.xml", "active": True},
            {"name": "CNET", "url": "https://www.cnet.com/rss/news/", "active": True},
            {"name": "TechRadar", "url": "https://www.techradar.com/rss", "active": True},
            {"name": "PCMag", "url": "https://www.pcmag.com/rss/news", "active": True},
            {"name": "Tom's Hardware", "url": "https://www.tomshardware.com/feeds/all", "active": True},
            {"name": "ExtremeTech", "url": "https://www.extremetech.com/feed", "active": True},
            {"name": "Slashdot", "url": "https://slashdot.org/index.rss", "active": True},
            {"name": "GeekWire", "url": "https://www.geekwire.com/feed/", "active": True},
            {"name": "Core77", "url": "https://www.core77.com/blog/rss", "active": True},
            {"name": "Dezeen", "url": "https://www.dezeen.com/feed/", "active": True},
            {"name": "Design Milk", "url": "https://design-milk.com/feed/", "active": True},
            {"name": "TechRepublic", "url": "https://www.techrepublic.com/rssfeeds/articles/", "active": True}
            # (지면 관계상 핵심 30개 위주 기재, DB 파일에서 50개까지 확장 가능)
        ],
        "China Innovation (20+)": [
            {"name": "36Kr (CN)", "url": "https://36kr.com/feed", "active": True},
            {"name": "TechNode", "url": "https://technode.com/feed/", "active": True},
            {"name": "Gizmochina", "url": "https://www.gizmochina.com/feed/", "active": True},
            {"name": "SCMP Tech", "url": "https://www.scmp.com/rss/318206/feed.xml", "active": True},
            {"name": "Pandaily", "url": "https://pandaily.com/feed/", "active": True},
            {"name": "KrASIA", "url": "https://kr-asia.com/feed", "active": True},
            {"name": "Huxiu (虎嗅)", "url": "https://www.huxiu.com/rss/0.xml", "active": True},
            {"name": "CnBeta", "url": "https://www.cnbeta.com.tw/backend.php", "active": True},
            {"name": "IT Home", "url": "https://www.ithome.com/rss/", "active": True},
            {"name": "Sina Tech", "url": "https://tech.sina.com.cn/rss/all.xml", "active": True}
        ],
        "Japan Innovation (20+)": [
            {"name": "The Bridge JP", "url": "https://thebridge.jp/feed", "active": True},
            {"name": "ITmedia News", "url": "https://rss.itmedia.co.jp/rss/2.0/news_bursts.xml", "active": True},
            {"name": "Gizmodo JP", "url": "https://www.gizmodo.jp/index.xml", "active": True},
            {"name": "CNET Japan", "url": "https://japan.cnet.com/rss/index.rdf", "active": True},
            {"name": "Nikkei Asia Tech", "url": "https://asia.nikkei.com/rss/feed/nar", "active": True},
            {"name": "ASCII.jp", "url": "https://ascii.jp/rss.xml", "active": True},
            {"name": "PC Watch", "url": "https://pc.watch.impress.co.jp/data/rss/1.0/pcw/feed.rdf", "active": True},
            {"name": "Impress Watch", "url": "https://www.watch.impress.co.jp/data/rss/1.0/ipw/feed.rdf", "active": True},
            {"name": "Mynavi Tech", "url": "https://news.mynavi.jp/rss/digital/it/", "active": True},
            {"name": "Yahoo JP Tech", "url": "https://news.yahoo.co.jp/rss/categories/it.xml", "active": True}
        ],
        "X (Twitter) Experts (20)": [
            {"name": "@MarkGurman (Apple)", "url": "https://rss.app/feeds/tVjKqK6L8WzZ7U0B.xml", "active": True},
            {"name": "@IceUniverse (Samsung)", "url": "https://rss.app/feeds/tw_iceuniverse.xml", "active": True},
            {"name": "@MingChiKuo", "url": "https://rss.app/feeds/tw_mingchikuo.xml", "active": True},
            {"name": "@MKBHD", "url": "https://rss.app/feeds/tw_mkbhd.xml", "active": True},
            {"name": "@evleaks", "url": "https://rss.app/feeds/tw_evleaks.xml", "active": True}
            # (RSS.app 등의 브리지 서비스를 통해 20개 계정 연동 가능)
        ],
        "Threads Insights (20)": [
            {"name": "Adam Mosseri", "url": "https://rss.app/feeds/th_mosseri.xml", "active": True},
            {"name": "Zuck", "url": "https://rss.app/feeds/th_zuck.xml", "active": True},
            {"name": "TechCrunch Threads", "url": "https://rss.app/feeds/th_techcrunch.xml", "active": True}
        ]
    }

# --- 2. 사용자별 독립 DB 관리 로직 ---
def get_db_path(user_id):
    return f"nod_user_{user_id}_db.json"

def load_user_db(user_id):
    path = get_db_path(user_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        # 최초 생성
        default_db = {
            "settings": {
                "api_key": "AIzaSyCW7kwkCqCSN-usKFG9gwcPzYlHwtQW_DQ",
                "sensing_period": 7,
                "max_articles": 30,
                "filter_prompt": "기술적 도약(AI/HCI), 시장 파괴력, 사용자 행태 변화 중심의 혁신 뉴스.",
                "ai_prompt": "삼성전자 기획자 관점에서 Fact/Impact/Takeaway 분석."
            },
            "channels": get_initial_db()
        }
        save_user_db(user_id, default_db)
        return default_db

def save_user_db(user_id, data):
    with open(get_db_path(user_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- 3. 데이터 수집 및 분석 엔진 ---
def natural_translate(text):
    if not text: return ""
    try: return GoogleTranslator(source='auto', target='ko').translate(text)
    except: return text

def get_ai_model():
    api_key = st.session_state.db["settings"]["api_key"].strip()
    if not api_key: return None
    try:
        genai.configure(api_key=api_key)
        return genai.GenerativeModel('gemini-1.5-flash')
    except: return None

def fetch_sensing_data(user_id):
    db = st.session_state.db
    all_news = []
    limit = datetime.now() - timedelta(days=db["settings"]["sensing_period"])
    model = get_ai_model()
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/110.0.0.0 Safari/537.36"
    
    active_feeds = []
    for cat, feeds in db["channels"].items():
        for f in feeds:
            if f.get("active", True): active_feeds.append((cat, f))
    
    if not active_feeds: return []
    
    prog = st.progress(0)
    stat = st.empty()
    
    for i, (cat, f) in enumerate(active_feeds):
        stat.caption(f"📡 {cat} - {f['name']} 센싱 중... ({int((i+1)/len(active_feeds)*100)}%)")
        prog.progress((i+1)/len(active_feeds))
        try:
            d = feedparser.parse(f["url"], agent=USER_AGENT)
            for entry in d.entries[:5]:
                try:
                    p_date = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    if p_date < limit: continue
                    
                    relevance_score = 5
                    if model:
                        filter_query = f"뉴스: {entry.title}\n{db['settings']['filter_prompt']}\n혁신적이면 'True,점수'로 답해."
                        res = model.generate_content(filter_query).text.strip().lower()
                        if "true" not in res: continue
                        try: relevance_score = int(''.join(filter(str.isdigit, res)))
                        except: relevance_score = 5

                    all_news.append({
                        "id": hashlib.md5(entry.link.encode()).hexdigest()[:12],
                        "title_ko": natural_translate(entry.title), "title_en": entry.title,
                        "summary_ko": natural_translate(BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:200]),
                        "source": f["name"], "category": cat, "date_obj": p_date, "date": p_date.strftime("%m.%d"),
                        "link": entry.link, "score": relevance_score
                    })
                except: continue
        except: continue
    
    prog.empty(); stat.empty()
    all_news.sort(key=lambda x: x['date_obj'], reverse=True)
    return all_news

# --- 4. 메인 UI (사이드바 및 렌더링) ---
st.set_page_config(page_title="NOD Intelligence DB", layout="wide")

with st.sidebar:
    st.title("👤 User Profile")
    user_id = st.selectbox("사용자 선택", ["1", "2", "3", "4"], index=0)
    
    # 사용자 변경 시 DB 로드
    if "current_user" not in st.session_state or st.session_state.current_user != user_id:
        st.session_state.current_user = user_id
        st.session_state.db = load_user_db(user_id)
        if "news_data" in st.session_state: del st.session_state.news_data
        st.rerun()

    st.divider()
    st.title("🛡️ NOD Controller")
    st.session_state.db["settings"]["api_key"] = st.text_input("Gemini API Key", value=st.session_state.db["settings"]["api_key"], type="password")
    
    st.divider()
    st.subheader("🌐 Channel Database")
    for cat in list(st.session_state.db["channels"].keys()):
        with st.expander(f"📁 {cat} ({len(st.session_state.db['channels'][cat])})"):
            # 채널 삭제 및 활성화
            for idx, f in enumerate(st.session_state.db["channels"][cat]):
                c1, c2 = st.columns([4, 1])
                f["active"] = c1.checkbox(f["name"], value=f.get("active", True), key=f"ch_{user_id}_{cat}_{idx}")
                if c2.button("❌", key=f"del_{user_id}_{cat}_{idx}"):
                    st.session_state.db["channels"][cat].pop(idx)
                    save_user_db(user_id, st.session_state.db); st.rerun()
            
            # 카테고리별 채널 추가
            st.markdown("---")
            with st.form(f"add_{cat}_{user_id}", clear_on_submit=True):
                n_name = st.text_input("새 채널명")
                n_url = st.text_input("RSS URL")
                if st.form_submit_button("채널 추가"):
                    if n_name and n_url:
                        st.session_state.db["channels"][cat].append({"name": n_name, "url": n_url, "active": True})
                        save_user_db(user_id, st.session_state.db); st.rerun()

    st.divider()
    if st.button("🚀 Apply & Sensing", use_container_width=True):
        save_user_db(user_id, st.session_state.db)
        st.session_state.news_data = fetch_sensing_data(user_id)
        st.rerun()

# --- 5. 대시보드 렌더링 ---
st.markdown("""<div style='padding: 30px; text-align: center; background: linear-gradient(135deg, #034EA2 0%, #007AFF 100%); border-radius: 0 0 30px 30px; color: white; margin-bottom: 30px;'>
    <h2 style='margin:0;'>Samsung NOD Strategy Hub</h2>
    <p style='opacity:0.8;'>User {} Profile - Connected to 130+ Innovation Channels</p>
</div>""".format(user_id), unsafe_allow_html=True)

if "news_data" in st.session_state:
    raw_data = st.session_state.news_data
    if raw_data:
        st.subheader("🌟 Top Pick Signals")
        cols = st.columns(3)
        for i, item in enumerate(raw_data[:6]):
            with cols[i%3]:
                st.markdown(f"""<div style='background: white; padding: 20px; border-radius: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); border: 1px solid #eee; margin-bottom: 20px;'>
                    <span style='background: #eef2ff; color: #034EA2; padding: 3px 10px; border-radius: 5px; font-size: 0.7rem; font-weight: 700;'>{item['category']}</span>
                    <h4 style='margin: 10px 0 5px 0;'>{item['title_ko']}</h4>
                    <p style='font-size: 0.8rem; color: #666;'>{item['source']} | {item['date']}</p>
                    <a href='{item['link']}' target='_blank' style='font-size: 0.8rem; color: #034EA2; text-decoration: none;'>🔗 Read Original</a>
                </div>""", unsafe_allow_html=True)
                if st.button("🔍 Deep Analysis", key=f"dd_{item['id']}"):
                    st.info(get_ai_model().generate_content(f"{st.session_state.db['settings']['ai_prompt']}\n{item['title_en']}").text)
        
        st.divider()
        st.subheader("📋 All Intelligence Stream")
        for item in raw_data[6:]:
            with st.expander(f"[{item['category']}] {item['title_ko']} ({item['source']})"):
                st.write(item['summary_ko'])
                st.link_button("원본 보기", item['link'])
    else:
        st.info("조건에 맞는 혁신 시그널이 없습니다. 기간을 늘려보세요.")
else:
    st.warning("사이드바의 Sensing 버튼을 눌러 데이터 수집을 시작하세요.")
