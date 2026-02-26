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
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
from collections import Counter

# 프롬프트 외부 연동
from prompts import GEMS_PERSONA, DEFAULT_FILTER_PROMPT

# ==========================================
# 📂 [데이터 관리] 채널 파일 및 캐시 파일 입출력
# ==========================================
CHANNELS_FILE = "channels.json"
MANUAL_CACHE_FILE = "manual_cache.json" # 💡 신규: 수동 센싱 결과를 저장할 파일

def load_channels_from_file():
    if os.path.exists(CHANNELS_FILE):
        try:
            with open(CHANNELS_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return {}
    return {}

def save_channels_to_file(channels_data):
    try:
        with open(CHANNELS_FILE, "w", encoding="utf-8") as f: json.dump(channels_data, f, ensure_ascii=False, indent=4)
    except: pass

def load_user_settings(user_id):
    fn = f"nod_samsung_user_{user_id}.json"
    default_settings = {
        "api_key": "", "sensing_period": 3, "max_articles": 60, "filter_weight": 70,
        "top_picks_count": 6, "top_picks_global_ratio": 50,
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
# 🧠 [AI 엔진] & 💡 [모달 UI]
# ==========================================
def get_ai_client(api_key):
    if not api_key or len(api_key.strip()) < 10: return None
    try: return genai.Client(api_key=api_key.strip())
    except: return None

@st.cache_data(ttl=3600)
def safe_translate(text):
    if not text: return ""
    try: return GoogleTranslator(source='auto', target='ko').translate(text)
    except: return text

@st.dialog("🤖 AI 수석 전략가 심층 분석 리포트", width="large")
def show_analysis_modal(item, api_key, persona, base_prompt):
    col1, col2 = st.columns([1, 2])
    with col1:
        img_src = item.get('thumbnail') if item.get('thumbnail') else f"https://s.wordpress.com/mshots/v1/{item['link']}?w=600"
        html_content = (
            '<div style="border-radius: 12px; overflow: hidden; border: 1px solid #eaeaea; background: #fdfdfd;">'
            f'<img src="{img_src}" style="width:100%; aspect-ratio:16/9; object-fit:cover; display:block; border-bottom: 1px solid #eaeaea;">'
            '<div style="padding: 16px;">'
            f'<span style="background-color:#E3F2FD; color:#1565C0; padding:4px 8px; border-radius:12px; font-size:0.7rem; font-weight:700; display:inline-block; margin-bottom:8px;">MATCH {item.get("score", 0)}%</span>'
            f'<div style="font-weight: 800; font-size: 1.05rem; margin-bottom: 8px; line-height: 1.4; color: #262626;">{item.get("insight_title", item.get("title_en", ""))}</div>'
            f'<div style="font-size: 0.85rem; color: #555; line-height: 1.5; margin-bottom: 12px;">{item.get("core_summary", item.get("summary_ko", ""))}</div>'
            f'<a href="{item.get("link", "#")}" target="_blank" style="display:block; font-size:0.85rem; font-weight:bold; color:#0095f6; text-decoration:none;">원문 기사 열기 ↗</a>'
            '</div></div>'
        )
        st.markdown(html_content, unsafe_allow_html=True)
        
    with col2:
        if not api_key:
            st.error("⚠️ 사이드바에 API Key가 없습니다.")
            return
        with st.spinner("💎 핵심 시그널과 기획 아이디어를 도출 중입니다..."):
            client = get_ai_client(api_key)
            if client:
                try:
                    config = types.GenerateContentConfig(system_instruction=persona)
                    analysis_prompt = f"{base_prompt}\n\n[기사 정보]\n제목: {item['title_en']}\n요약: {item['summary_en']}\n**[출력 지침]**\n1. 리포트가 길어지면 안 됩니다. 각 항목은 '2~3줄 이내의 짧은 Bullet Point'로 요약하세요.\n2. 'Implication (기획자 참고 아이디어)' 항목을 마지막에 추가하여 구체적이고 참신한 아이디어를 제안해 주세요."
                    response = client.models.generate_content(model="gemini-2.5-flash", contents=analysis_prompt, config=config)
                    st.markdown(response.text)
                except Exception as e:
                    st.error(f"🚨 분석 중 오류가 발생했습니다: {e}")

@st.dialog("📂 채널 상세 관리", width="large")
def manage_channels_modal(cat):
    st.markdown(f"### 📌 {cat} 채널 목록 수정")
    with st.container(border=True):
        st.markdown("**➕ 새 채널 추가**")
        col_n, col_u, col_b = st.columns([2, 3, 1])
        new_name = col_n.text_input("이름 (예: Verge)", key=f"new_name_{cat}")
        new_url = col_u.text_input("RSS URL", key=f"new_url_{cat}")
        if col_b.button("추가", key=f"add_btn_{cat}", use_container_width=True):
            if new_name and new_url:
                st.session_state.channels[cat].append({"name": new_name, "url": new_url, "active": True})
                save_channels_to_file(st.session_state.channels)
                st.rerun()
    st.divider()
    for idx, f in enumerate(st.session_state.channels[cat]):
        c1, c2 = st.columns([5, 1])
        prev_state = f.get("active", True)
        new_state = c1.checkbox(f["name"], value=prev_state, key=f"modal_cb_{cat}_{idx}")
        if prev_state != new_state:
            st.session_state.channels[cat][idx]["active"] = new_state
            save_channels_to_file(st.session_state.channels)
            st.rerun()
        if c2.button("🗑️ 삭제", key=f"modal_del_{cat}_{idx}", use_container_width=True):
            st.session_state.channels[cat].pop(idx)
            save_channels_to_file(st.session_state.channels)
            st.rerun()

# ==========================================
# 📡 [수집 및 AI 필터링 엔진]
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
            
            thumbnail = ""
            if 'media_content' in entry and len(entry.media_content) > 0: thumbnail = entry.media_content[0].get('url', '')
            elif 'media_thumbnail' in entry and len(entry.media_thumbnail) > 0: thumbnail = entry.media_thumbnail[0].get('url', '')
            if not thumbnail:
                html_content = ""
                if hasattr(entry, 'content') and isinstance(entry.content, list): html_content += entry.content[0].get('value', '')
                if hasattr(entry, 'summary'): html_content += entry.summary
                if html_content:
                    soup = BeautifulSoup(html_content, "html.parser")
                    img_tag = soup.find('img')
                    if img_tag and img_tag.get('src'): thumbnail = img_tag.get('src')

            articles.append({
                "id": hashlib.md5(entry.link.encode()).hexdigest()[:12], "title_en": entry.title, "link": entry.link, "source": f["name"],
                "category": cat, "date_obj": p_date, "date": p_date.strftime("%Y.%m.%d"),
                "summary_en": BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:300], "thumbnail": thumbnail
            })
    except: pass
    return articles

def get_filtered_news(settings, channels_data, _prompt, pb_ui=None, st_text_ui=None):
    # 💡 [핵심 최적화] AI 채점만 하고 필터링은 하지 않은 채 "원본"을 반환합니다.
    active_key = settings.get("api_key", "").strip()
    if not active_key: return []
    limit = datetime.now() - timedelta(days=settings["sensing_period"])
    active_tasks = [(cat, f, limit) for cat, feeds in channels_data.items() if settings["category_active"].get(cat, True) for f in feeds if f.get("active", True)]
    if not active_tasks: return []

    if st_text_ui:
        st_text_ui.markdown("<div style='text-align:center; padding:10px;'><h3 style='color:#0072FF;'>📡 전 세계 RSS 채널에서 최신 뉴스를 수집하고 있습니다... (약 5~10초 소요)</h3></div>", unsafe_allow_html=True)

    raw_news = []
    with ThreadPoolExecutor(max_workers=40) as executor:
        for f in as_completed([executor.submit(fetch_raw_news, t) for t in active_tasks]):
            raw_news.extend(f.result())
            
    fetch_limit = int(settings["max_articles"] * 1.3)
    raw_news = sorted(raw_news, key=lambda x: x['date_obj'], reverse=True)[:fetch_limit]
    
    client = get_ai_client(active_key)
    if not client or not _prompt: return []

    total_items = len(raw_news)
    if total_items == 0:
        if st_text_ui:
            st_text_ui.markdown("<div style='text-align:center; padding:10px;'><h3 style='color:#E74C3C;'>⚠️ 설정된 기간 내에 수집된 기사가 없습니다.</h3></div>", unsafe_allow_html=True)
        return []

    if st_text_ui:
        st_text_ui.markdown(f"<div style='text-align:center; padding:10px;'><h3 style='color:#00C6FF;'>🧠 총 {total_items}개 기사 확보! AI 수석 전략가가 분석을 시작합니다...</h3><p style='font-size:1.1rem; color:#555;'>(0 / {total_items} 완료)</p></div>", unsafe_allow_html=True)

    current_ctx = get_script_run_ctx()
    processed_items = []
    
    def ai_scoring_worker(item):
        add_script_run_ctx(ctx=current_ctx)
        try:
            import random
            time.sleep(random.uniform(0.1, 0.8))
            
            # 방어막: Reddit, V2EX 등은 AI 착각 방지를 위해 명시
            score_query = f"{_prompt}\n\n[평가 대상]\n매체(출처): {item['source']}\n링크: {item['link']}\n제목: {item['title_en']}\n요약: {item['summary_en'][:200]}"
            response = client.models.generate_content(model="gemini-2.5-flash", contents=score_query)
            
            json_match = re.search(r'\{.*\}', response.text.strip(), re.DOTALL)
            if json_match:
                parsed_data = json.loads(json_match.group())
                
                url_lower = item['link'].lower()
                source_lower = item['source'].lower()
                community_domains = ['reddit', 'v2ex', 'hacker news', 'ycombinator', 'clien', 'dcinside', 'blind']
                
                if any(domain in url_lower or domain in source_lower for domain in community_domains):
                    item['content_type'] = 'community'
                else:
                    item['content_type'] = parsed_data.get('content_type', 'news')
                
                item['score'] = int(parsed_data.get('score', 0)) if item['content_type'] == 'news' else 0
                item['insight_title'] = parsed_data.get('insight_title') or safe_translate(item['title_en'])
                item['core_summary'] = parsed_data.get('core_summary') or safe_translate(item['summary_en'])
                item['keywords'] = parsed_data.get('keywords', [])
            else: raise ValueError("JSON Not Found")
        except:
            item['content_type'] = 'news'
            item['score'] = 50 
            item['insight_title'] = safe_translate(item['title_en'])
            item['core_summary'] = safe_translate(item['summary_en'])
            item['keywords'] = []
        return item

    with ThreadPoolExecutor(max_workers=5) as executor:
        for i, future in enumerate(as_completed({executor.submit(ai_scoring_worker, item): item for item in raw_news})):
            if st_text_ui and pb_ui:
                html_msg = f"<div style='text-align:center; padding:10px;'><h3 style='color:#00C6FF;'>📡 AI가 기사 내용과 커뮤니티 버즈를 심층 분석하고 있습니다...</h3><p style='font-size:1.1rem; color:#555;'>({i+1} / {total_items} 완료)</p></div>"
                st_text_ui.markdown(html_msg, unsafe_allow_html=True)
                pb_ui.progress((i + 1) / total_items)
            processed_items.append(future.result())

    news_pool = []
    community_pool = []
    for item in processed_items:
        if item.get('content_type') == 'community': community_pool.append(item)
        else: news_pool.append(item)

    community_keywords = []
    for cp in community_pool:
        kws = cp.get('keywords', [])
        if isinstance(kws, list): community_keywords.extend([str(k).upper() for k in kws])
            
    comm_kw_counts = Counter(community_keywords)
    hot_comm_keywords = set([k for k, v in comm_kw_counts.items() if v >= 1])

    for news in news_pool:
        news_kws = set([str(k).upper() for k in news.get('keywords', [])])
        overlap = news_kws.intersection(hot_comm_keywords)
        if overlap:
            news['score'] = min(100, news['score'] + (len(overlap) * 5))
            news['community_buzz'] = True
            news['buzz_words'] = list(overlap)
        else:
            news['community_buzz'] = False

    # 💡 필터링하지 않고, 점수가 매겨진 전체 뉴스 풀을 저장용으로 반환합니다.
    news_pool = sorted(news_pool, key=lambda x: x.get('score', 0), reverse=True)
    return news_pool

# ==========================================
# 🖥️ [UI] 메인 화면 및 CSS
# ==========================================
st.set_page_config(page_title="NGEPT Sensing Dashboard", layout="wide")

st.markdown("""<style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
    
    [data-testid="stSidebar"] { background-color: #F8FAFC !important; border-right: 1px solid #E2E8F0; }
    .sidebar-label { color: #64748B; font-size: 0.75rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 1.5rem; margin-bottom: 0.75rem; padding-left: 5px; }
    
    div[data-testid="stButton"] button[kind="primary"] { background: linear-gradient(135deg, #00C6FF 0%, #0072FF 100%); color: white; border: none; border-radius: 12px; font-weight: 700; box-shadow: 0 4px 15px rgba(0, 114, 255, 0.25); transition: all 0.2s ease; }
    div[data-testid="stButton"] button[kind="primary"]:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(0, 114, 255, 0.35); }
    
    div[data-testid="stButton"] button[kind="secondary"] { 
        border-radius: 16px !important; 
        min-height: 34px !important;
        height: 34px !important;
        padding: 0 14px !important;
        border: 1px solid #CBD5E1 !important; 
        color: #334155 !important; 
        font-weight: 700 !important; 
        background-color: #FFFFFF !important;
        transition: all 0.2s ease; 
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.85rem !important;
    }
    div[data-testid="stButton"] button[kind="secondary"]:hover { 
        background-color: #F1F5F9 !important; 
        color: #0F172A !important; 
        border-color: #94A3B8 !important; 
    }
    
    div[data-testid="stButton"] button[kind="tertiary"] {
        padding: 0 !important;
        min-height: 34px !important;
        height: 34px !important;
        font-size: 1.2rem !important;
        color: #64748B !important;
        background: transparent !important;
        border: none !important;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    div[data-testid="stButton"] button[kind="tertiary"]:hover {
        color: #0F172A !important;
        background-color: #F1F5F9 !important;
        border-radius: 8px !important;
    }

    .stTextInput>div>div>input { border-radius: 10px; }
    
    .hero-banner { background: linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%); padding: 2rem 2.5rem; border-radius: 16px; text-align: center; margin-bottom: 1.5rem; box-shadow: 0 4px 15px rgba(0,0,0,0.03); border: 1px solid #eaeaea; position: relative; }
    .hero-badge { display: inline-block; background: #2c3e50; color: white; padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: bold; margin-bottom: 12px; letter-spacing: 1px; }
    .hero-h1 { margin: 0; font-size: 2.6rem; font-weight: 900; background: linear-gradient(45deg, #1A2980 0%, #26D0CE 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    
    .hero-img-box { position: relative; border-radius: 8px; overflow: hidden; aspect-ratio: 4/3; margin-bottom: 10px; }
    .hero-bg { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; z-index: 1; }
    .hero-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: linear-gradient(to bottom, rgba(0,0,0,0.1) 0%, rgba(0,0,0,0.85) 100%); z-index: 2; }
    .hero-content { position: absolute; bottom: 0; left: 0; width: 100%; padding: 15px; z-index: 3; color: white; }
    
    .badge { display: inline-block; padding: 4px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 700; margin-bottom: 8px; margin-right: 6px; }
    .badge-fire { background: #e74c3c; color: white; }
    .badge-score { background: #34495e; color: white; }
    .badge-global { background: #9b59b6; color: white; }
    .badge-china { background: #e67e22; color: white; }
    .badge-buzz { background: #f39c12; color: white; }
    .badge-tag { background: #ecf0f1; color: #333; font-weight: 600; padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; margin-right: 8px; display: inline-block; margin-bottom: 8px;}
    
    .hero-title { font-size: 1.15rem; font-weight: 800; line-height: 1.3; margin-bottom: 8px; text-shadow: 0 1px 3px rgba(0,0,0,0.5); }
    
    .section-header { font-size: 1.5rem; font-weight: 700; margin: 30px 0 20px 0; display: flex; align-items: center; gap: 10px; border-bottom: 2px solid #f0f0f0; padding-bottom: 10px; }
    .section-desc { font-size: 1rem; color: #888; font-weight: normal; margin-left: 5px; }
</style>""", unsafe_allow_html=True)

if "channels" not in st.session_state: st.session_state.channels = load_channels_from_file()

with st.sidebar:
    if "current_user" not in st.session_state:
        st.session_state.current_user = "1"
        st.session_state.settings = load_user_settings("1")
    
    active_user = st.session_state.current_user
    
    profile_html = f"""
    <div style="display: flex; align-items: center; background: white; padding: 14px; border-radius: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.04); margin-bottom: 15px; border: 1px solid #F1F5F9;">
        <div style="width: 44px; height: 44px; border-radius: 50%; background: linear-gradient(135deg, #00C6FF 0%, #0072FF 100%); color: white; font-weight: bold; font-size: 1.2rem; display: flex; align-items: center; justify-content: center; margin-right: 14px;">
            {active_user}
        </div>
        <div style="display: flex; flex-direction: column;">
            <p style="font-size: 0.95rem; font-weight: 800; color: #1E293B; margin:0; line-height: 1.2;">NGEPT Leader {active_user}</p>
            <p style="font-size: 0.75rem; color: #64748B; margin:0;">Strategy & Planning</p>
        </div>
    </div>
    """
    st.markdown(profile_html, unsafe_allow_html=True)

    st.markdown("<div class='sidebar-label'>Switch Profile</div>", unsafe_allow_html=True)
    p_cols = st.columns(4)
    for idx, p in enumerate(["1", "2", "3", "4"]):
        btn_type = "primary" if active_user == p else "secondary"
        if p_cols[idx].button(f"👤 {p}", key=f"prof_{p}", type=btn_type, use_container_width=True):
            st.session_state.current_user = p
            st.session_state.settings = load_user_settings(p)
            st.session_state.channels = load_channels_from_file()
            st.rerun()

    st.markdown("<div class='sidebar-label'>API Connection</div>", unsafe_allow_html=True)
    if "GEMINI_API_KEY" in st.secrets:
        st.session_state.settings["api_key"] = st.secrets["GEMINI_API_KEY"]
        st.success("🔒 System API Key Connected")
    else:
        curr_key = st.session_state.settings.get("api_key", "").strip()
        if not st.session_state.get("editing_key", False) and curr_key:
            st.success("✅ Manual API Key Connected")
            if st.button("🔑 Edit Key"): st.session_state.editing_key = True; st.rerun()
        else:
            new_key = st.text_input("Gemini API Key", value=curr_key, type="password", placeholder="Enter your key...")
            if st.button("💾 Save Key"):
                st.session_state.settings["api_key"] = new_key.strip()
                save_user_settings(st.session_state.current_user, st.session_state.settings)
                st.session_state.editing_key = False; st.rerun()

    st.markdown("<div class='sidebar-label'>Data Sources</div>", unsafe_allow_html=True)
    for cat in st.session_state.channels.keys():
        if cat not in st.session_state.settings["category_active"]: st.session_state.settings["category_active"][cat] = True

    for cat in list(st.session_state.channels.keys()):
        is_active = st.session_state.settings["category_active"].get(cat, True)
        c1, c2 = st.columns([5, 1])
        with c1:
            st.session_state.settings["category_active"][cat] = st.toggle(f"{cat} ({len(st.session_state.channels[cat])})", value=is_active)
        with c2:
            if st.button("⚙️", key=f"open_modal_{cat}"):
                manage_channels_modal(cat)

    st.markdown("<div class='sidebar-label'>AI Filters</div>", unsafe_allow_html=True)
    # 💡 UI 실시간 연동을 위해 session_state 값 직접 바인딩
    f_weight = st.slider("🎯 최소 매칭 점수", 0, 100, st.session_state.settings.get("filter_weight", 70))
    st.session_state.settings["filter_weight"] = f_weight
    
    st.session_state.settings["sensing_period"] = st.slider("최근 N일 기사만 수집", 1, 30, st.session_state.settings.get("sensing_period", 3))
    st.session_state.settings["max_articles"] = st.slider("최대 화면 표시 기사 수", 30, 100, st.session_state.settings.get("max_articles", 60))

    st.markdown("<div class='sidebar-label'>Curation Settings</div>", unsafe_allow_html=True)
    current_tp_count = st.session_state.settings.get("top_picks_count", 6)
    current_tp_ratio = st.session_state.settings.get("top_picks_global_ratio", 50)
    
    tp_count_options = [3, 6, 9, 12]
    tp_count = st.selectbox("🏆 Today's Picks 노출 개수", options=tp_count_options, index=tp_count_options.index(current_tp_count) if current_tp_count in tp_count_options else 1)
    tp_ratio = st.slider("🌐 글로벌 뉴스 비율 (%)", min_value=0, max_value=100, value=current_tp_ratio, step=10)
    st.session_state.settings["top_picks_count"] = tp_count
    st.session_state.settings["top_picks_global_ratio"] = tp_ratio

    with st.expander("⚙️ 고급 프롬프트 설정", expanded=False):
        f_prompt = st.text_area("🔍 필터 프롬프트", value=st.session_state.settings["filter_prompt"], height=200)
        st.session_state.settings["ai_prompt"] = st.text_area("📝 분석 프롬프트", value=st.session_state.settings["ai_prompt"], height=100)

    st.markdown("<div class='sidebar-label'>Actions</div>", unsafe_allow_html=True)
    
    if st.button("🚀 실시간 수동 센싱 시작", use_container_width=True, type="primary"):
        st.session_state.settings["filter_prompt"] = f_prompt
        save_user_settings(st.session_state.current_user, st.session_state.settings)
        st.session_state.run_sensing = True
        st.rerun()
            
    if st.button("♻️ 원래 아침(자동) 버전으로 복귀", use_container_width=True):
        st.session_state.is_live_mode = False
        st.rerun()

# ==========================================
# 4. 메인 컨텐츠 영역
# ==========================================
st.markdown("""
<div class="hero-banner">
    <div class="hero-badge">AI-POWERED CURATION</div>
    <h1 class="hero-h1">NGEPT Sensing Dashboard</h1>
</div>
""", unsafe_allow_html=True)

# 💡 [핵심 최적화] 실시간 센싱 버튼 클릭 시 동작
if st.session_state.get("run_sensing", False):
    st.markdown("<br><br>", unsafe_allow_html=True)
    st_text_ui = st.empty()
    pb_ui = st.progress(0)
    
    st_text_ui.markdown("<div style='text-align:center; padding:10px;'><h3 style='color:#0072FF;'>🚀 실시간 데이터 파이프라인 가동 준비 중...</h3></div>", unsafe_allow_html=True)
    st.markdown("<br><br>", unsafe_allow_html=True)
    
    # 여기서 필터링 없이 전체 풀을 로드하여 캐시 파일로 저장합니다.
    all_scored_news = get_filtered_news(
        st.session_state.settings, 
        st.session_state.channels, 
        st.session_state.settings["filter_prompt"], 
        pb_ui, 
        st_text_ui
    )
    
    # 로컬 캐시에 저장
    try:
        with open(MANUAL_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(all_scored_news, f, ensure_ascii=False, indent=4)
        st.session_state.is_live_mode = True
    except Exception as e:
        st.error(f"캐시 저장 실패: {e}")
        
    st_text_ui.empty()
    pb_ui.empty()
    st.session_state.run_sensing = False
    st.rerun()

c1, c2 = st.columns([2, 1])
with c1: st.caption("차세대 경험기획팀을 위한 글로벌/중국 트렌드 심층 분석 보드")
with c2:
    if st.session_state.get("is_live_mode", False):
        st.markdown("<div style='text-align:right; color:#e74c3c; font-weight:bold; font-size:0.9rem;'>📡 Live Mode (실시간 수동 수집)</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div style='text-align:right; color:#3498db; font-weight:bold; font-size:0.9rem;'>🕒 Batch Mode (일일 자동 브리핑)</div>", unsafe_allow_html=True)

# 💡 [핵심] 모드에 따라 읽어올 파일을 결정 (캐싱 로드)
raw_news_pool = []
target_file = MANUAL_CACHE_FILE if st.session_state.get("is_live_mode", False) else "today_news.json"

if os.path.exists(target_file):
    try:
        with open(target_file, "r", encoding="utf-8") as f: 
            raw_news_pool = json.load(f)
    except: pass

# 💡 [프론트엔드 실시간 필터링] 로드한 전체 데이터에서 UI 슬라이더 값에 따라 즉시 필터링
f_weight = st.session_state.settings.get("filter_weight", 70)
news_list = [n for n in raw_news_pool if n.get("score", 0) >= f_weight]

if not raw_news_pool:
    st.warning("📭 수집된 데이터가 없습니다. 좌측의 [🚀 실시간 수동 센싱 시작] 버튼을 눌러주세요!")
elif not news_list:
    st.warning(f"📭 수집은 완료되었으나, 최소 점수({f_weight}점)를 넘는 기사가 없습니다.")
    st.info(f"💡 전체 수집된 **총 {len(raw_news_pool)}개 기사**의 점수 분포를 확인하고 좌측 슬라이더를 조절해 보세요. (AI 재호출 없이 1초만에 화면이 바뀝니다!)")
    
    score_ranges = {"90-100": 0, "70-89": 0, "50-69": 0, "0-49": 0}
    for n in raw_news_pool:
        s = n.get("score", 0)
        if s >= 90: score_ranges["90-100"] += 1
        elif s >= 70: score_ranges["70-89"] += 1
        elif s >= 50: score_ranges["50-69"] += 1
        else: score_ranges["0-49"] += 1
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🔥 90~100점", f"{score_ranges['90-100']}개")
    col2.metric("🏆 70~89점", f"{score_ranges['70-89']}개")
    col3.metric("📝 50~69점", f"{score_ranges['50-69']}개")
    col4.metric("🗑️ 0~49점", f"{score_ranges['0-49']}개")

else:
    # 이하 기존 화면 렌더링 로직 (실시간 반영됨)
    news_list = news_list[:st.session_state.settings.get("max_articles", 60)]
    
    def get_word_set(text): return set(re.findall(r'\w+', str(text).lower()))

    global_news_for_clustering = [item for item in news_list if item.get('category') == 'Global Innovation']
    
    clusters = []
    for item in global_news_for_clustering:
        item_words = get_word_set(item.get('title_en', ''))
        if not item_words: continue
        added = False
        for cluster in clusters:
            cluster_words = get_word_set(cluster[0].get('title_en', ''))
            if not cluster_words: continue
            overlap = len(item_words.intersection(cluster_words))
            min_len = min(len(item_words), len(cluster_words))
            if min_len > 0 and overlap / min_len >= 0.4:
                cluster.append(item)
                added = True
                break
        if not added: clusters.append([item])

    clusters.sort(key=lambda x: (len(x), max([a.get('score', 0) for a in x])), reverse=True)

    must_know_items = []
    used_ids = set()

    for cluster in clusters[:3]:
        best_item = max(cluster, key=lambda x: x.get('score', 0))
        best_item['dup_count'] = len(cluster)
        must_know_items.append(best_item)
        for a in cluster: used_ids.add(a['id'])

    remaining_news = [a for a in news_list if a['id'] not in used_ids]

    total_picks = st.session_state.settings.get("top_picks_count", 6)
    global_ratio = st.session_state.settings.get("top_picks_global_ratio", 50) / 100.0
    global_target = int(total_picks * global_ratio)
    china_target = total_picks - global_target

    global_picks = [a for a in remaining_news if a['category'] == 'Global Innovation'][:global_target]
    china_picks = [a for a in remaining_news if a['category'] == 'China & East Asia'][:china_target]
    top_picks = global_picks + china_picks
    for a in top_picks: used_ids.add(a['id'])

    if len(top_picks) < total_picks:
        pool = [a for a in remaining_news if a['id'] not in used_ids]
        pool.sort(key=lambda x: x.get('score', 0), reverse=True)
        fillers = pool[:total_picks - len(top_picks)]
        top_picks += fillers
        for a in fillers: used_ids.add(a['id'])

    stream_news = [a for a in remaining_news if a['id'] not in used_ids]

    # ==========================
    # 🔥 Section 1: MUST KNOW
    # ==========================
    if must_know_items:
        st.markdown("<div class='section-header'>🔥 MUST KNOW <span class='section-desc'>글로벌 매체 핵심 이슈</span></div>", unsafe_allow_html=True)
        cols = st.columns(3)
        for i, item in enumerate(must_know_items):
            with cols[i % 3]:
                with st.container(border=True):
                    img_src = item.get('thumbnail') if item.get('thumbnail') else f"https://s.wordpress.com/mshots/v1/{item['link']}?w=800"
                    dup_badge = f"🔥 {item['dup_count']}개 매체 중복 보도" if item.get('dup_count', 1) > 1 else "🔥 글로벌 핫트렌드"
                    
                    buzz_badge = ""
                    if item.get('community_buzz'):
                        buzz_words_str = ", ".join(item.get('buzz_words', []))
                        buzz_badge = f"<span class='badge badge-buzz' title='커뮤니티 언급: {buzz_words_str}'>💬 긱(Geek) 화제</span>"
                    
                    html_content = (
                        '<div class="hero-img-box">'
                        f'<img src="{img_src}" class="hero-bg" onerror="this.src=\'https://via.placeholder.com/800x600/1a1a1a/ffffff?text=MUST+KNOW\';">'
                        '<div class="hero-overlay"></div>'
                        '<div class="hero-content">'
                        f'<span class="badge badge-fire">{dup_badge}</span> '
                        f'<span class="badge badge-score">MATCH {item.get("score", 0)}%</span> '
                        f'{buzz_badge}'
                        f'<div class="hero-title">{item.get("insight_title", item.get("title_en", ""))}</div>'
                        '</div></div>'
                    )
                    st.markdown(html_content, unsafe_allow_html=True)
                    
                    act_c1, act_c2, act_c3 = st.columns([5, 2.5, 2.5])
                    with act_c1:
                        st.markdown(f"""
                        <div style='height: 34px; display: flex; align-items: center; font-size: 0.95rem; margin-top: 2px;'>
                            <a href='{item.get("link", "#")}' target='_blank' style='color:#1E293B; font-weight:800; text-decoration:none; margin-right:8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'>📰 {item.get("source", "Source")}</a>
                            <span style='font-size: 0.8rem; color: #64748B; white-space: nowrap;'>{item.get("date", "")}</span>
                        </div>
                        """, unsafe_allow_html=True)
                    with act_c2:
                        if st.button("📤 공유", key=f"share_mk_{item['id']}_{i}", type="secondary", use_container_width=True):
                            st.toast("기사 링크가 복사되었습니다!")
                    with act_c3:
                        if st.button("🤖 AI 분석", key=f"btn_mk_{item['id']}_{i}", type="secondary", use_container_width=True):
                            show_analysis_modal(item, st.session_state.settings.get("api_key", "").strip(), GEMS_PERSONA, st.session_state.settings['ai_prompt'])

    # ==========================
    # 🏆 Section 2: Today's Top Picks
    # ==========================
    if top_picks:
        st.markdown(f"<div class='section-header'>🏆 Today's Top Picks <span class='section-desc'>글로벌 & 중국 큐레이션 (총 {total_picks}개)</span></div>", unsafe_allow_html=True)
        cols = st.columns(3)
        for i, item in enumerate(top_picks):
            with cols[i % 3]:
                with st.container(border=True):
                    img_src = item.get('thumbnail') if item.get('thumbnail') else f"https://s.wordpress.com/mshots/v1/{item['link']}?w=800"
                    
                    cat_badge = ""
                    if item['category'] == 'Global Innovation': cat_badge = "<span class='badge badge-global'>🌐 Global</span>"
                    elif item['category'] == 'China & East Asia': cat_badge = "<span class='badge badge-china'>🇨🇳 China</span>"
                    else: cat_badge = f"<span class='badge' style='background:#7f8c8d;'>{item['category'][:6]}</span>"
                    
                    buzz_badge = ""
                    if item.get('community_buzz'):
                        buzz_words_str = ", ".join(item.get('buzz_words', []))
                        buzz_badge = f"<span class='badge badge-buzz' title='커뮤니티 언급: {buzz_words_str}'>💬 커뮤니티 화제</span>"
                    
                    html_content = (
                        '<div class="hero-img-box">'
                        f'<img src="{img_src}" class="hero-bg" onerror="this.src=\'https://via.placeholder.com/800x600/1a1a1a/ffffff?text=TOP+PICK\';">'
                        '<div class="hero-overlay"></div>'
                        '<div class="hero-content">'
                        f'{cat_badge} '
                        f'<span class="badge badge-score">MATCH {item.get("score", 0)}%</span> '
                        f'{buzz_badge}'
                        f'<div class="hero-title">{item.get("insight_title", item.get("title_en", ""))}</div>'
                        '</div></div>'
                    )
                    st.markdown(html_content, unsafe_allow_html=True)
                    
                    act_c1, act_c2, act_c3 = st.columns([5, 2.5, 2.5])
                    with act_c1:
                        st.markdown(f"""
                        <div style='height: 34px; display: flex; align-items: center; font-size: 0.95rem; margin-top: 2px;'>
                            <a href='{item.get("link", "#")}' target='_blank' style='color:#1E293B; font-weight:800; text-decoration:none; margin-right:8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'>📰 {item.get("source", "Source")}</a>
                            <span style='font-size: 0.8rem; color: #64748B; white-space: nowrap;'>{item.get("date", "")}</span>
                        </div>
                        """, unsafe_allow_html=True)
                    with act_c2:
                        if st.button("공유", key=f"share_tp_{item['id']}_{i}", type="secondary", use_container_width=True):
                            st.toast("기사 링크가 복사되었습니다!")
                    with act_c3:
                        if st.button("AI분석", key=f"btn_tp_{item['id']}_{i}", type="secondary", use_container_width=True):
                            show_analysis_modal(item, st.session_state.settings.get("api_key", "").strip(), GEMS_PERSONA, st.session_state.settings['ai_prompt'])

    # ==========================
    # 🌊 Section 3: Sensing Stream 
    # ==========================
    if stream_news:
        st.divider()
        
        all_tags = []
        for n in news_list:
            if isinstance(n.get('keywords'), list):
                all_tags.extend([str(k).upper() for k in n['keywords']])
        
        top_tags = [tag for tag, count in Counter(all_tags).most_common(8)]
        tag_html = " ".join([f"<span class='badge-tag'>#{t}</span>" for t in top_tags])
        
        st.markdown("<div class='section-header'>🌊 Sensing Stream <span class='section-desc'>기타 관심 동향 타임라인</span></div>", unsafe_allow_html=True)
        if tag_html:
            st.markdown(f"<div style='margin-bottom: 20px;'>{tag_html}</div>", unsafe_allow_html=True)

        stream_cols = st.columns(3)
        for i, item in enumerate(stream_news):
            with stream_cols[i % 3]:
                with st.container(border=True):
                    img_src = item.get('thumbnail') if item.get('thumbnail') else f"https://s.wordpress.com/mshots/v1/{item['link']}?w=600"
                    
                    title_text = item.get('insight_title', item.get('title_en', ''))
                    summary_text = item.get('core_summary', item.get('summary_ko', ''))
                    
                    buzz_tag = ""
                    if item.get('community_buzz'):
                        buzz_tag = "<span style='background:#f39c12; color:white; padding:2px 6px; border-radius:8px; font-size:0.65rem; font-weight:bold; margin-left:5px;'>💬 화제</span>"
                    
                    html_content = (
                        '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">'
                        '<div style="display:flex; align-items:center; gap:8px;">'
                        '<div style="width:24px; height:24px; background:#f0f2f5; border-radius:50%; display:flex; justify-content:center; align-items:center; font-size:12px;">📰</div>'
                        f'<a href="{item.get("link", "#")}" target="_blank" style="font-weight:800; font-size:0.95rem; color:#1E293B; text-decoration:none;">{item.get("source", "Source")}</a>'
                        '</div><div>'
                        f'<span style="background-color:#E3F2FD; color:#1565C0; padding:4px 8px; border-radius:12px; font-size:0.7rem; font-weight:700;">MATCH {item.get("score", 0)}%</span> '
                        f'{buzz_tag}'
                        '</div></div>'
                        f'<img src="{img_src}" style="width:100%; aspect-ratio:16/9; object-fit:cover; border-radius:8px; display:block; margin-bottom:12px;" onerror="this.src=\'https://via.placeholder.com/600x338?text=No+Image\';">'
                        f'<div style="font-weight:700; font-size:1.05rem; line-height:1.4; color:#262626; margin-bottom:8px;">💡 {title_text}</div>'
                        f'<div style="font-size:0.85rem; color:#444; line-height:1.5; margin-bottom:12px;">{summary_text}</div>'
                    )
                    st.markdown(html_content, unsafe_allow_html=True)
                    
                    act_c1, act_c2, act_c3 = st.columns([5, 2.5, 2.5])
                    with act_c1:
                        st.markdown(f"<div style='height: 34px; display: flex; align-items: center; font-size: 0.8rem; color: #64748B; margin-top: 2px;'>{item.get('date', '')}</div>", unsafe_allow_html=True)
                    with act_c2:
                        if st.button("공유", key=f"share_st_{item['id']}_{i}", type="secondary", use_container_width=True):
                            st.toast("기사 링크가 복사되었습니다!")
                    with act_c3:
                        if st.button("AI분석", key=f"btn_st_{item['id']}_{i}", type="secondary", use_container_width=True):
                            show_analysis_modal(item, st.session_state.settings.get("api_key", "").strip(), GEMS_PERSONA, st.session_state.settings['ai_prompt'])
