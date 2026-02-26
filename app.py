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
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

# 👇 프롬프트 외부 연동
from prompts import GEMS_PERSONA, DEFAULT_FILTER_PROMPT

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
        "sensing_period": 3,
        "max_articles": 60,
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
# 📡 [수집 엔진] 뉴스 크롤링 및 초고속 병렬 필터링 (수동 실행용)
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
            if 'media_content' in entry and len(entry.media_content) > 0:
                thumbnail = entry.media_content[0].get('url', '')
            elif 'media_thumbnail' in entry and len(entry.media_thumbnail) > 0:
                thumbnail = entry.media_thumbnail[0].get('url', '')
                
            articles.append({
                "id": hashlib.md5(entry.link.encode()).hexdigest()[:12],
                "title_en": entry.title, "link": entry.link, "source": f["name"],
                "category": cat, "date_obj": p_date, "date": p_date.strftime("%Y.%m.%d"),
                "summary_en": BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:300],
                "thumbnail": thumbnail
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
    with ThreadPoolExecutor(max_workers=40) as executor:
        futures = [executor.submit(fetch_raw_news, t) for t in active_tasks]
        for f in as_completed(futures): raw_news.extend(f.result())
    
    raw_news = sorted(raw_news, key=lambda x: x['date_obj'], reverse=True)[:settings["max_articles"]]
    
    client = get_ai_client(settings["api_key"])
    filtered_list = []
    
    if not client or not _prompt: 
        for item in raw_news:
            item["score"] = 100
            item["insight_title"] = safe_translate(item["title_en"])
            item["core_summary"] = safe_translate(item["summary_en"])
            filtered_list.append(item)
        return filtered_list

    pb = st.progress(0)
    st_text = st.empty()
    current_ctx = get_script_run_ctx()

    def ai_scoring_worker(item):
        add_script_run_ctx(ctx=current_ctx)
        try:
            import random
            time.sleep(random.uniform(0.1, 1.5))

            score_query = f"{_prompt}\n\n[평가 대상]\n제목: {item['title_en']}\n요약: {item['summary_en'][:200]}"
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=score_query
            )
            res = response.text.strip()
            json_match = re.search(r'\{.*\}', res, re.DOTALL)
            
            if json_match:
                parsed_data = json.loads(json_match.group())
                item['score'] = int(parsed_data.get('score', 50))
                item['insight_title'] = parsed_data.get('insight_title') or safe_translate(item['title_en'])
                item['core_summary'] = parsed_data.get('core_summary') or safe_translate(item['summary_en'])
            else:
                raise ValueError("JSON 형식을 찾을 수 없음")
                
        except Exception as e:
            print(f"❌ 분석 실패 [{item['title_en'][:15]}...]: {e}")
            item['score'] = 50 
            item['insight_title'] = safe_translate(item['title_en'])
            item['core_summary'] = safe_translate(item['summary_en'])
        return item

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_item = {executor.submit(ai_scoring_worker, item): item for item in raw_news}
        
        for i, future in enumerate(as_completed(future_to_item)):
            st_text.caption(f"⚡ AI 수석 전략가가 실시간 분석 중입니다... ({i+1}/{len(raw_news)})")
            pb.progress((i + 1) / len(raw_news))
            
            item = future.result()
            if item['score'] >= _weight:
                filtered_list.append(item)
                
    st_text.empty()
    pb.empty()
    return sorted(filtered_list, key=lambda x: x.get('score', 0), reverse=True)

# ==========================================
# 🖥️ [UI] 메인 화면 렌더링 (MUST KNOW + Top Picks + Stream)
# ==========================================
st.set_page_config(page_title="NGEPT Strategy Hub", layout="wide")

st.markdown("""<style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
    
    /* 공통 히어로 카드 오버레이 스타일 (MUST KNOW & Top Picks 호환) */
    .hero-card {
        position: relative; border-radius: 16px; overflow: hidden;
        aspect-ratio: 4/3; margin-bottom: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        transition: transform 0.2s;
    }
    .hero-card:hover { transform: translateY(-3px); }
    .hero-bg { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; z-index: 1; }
    .hero-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: linear-gradient(to bottom, rgba(0,0,0,0.1) 0%, rgba(0,0,0,0.85) 100%); z-index: 2; }
    .hero-content { position: absolute; bottom: 0; left: 0; width: 100%; padding: 20px; z-index: 3; color: white; }
    
    /* 뱃지 스타일 */
    .badge { display: inline-block; padding: 4px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 700; margin-bottom: 8px; margin-right: 6px; }
    .badge-fire { background: #e74c3c; color: white; }
    .badge-score { background: #34495e; color: white; }
    .badge-global { background: #9b59b6; color: white; }
    .badge-china { background: #e67e22; color: white; }
    
    .hero-title { font-size: 1.2rem; font-weight: 800; line-height: 1.3; margin-bottom: 8px; text-shadow: 0 1px 3px rgba(0,0,0,0.5); }
    .hero-source { font-size: 0.85rem; opacity: 0.9; }

    /* Sensing Stream 카드 스타일 */
    .stream-card { background: #ffffff; border: 1px solid #dbdbdb; border-radius: 12px; margin-bottom: 30px; overflow: hidden; }
    .stream-header { padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #efefef; }
    .source-badge { display: flex; align-items: center; gap: 10px; }
    .source-icon { width: 28px; height: 28px; background: #f0f2f5; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 14px; }
    .source-name { font-weight: 600; font-size: 0.9rem; color: #262626; }
    .stream-score { background-color: #E3F2FD; color: #1565C0; padding: 4px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 700; }
    .stream-img { width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; }
    .stream-body { padding: 16px; }
    .stream-title { font-weight: 700; font-size: 1.05rem; line-height: 1.4; color: #262626; margin-bottom: 10px; }
    .stream-text { font-size: 0.9rem; color: #444; line-height: 1.5; margin-bottom: 16px; }
    .read-more { color: #0095f6; font-weight: 600; text-decoration: none; font-size: 0.9rem; }
    
    .section-header { font-size: 1.5rem; font-weight: 700; margin: 30px 0 20px 0; display: flex; align-items: center; gap: 10px; border-bottom: 2px solid #f0f0f0; padding-bottom: 10px; }
    .section-desc { font-size: 1rem; color: #888; font-weight: normal; margin-left: 5px; }
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
    
    if "GEMINI_API_KEY" in st.secrets:
        st.session_state.settings["api_key"] = st.secrets["GEMINI_API_KEY"]
        st.success("🔒 시스템 API Key 연동 완료")
    else:
        curr_key = st.session_state.settings.get("api_key", "").strip()
        if not st.session_state.get("editing_key", False) and curr_key:
            st.success("✅ 수동 API Key 연동됨")
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
    st.subheader("🎛️ 기본 필터 설정")
    f_weight = st.slider("🎯 최소 매칭 점수", 0, 100, st.session_state.settings["filter_weight"])
    st.session_state.settings["sensing_period"] = st.slider("최근 N일 기사만 수집", 1, 30, st.session_state.settings["sensing_period"])
    st.session_state.settings["max_articles"] = st.slider("최대 분석 기사 수", 30, 100, st.session_state.settings["max_articles"])

    with st.expander("⚙️ 고급 프롬프트 설정", expanded=False):
        f_prompt = st.text_area("🔍 필터 프롬프트", value=st.session_state.settings["filter_prompt"], height=200)
        st.session_state.settings["ai_prompt"] = st.text_area("📝 분석 프롬프트", value=st.session_state.settings["ai_prompt"], height=100)

    st.info("💡 평소엔 아침 자동 수집본을 보여줍니다. 즉시 최신 뉴스를 보려면 아래 버튼을 누르세요.")
    if st.button("🚀 실시간 수동 센싱 시작", use_container_width=True, type="primary"):
        st.session_state.settings["filter_prompt"] = f_prompt
        st.session_state.settings["filter_weight"] = f_weight
        save_user_settings(u_id, st.session_state.settings)
        
        with st.spinner("📡 현재 기준 최신 기사 수집 및 AI 분석 중..."):
            live_result = get_filtered_news(
                st.session_state.settings, 
                st.session_state.channels, 
                st.session_state.settings["filter_prompt"], 
                st.session_state.settings["filter_weight"]
            )
            st.session_state.manual_news = live_result
            st.success("✅ 실시간 업데이트 완료!")
            time.sleep(1)
            st.rerun()
            
    if st.button("♻️ 원래 아침(자동) 버전으로 돌아가기", use_container_width=True):
        if "manual_news" in st.session_state:
            del st.session_state["manual_news"]
        st.rerun()

# ==========================================
# 2. 메인 컨텐츠 영역
# ==========================================
st.markdown("<h1 style='text-align:center;'>NOD Strategy Hub</h1>", unsafe_allow_html=True)
st.caption(f"<div style='text-align:center;'>차세대 경험기획팀을 위한 Gems 통합 인사이트 보드</div><br>", unsafe_allow_html=True)

news_list = []
if "manual_news" in st.session_state:
    news_list = st.session_state.manual_news
    st.success("📡 **Live Mode:** 수동으로 실시간 수집한 뉴스를 보고 계십니다.")
elif os.path.exists("today_news.json"):
    try:
        with open("today_news.json", "r", encoding="utf-8") as f:
            news_list = json.load(f)
        st.info("🕒 **Batch Mode:** 매일 아침 자동 수집된 데일리 브리핑입니다.")
    except Exception as e:
        pass

if not news_list:
    st.warning("📭 보여줄 뉴스가 없습니다. 좌측의 [🚀 실시간 수동 센싱 시작] 버튼을 눌러주세요!")
else:
    # 💡 [큐레이션 알고리즘] 기사 군집화 및 분배
    def get_word_set(text): 
        # 특수문자를 제외한 영문/숫자 단어 집합 생성
        return set(re.findall(r'\w+', str(text).lower()))

    clusters = []
    for item in news_list:
        item_words = get_word_set(item.get('title_en', ''))
        if not item_words: continue

        added = False
        for cluster in clusters:
            cluster_words = get_word_set(cluster[0].get('title_en', ''))
            if not cluster_words: continue
            
            overlap = len(item_words.intersection(cluster_words))
            min_len = min(len(item_words), len(cluster_words))
            # 주요 단어가 40% 이상 겹치면 같은 이슈로 묶음
            if min_len > 0 and overlap / min_len >= 0.4:
                cluster.append(item)
                added = True
                break
        
        if not added:
            clusters.append([item])

    # 1순위: 묶인 기사 수(중복도), 2순위: 그 안에서 가장 높은 AI 점수
    clusters.sort(key=lambda x: (len(x), max([a.get('score', 0) for a in x])), reverse=True)

    must_know_items = []
    used_ids = set()

    # 1. 🔥 MUST KNOW 추출 (최대 3개)
    for cluster in clusters[:3]:
        # 군집 내에서 가장 점수가 높은 기사를 대표로 선정
        best_item = max(cluster, key=lambda x: x.get('score', 0))
        best_item['dup_count'] = len(cluster)
        must_know_items.append(best_item)
        # 같은 이슈의 다른 기사들은 이후 피드에 도배되지 않도록 블랙리스트 처리
        for a in cluster: used_ids.add(a['id'])

    remaining_news = [a for a in news_list if a['id'] not in used_ids]

    # 2. 🏆 Top Picks 추출 (Global 3개, China 3개)
    global_picks = [a for a in remaining_news if a['category'] == 'Global Innovation'][:3]
    china_picks = [a for a in remaining_news if a['category'] == 'China & East Asia'][:3]
    top_picks = global_picks + china_picks
    for a in top_picks: used_ids.add(a['id'])

    # 만약 채널 부족 등으로 6개가 다 안 채워지면 점수순으로 보충
    if len(top_picks) < 6:
        pool = [a for a in remaining_news if a['id'] not in used_ids]
        # 점수 내림차순 정렬
        pool.sort(key=lambda x: x.get('score', 0), reverse=True)
        fillers = pool[:6 - len(top_picks)]
        top_picks += fillers
        for a in fillers: used_ids.add(a['id'])

    # 3. 🌊 Sensing Stream (나머지 전부)
    stream_news = [a for a in remaining_news if a['id'] not in used_ids]

    # ==========================
    # 🔥 Section 1: MUST KNOW
    # ==========================
    if must_know_items:
        st.markdown("<div class='section-header'>🔥 MUST KNOW <span class='section-desc'>여러 매체에서 동시다발적으로 보도 중인 핵심 이슈</span></div>", unsafe_allow_html=True)
        cols = st.columns(3)
        for i, item in enumerate(must_know_items):
            with cols[i % 3]:
                img_src = item.get('thumbnail') if item.get('thumbnail') else f"https://s.wordpress.com/mshots/v1/{item['link']}?w=800"
                # 2개 이상 중복 시 뱃지 표시, 1개면 핵심 트렌드로 표시
                dup_badge = f"🔥 {item['dup_count']}개 매체 중복 보도" if item.get('dup_count', 1) > 1 else "🔥 핵심 트렌드"
                
                html_card = f"""
                <a href="{item['link']}" target="_blank" style="text-decoration:none;">
                    <div class="hero-card" style="border: 2px solid #e74c3c;">
                        <img src="{img_src}" class="hero-bg" loading="lazy" onerror="this.src='https://via.placeholder.com/800x600/1a1a1a/ffffff?text=MUST+KNOW';">
                        <div class="hero-overlay"></div>
                        <div class="hero-content">
                            <span class="badge badge-fire">{dup_badge}</span>
                            <span class="badge badge-score">MATCH {item['score']}%</span>
                            <div class="hero-title">{item.get('insight_title', item['title_en'])}</div>
                            <div class="hero-source">📰 {item['source']}</div>
                        </div>
                    </div>
                </a>
                """
                st.markdown(html_card, unsafe_allow_html=True)

    # ==========================
    # 🏆 Section 2: Today's Top Picks
    # ==========================
    if top_picks:
        st.markdown("<div class='section-header'>🏆 Today's Top Picks <span class='section-desc'>글로벌 & 중국 주요 시그널 (3:3 밸런스)</span></div>", unsafe_allow_html=True)
        cols = st.columns(3)
        for i, item in enumerate(top_picks):
            with cols[i % 3]:
                img_src = item.get('thumbnail') if item.get('thumbnail') else f"https://s.wordpress.com/mshots/v1/{item['link']}?w=800"
                
                # 카테고리별 맞춤 뱃지 색상 부여
                cat_badge = ""
                if item['category'] == 'Global Innovation': cat_badge = "<span class='badge badge-global'>🌐 Global</span>"
                elif item['category'] == 'China & East Asia': cat_badge = "<span class='badge badge-china'>🇨🇳 China</span>"
                else: cat_badge = f"<span class='badge' style='background:#7f8c8d;'>{item['category'][:6]}</span>"
                
                html_card = f"""
                <a href="{item['link']}" target="_blank" style="text-decoration:none;">
                    <div class="hero-card">
                        <img src="{img_src}" class="hero-bg" loading="lazy" onerror="this.src='https://via.placeholder.com/800x600/1a1a1a/ffffff?text=TOP+PICK';">
                        <div class="hero-overlay"></div>
                        <div class="hero-content">
                            {cat_badge}
                            <span class="badge badge-score">MATCH {item['score']}%</span>
                            <div class="hero-title">{item.get('insight_title', item['title_en'])}</div>
                            <div class="hero-source">📰 {item['source']}</div>
                        </div>
                    </div>
                </a>
                """
                st.markdown(html_card, unsafe_allow_html=True)

    # ==========================
    # 🌊 Section 3: Sensing Stream
    # ==========================
    if stream_news:
        st.divider()
        st.markdown("<div class='section-header'>🌊 Sensing Stream <span class='section-desc'>기타 관심 동향 타임라인</span></div>", unsafe_allow_html=True)
        stream_cols = st.columns(3)
        for i, item in enumerate(stream_news):
            with stream_cols[i % 3]:
                img_src = item.get('thumbnail') if item.get('thumbnail') else f"https://s.wordpress.com/mshots/v1/{item['link']}?w=600"
                title_text = item.get('insight_title', item['title_en'])
                summary_text = item.get('core_summary', item.get('summary_ko', ''))
                
                html_card = f"""
                <div class="stream-card">
                    <div class="stream-header">
                        <div class="source-badge">
                            <div class="source-icon">📰</div>
                            <div class="source-name">{item['source']}</div>
                        </div>
                        <span class="stream-score">MATCH {item['score']}%</span>
                    </div>
                    <img src="{img_src}" class="stream-img" loading="lazy" onerror="this.src='https://via.placeholder.com/600x338?text=No+Image';">
                    <div class="stream-body">
                        <div class="stream-title">💡 {title_text}</div>
                        <div class="stream-text">{summary_text}</div>
                        <a href="{item['link']}" target="_blank" class="read-more">원문 기사 읽기 ↗</a>
                    </div>
                </div>
                """
                st.markdown(html_card, unsafe_allow_html=True)
                
                if st.button("🔍 Gems Deep Analysis", key=f"btn_{item['id']}", use_container_width=True):
                    current_api_key = st.session_state.settings.get("api_key", "").strip()
                    if not current_api_key:
                        st.warning("⚠️ API Key를 확인해주세요.")
                    else:
                        client = get_ai_client(current_api_key)
                        if client:
                            with st.spinner("💎 수석 전략가가 분석 중입니다..."):
                                try:
                                    config = types.GenerateContentConfig(system_instruction=GEMS_PERSONA)
                                    prompt = f"{st.session_state.settings['ai_prompt']}\n\n[기사]\n제목: {item['title_en']}\n요약: {item['summary_en']}"
                                    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt, config=config)
                                    st.info(response.text)
                                except Exception as e:
                                    st.error(f"🚨 분석 오류: {e}")
