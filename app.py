import streamlit as st
import streamlit.components.v1 as components
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
# 📋 [유틸] 클립보드 복사 함수 (JS Injection)
# ==========================================
def copy_to_clipboard(title, summary, link):
    copy_text = f"[NGEPT Insight]\n제목: {title}\n요약: {summary}\n원문: {link}"
    copy_text = copy_text.replace('`', '\\`').replace('$', '\\$')
    js_code = f"""
    <script>
    const textArea = document.createElement("textarea");
    textArea.value = `{copy_text}`;
    document.body.appendChild(textArea);
    textArea.select();
    try {{ document.execCommand('copy'); }} 
    catch (err) {{ console.error('Copy failed', err); }}
    document.body.removeChild(textArea);
    </script>
    """
    components.html(js_code, height=0, width=0)

# ==========================================
# 🎨 [애니메이션] 스피너 SVG UI 컴포넌트
# ==========================================
SPINNER_SVG = """
<svg width="28" height="28" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" style="vertical-align: middle; margin-right: 10px; margin-bottom: 4px; animation: spin 1s linear infinite;">
    <style>@keyframes spin { 100% { transform: rotate(360deg); } }</style>
    <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 18a8 8 0 1 1 8-8 8 8 0 0 1-8 8z" fill="#E2E8F0"/>
    <path d="M12 2a10 10 0 0 1 10 10h-2A8 8 0 0 0 12 4z" fill="#0072FF"/>
</svg>
"""

# ==========================================
# 📂 [데이터 관리] 채널 파일 입출력
# ==========================================
CHANNELS_FILE = "channels.json"
MANUAL_CACHE_FILE = "manual_cache.json"

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
        "api_key": "", "sensing_period": 14, "max_articles": 50, "filter_weight": 50,
        "top_picks_count": 6, "top_picks_global_ratio": 70,
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

@st.dialog("📤 기사 정보 공유", width="small")
def show_share_modal(item):
    title = item.get("insight_title", item.get("title_en", ""))
    summary = item.get("core_summary", item.get("summary_ko", ""))
    link = item.get("link", "")
    
    share_text = f"[NGEPT Insight]\n📌 제목: {title}\n\n💡 요약: {summary}\n\n🔗 원문: {link}"
    
    st.markdown("<p style='font-size: 0.9rem; color: #475569; margin-bottom: 5px;'>아래 코드 박스 우측 상단의 <b>복사 아이콘(📋)</b>을 누르시면 클립보드에 깔끔하게 저장됩니다.</p>", unsafe_allow_html=True)
    st.code(share_text, language="markdown")

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

@st.dialog("🧠 NGEPT AI 큐레이션 파이프라인", width="large")
def show_help_modal():
    html_content = (
        '<div style="padding: 10px 5px;">'
        '<p style="color: #64748B; font-size: 0.95rem; margin-bottom: 25px;">'
        'NGEPT Sensing Dashboard는 단순한 뉴스 나열이 아닙니다. '
        '구글의 <strong>Gemini 2.5 Flash</strong> 엔진과 <strong>소셜 리스닝(Social Listening)</strong> 기법이 결합된 5단계 심층 큐레이션 파이프라인을 거칩니다.'
        '</p>'
        
        '<div style="display: flex; margin-bottom: 25px; position: relative;">'
        '<div style="width: 40px; height: 40px; border-radius: 50%; background: linear-gradient(135deg, #E2E8F0 0%, #CBD5E1 100%); color: #334155; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 1.1rem; z-index: 2; box-shadow: 0 4px 6px rgba(0,0,0,0.05); flex-shrink: 0;">1</div>'
        '<div style="position: absolute; left: 19px; top: 40px; bottom: -25px; width: 2px; background-color: #E2E8F0; z-index: 1;"></div>'
        '<div style="margin-left: 20px; background: #F8FAFC; padding: 15px; border-radius: 12px; border: 1px solid #F1F5F9; width: 100%;">'
        '<h4 style="margin: 0 0 5px 0; color: #1E293B;">🌐 1. Global Sensing (데이터 수집)</h4>'
        '<p style="margin: 0; color: #475569; font-size: 0.85rem; line-height: 1.5;">전 세계 주요 IT 매체 및 긱(Geek) 커뮤니티(Reddit, V2EX 등)의 RSS 피드에서 설정된 기간(N일) 내의 최신 기사를 1.3배수 확보하여 로딩 속도를 최적화합니다.</p>'
        '</div></div>'

        '<div style="display: flex; margin-bottom: 25px; position: relative;">'
        '<div style="width: 40px; height: 40px; border-radius: 50%; background: linear-gradient(135deg, #00C6FF 0%, #0072FF 100%); color: white; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 1.1rem; z-index: 2; box-shadow: 0 4px 10px rgba(0, 114, 255, 0.3); flex-shrink: 0;">2</div>'
        '<div style="position: absolute; left: 19px; top: 40px; bottom: -25px; width: 2px; background-color: #E2E8F0; z-index: 1;"></div>'
        '<div style="margin-left: 20px; background: #F8FAFC; padding: 15px; border-radius: 12px; border: 1px solid #F1F5F9; width: 100%;">'
        '<h4 style="margin: 0 0 5px 0; color: #1E293B;">🧠 2. AI Deep Scoring (심층 분석 & 필터링)</h4>'
        '<p style="margin: 0; color: #475569; font-size: 0.85rem; line-height: 1.5;">수집된 모든 데이터를 Gemini AI가 분석하여 <b>적합도 점수(0~100점), 기획자 관점의 1줄 요약, 핵심 태그(Keyword), 출처 유형(뉴스 vs 커뮤니티)</b>을 JSON 형태로 즉각 추출해냅니다.</p>'
        '</div></div>'

        '<div style="display: flex; margin-bottom: 25px; position: relative;">'
        '<div style="width: 40px; height: 40px; border-radius: 50%; background: linear-gradient(135deg, #f1c40f 0%, #e67e22 100%); color: white; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 1.1rem; z-index: 2; box-shadow: 0 4px 10px rgba(230, 126, 34, 0.3); flex-shrink: 0;">3</div>'
        '<div style="position: absolute; left: 19px; top: 40px; bottom: -25px; width: 2px; background-color: #E2E8F0; z-index: 1;"></div>'
        '<div style="margin-left: 20px; background: #FFFbeb; padding: 15px; border-radius: 12px; border: 1px solid #Fef08a; width: 100%;">'
        '<h4 style="margin: 0 0 5px 0; color: #b45309;">💬 3. Social Listening (버즈량 융합 엔진)</h4>'
        '<p style="margin: 0; color: #78350f; font-size: 0.85rem; line-height: 1.5;">커뮤니티 글은 노출 명단에서 숨기고 <b>\'트렌드 레이더\'</b>로만 사용합니다. 커뮤니티에서 자주 언급되는 키워드를 다룬 공식 뉴스에는 <b>가산점(+점수)과 [💬 화제] 뱃지</b>를 부여합니다.</p>'
        '</div></div>'

        '<div style="display: flex; margin-bottom: 25px; position: relative;">'
        '<div style="width: 40px; height: 40px; border-radius: 50%; background: linear-gradient(135deg, #9b59b6 0%, #8e44ad 100%); color: white; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 1.1rem; z-index: 2; box-shadow: 0 4px 10px rgba(142, 68, 173, 0.3); flex-shrink: 0;">4</div>'
        '<div style="position: absolute; left: 19px; top: 40px; bottom: -25px; width: 2px; background-color: #E2E8F0; z-index: 1;"></div>'
        '<div style="margin-left: 20px; background: #F8FAFC; padding: 15px; border-radius: 12px; border: 1px solid #F1F5F9; width: 100%;">'
        '<h4 style="margin: 0 0 5px 0; color: #1E293B;">🗂️ 4. Clustering & Curation (군집화 및 배분)</h4>'
        '<p style="margin: 0; color: #475569; font-size: 0.85rem; line-height: 1.5;">단어 유사도를 분석해 중복 이슈를 하나로 묶어(Clustering) <b>\'MUST KNOW\'</b>에 최상단 배치하고, 남은 기사들은 설정하신 비율(글로벌:중국)에 맞춰 <b>\'Top Picks\'</b>에 분배합니다.</p>'
        '</div></div>'
        
        '<div style="display: flex; position: relative;">'
        '<div style="width: 40px; height: 40px; border-radius: 50%; background: linear-gradient(135deg, #2ecc71 0%, #27ae60 100%); color: white; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 1.1rem; z-index: 2; box-shadow: 0 4px 10px rgba(39, 174, 96, 0.3); flex-shrink: 0;">5</div>'
        '<div style="margin-left: 20px; background: #F8FAFC; padding: 15px; border-radius: 12px; border: 1px solid #F1F5F9; width: 100%;">'
        '<h4 style="margin: 0 0 5px 0; color: #1E293B;">🎨 5. Zero-Latency Rendering (캐싱 및 시각화)</h4>'
        '<p style="margin: 0; color: #475569; font-size: 0.85rem; line-height: 1.5;">최종 결과는 로컬(JSON)에 캐싱되어, 팀장님이 슬라이더(점수/개수)를 조작할 때마다 <b>AI 재호출 없이 0.1초 만에 즉각적으로 화면 레이아웃이 갱신</b>됩니다.</p>'
        '</div></div>'
        '</div>'
    )
    st.markdown(html_content, unsafe_allow_html=True)

# ==========================================
# 📡 [수집 및 AI 필터링 엔진]
# ==========================================
def fetch_raw_news(args):
    cat, f, limit = args
    articles = []
    try:
        d = feedparser.parse(f["url"])
        if not d.entries: return []
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
                "id": hashlib.md5(entry.link.encode()).hexdigest()[:12], 
                "title_en": entry.title, 
                "link": entry.link, 
                "source": f["name"],
                "category": cat, 
                "date_obj": p_date.isoformat(), 
                "date": p_date.strftime("%Y.%m.%d"),
                "summary_en": BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:300], 
                "thumbnail": thumbnail
            })
    except Exception as e:
        pass
    return articles

def get_filtered_news(settings, channels_data, _prompt, pb_ui=None, st_text_ui=None):
    active_key = settings.get("api_key", "").strip()
    if not active_key: return []
    limit = datetime.now() - timedelta(days=settings["sensing_period"])
    active_tasks = [(cat, f, limit) for cat, feeds in channels_data.items() if settings["category_active"].get(cat, True) for f in feeds if f.get("active", True)]
    if not active_tasks: return []

    raw_news = []
    total_feeds = len(active_tasks)
    
    if st_text_ui and pb_ui:
        st_text_ui.markdown(f"<div style='text-align:center; padding:10px;'><h3 style='color:#1E293B;'>{SPINNER_SVG} 전 세계 매체에서 최신 뉴스를 수집 중입니다...</h3><p style='font-size:1.1rem; color:#64748B;'>(0 / {total_feeds} 채널 확인 완료)</p></div>", unsafe_allow_html=True)
        pb_ui.progress(0)

    with ThreadPoolExecutor(max_workers=40) as executor:
        futures = [executor.submit(fetch_raw_news, t) for t in active_tasks]
        for i, f in enumerate(as_completed(futures)):
            raw_news.extend(f.result())
            if st_text_ui and pb_ui:
                st_text_ui.markdown(f"<div style='text-align:center; padding:10px;'><h3 style='color:#1E293B;'>{SPINNER_SVG} 전 세계 매체에서 최신 뉴스를 수집 중입니다...</h3><p style='font-size:1.1rem; color:#64748B;'>({i+1} / {total_feeds} 채널 확인 완료)</p></div>", unsafe_allow_html=True)
                pb_ui.progress((i + 1) / total_feeds)
            
    fetch_limit = int(settings["max_articles"] * 1.3)
    raw_news = sorted(raw_news, key=lambda x: x['date_obj'], reverse=True)[:fetch_limit]
    
    client = get_ai_client(active_key)
    if not client or not _prompt: return []

    total_items = len(raw_news)
    if total_items == 0:
        return []

    if st_text_ui and pb_ui:
        st_text_ui.markdown(f"<div style='text-align:center; padding:10px;'><h3 style='color:#1E293B;'>{SPINNER_SVG} 총 {total_items}개 기사 확보! AI 심층 분석을 시작합니다...</h3><p style='font-size:1.1rem; color:#64748B;'>(0 / {total_items} 분석 완료)</p></div>", unsafe_allow_html=True)
        pb_ui.progress(0)

    current_ctx = get_script_run_ctx()
    processed_items = []
    
    def ai_scoring_worker(item):
        add_script_run_ctx(ctx=current_ctx)
        try:
            import random
            time.sleep(random.uniform(0.1, 0.8))
            
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
                html_msg = f"<div style='text-align:center; padding:10px;'><h3 style='color:#1E293B;'>{SPINNER_SVG} AI가 기사 내용과 커뮤니티 버즈를 분석 중입니다...</h3><p style='font-size:1.1rem; color:#64748B;'>({i+1} / {total_items} 분석 완료)</p></div>"
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
    
    /* 사이드바 기본 Primary 버튼 */
    div[data-testid="stButton"] button[kind="primary"] { background: linear-gradient(135deg, #00C6FF 0%, #0072FF 100%); color: white; border: none; border-radius: 12px; font-weight: 700; box-shadow: 0 4px 15px rgba(0, 114, 255, 0.25); transition: all 0.2s ease; }
    div[data-testid="stButton"] button[kind="primary"]:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(0, 114, 255, 0.35); }
    
    /* 사이드바 기본 Secondary/Tertiary 버튼 (원래 크기 유지) */
    div[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="secondary"],
    div[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="tertiary"] {
        border-radius: 12px !important; 
        min-height: 38px !important;
        height: 38px !important;
        font-size: 0.95rem !important;
        padding: 0 14px !important;
    }

    /* 카드 안 액션 버튼: 둥근 사각, 넓은 가로, 0.65rem 텍스트 */
    [data-testid="stMain"] [data-testid="stColumn"] div[data-testid="stButton"] button[kind="secondary"] { 
        border-radius: 6px !important; 
        min-height: 24px !important;  
        height: 24px !important;
        padding: 0 10px !important;   
        border: none !important; 
        color: #0284C7 !important; 
        font-weight: 700 !important; 
        background-color: #E0F2FE !important;
        transition: all 0.2s ease; 
        font-size: 0.65rem !important; 
        white-space: nowrap !important;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    [data-testid="stMain"] [data-testid="stColumn"] div[data-testid="stButton"] button[kind="secondary"]:hover { 
        background-color: #BAE6FD !important; 
        color: #0369A1 !important; 
    }
    
    [data-testid="stMain"] [data-testid="stColumn"] div[data-testid="stButton"] button[kind="tertiary"] {
        border-radius: 6px !important; 
        min-height: 24px !important;  
        height: 24px !important;
        padding: 0 10px !important;   
        border: none !important; 
        color: #475569 !important; 
        font-weight: 700 !important; 
        background-color: #F1F5F9 !important;
        transition: all 0.2s ease; 
        font-size: 0.65rem !important; 
        white-space: nowrap !important;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    [data-testid="stMain"] [data-testid="stColumn"] div[data-testid="stButton"] button[kind="tertiary"]:hover {
        background-color: #E2E8F0 !important; 
        color: #0F172A !important; 
    }
    
    /* 💡 [요청사항 1, 2, 3] 모든 라디오 버튼 (상단 토글 + 하단 필터 공통)을 중앙 정렬 & 블루 컬러 알약 디자인으로 통일 */
    [data-testid="stRadio"] {
        display: flex !important;
        justify-content: center !important; /* 항상 중앙 정렬 */
        width: 100% !important;
    }
    [data-testid="stRadio"] > div[role="radiogroup"] {
        background-color: #F1F5F9 !important; /* 연한 회색 바탕 */
        padding: 4px !important;
        border-radius: 9999px !important; /* 전체를 감싸는 긴 알약 */
        display: inline-flex !important;
        gap: 0 !important;
        border: none !important;
        flex-wrap: wrap !important;
        justify-content: center !important;
    }
    [data-testid="stRadio"] > div[role="radiogroup"] label {
        background-color: transparent !important;
        border: none !important;
        padding: 8px 24px !important; /* 넉넉한 내부 여백 */
        border-radius: 9999px !important; /* 내부 탭도 둥근 알약 */
        margin: 0 !important;
        cursor: pointer !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    [data-testid="stRadio"] > div[role="radiogroup"] label:hover {
        background-color: #E2E8F0 !important;
    }
    /* 라디오 원형 아이콘 완전 삭제 */
    [data-testid="stRadio"] > div[role="radiogroup"] label div[data-baseweb="radio"],
    [data-testid="stRadio"] > div[role="radiogroup"] label > div:first-child {
        display: none !important;
    }
    /* 💡 선택된 탭: 파란색 바탕 + 그림자 */
    [data-testid="stRadio"] > div[role="radiogroup"] label[data-checked="true"],
    [data-testid="stRadio"] > div[role="radiogroup"] label[aria-checked="true"],
    [data-testid="stRadio"] > div[role="radiogroup"] label:has(input:checked) {
        background-color: #0072FF !important; 
        box-shadow: 0 4px 12px rgba(0, 114, 255, 0.25) !important; 
    }
    /* 💡 미선택 텍스트 스타일: 회색 */
    [data-testid="stRadio"] > div[role="radiogroup"] label p {
        color: #64748B !important; 
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    /* 💡 선택 텍스트 스타일: 흰색 */
    [data-testid="stRadio"] > div[role="radiogroup"] label[data-checked="true"] p,
    [data-testid="stRadio"] > div[role="radiogroup"] label[aria-checked="true"] p,
    [data-testid="stRadio"] > div[role="radiogroup"] label:has(input:checked) p {
        color: #FFFFFF !important; 
        font-weight: 800 !important;
    }

    .stTextInput>div>div>input { border-radius: 10px; }
    
    .hero-banner { background: linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%); padding: 2rem 2.5rem; border-radius: 16px; text-align: center; margin-bottom: 1.5rem; box-shadow: 0 4px 15px rgba(0,0,0,0.03); border: 1px solid #eaeaea; position: relative; }
    .hero-badge { display: inline-block; background: #2c3e50; color: white; padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: bold; margin-bottom: 12px; letter-spacing: 1px; }
    .hero-h1 { margin: 0; font-size: 2.6rem; font-weight: 900; background: linear-gradient(45deg, #1A2980 0%, #26D0CE 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .hero-subtitle { margin-top: 15px; font-size: 1.1rem; color: #64748B; font-weight: 600; letter-spacing: -0.5px; margin-bottom: 0; }
    
    .hero-img-box { position: relative; border-radius: 8px; overflow: hidden; aspect-ratio: 4/3; margin-bottom: 5px; }
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

if "view_mode" not in st.session_state:
    st.session_state.view_mode = "데일리 모닝 센싱"

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
    f_weight = st.slider("🎯 최소 매칭 점수", 0, 100, st.session_state.settings.get("filter_weight", 50), help="AI가 평가한 기사 관련도 점수입니다. 점수가 높을수록 검색 조건에 부합합니다.")
    st.session_state.settings["filter_weight"] = f_weight
    
    s_period = st.slider("최근 N일 기사만 수집", 1, 30, st.session_state.settings.get("sensing_period", 14), help="지정된 기간 내의 최신 기사만 수집합니다.")
    st.session_state.settings["sensing_period"] = s_period
    
    m_articles = st.slider("최대 화면 표시 기사 수", 30, 100, st.session_state.settings.get("max_articles", 50), help="대시보드에 노출될 최대 기사 개수입니다.")
    st.session_state.settings["max_articles"] = m_articles

    st.markdown("<div class='sidebar-label'>Curation Settings</div>", unsafe_allow_html=True)
    current_tp_count = st.session_state.settings.get("top_picks_count", 6)
    current_tp_ratio = st.session_state.settings.get("top_picks_global_ratio", 70)
    
    tp_count_options = [3, 6, 9, 12]
    tp_count = st.selectbox("🏆 Today's Picks 노출 개수", options=tp_count_options, index=tp_count_options.index(current_tp_count) if current_tp_count in tp_count_options else 1, help="대시보드 상단 영역에 표시할 핵심 기사의 총 개수입니다.")
    st.session_state.settings["top_picks_count"] = tp_count
    
    tp_ratio = st.slider("🌐 글로벌 뉴스 비율 (%)", min_value=0, max_value=100, value=current_tp_ratio, step=10, help="Top Picks에 글로벌 혁신 기사를 몇 퍼센트(%) 할당할지 결정합니다. 나머지는 중국 동향으로 채워집니다.")
    st.session_state.settings["top_picks_global_ratio"] = tp_ratio

    with st.expander("⚙️ 고급 프롬프트 설정", expanded=False):
        f_prompt = st.text_area("🔍 필터 프롬프트", value=st.session_state.settings["filter_prompt"], height=200)
        st.session_state.settings["filter_prompt"] = f_prompt
        
        a_prompt = st.text_area("📝 분석 프롬프트", value=st.session_state.settings["ai_prompt"], height=100)
        st.session_state.settings["ai_prompt"] = a_prompt

    save_user_settings(st.session_state.current_user, st.session_state.settings)

    st.markdown("<div class='sidebar-label'>Actions</div>", unsafe_allow_html=True)
    
    if st.button("🚀 실시간 수동 센싱 시작", use_container_width=True, type="primary"):
        st.session_state.run_sensing = True
        st.rerun()
        
    if st.button("ℹ️ 시스템 작동 원리 (Help)", use_container_width=True, type="secondary"):
        show_help_modal()

# ==========================================
# 4. 메인 컨텐츠 영역
# ==========================================
st.markdown("""
<div class="hero-banner">
    <div class="hero-badge">AI-POWERED CURATION</div>
    <h1 class="hero-h1">NGEPT Sensing Dashboard</h1>
    <p class="hero-subtitle">차세대 경험기획팀을 위한 데일리 센싱 분석 보드</p>
</div>
""", unsafe_allow_html=True)

if st.session_state.get("run_sensing", False):
    st.session_state.run_sensing = False  # 즉시 끄기 방어막
    st.markdown("<br><br>", unsafe_allow_html=True)
    
    if not st.session_state.settings.get("api_key", "").strip():
        st.error("🛑 사이드바에 Gemini API Key가 없습니다!")
        st.stop()
        
    has_active_channel = False
    for cat, feeds in st.session_state.channels.items():
        if st.session_state.settings["category_active"].get(cat, True) and any(f.get("active", True) for f in feeds):
            has_active_channel = True; break
            
    if not has_active_channel:
        st.error("🛑 수집할 RSS 채널이 없습니다!")
        st.stop()

    st_text_ui = st.empty()
    pb_ui = st.progress(0)
    
    st_text_ui.markdown(f"<div style='text-align:center; padding:10px;'><h3 style='color:#1E293B;'>{SPINNER_SVG} 실시간 데이터 파이프라인 가동 준비 중...</h3></div>", unsafe_allow_html=True)
    st.markdown("<br><br>", unsafe_allow_html=True)
    
    all_scored_news = get_filtered_news(st.session_state.settings, st.session_state.channels, st.session_state.settings["filter_prompt"], pb_ui, st_text_ui)
    
    if not all_scored_news:
        st.error("🛑 수집된 기사가 0개입니다. 수집 기간을 늘려보세요.")
        st.stop()

    try:
        with open(MANUAL_CACHE_FILE, "w", encoding="utf-8") as f: json.dump(all_scored_news, f, ensure_ascii=False, indent=4)
        st.session_state.view_mode = "실시간 수동 센싱"
    except Exception as e:
        st.error(f"🚨 저장 실패: {e}")
        st.stop()
        
    st_text_ui.empty()
    pb_ui.empty()
    st.rerun()

st.markdown("<br>", unsafe_allow_html=True)

# 💡 [요청사항 1, 2] 상단 중앙 정렬된 모드 토글
view_mode = st.radio("모드", ["데일리 모닝 센싱", "실시간 수동 센싱"], horizontal=True, label_visibility="collapsed", key="view_mode")

st.markdown("<br>", unsafe_allow_html=True)

raw_news_pool = []
target_file = MANUAL_CACHE_FILE if st.session_state.view_mode == "실시간 수동 센싱" else "today_news.json"

if os.path.exists(target_file):
    try:
        with open(target_file, "r", encoding="utf-8") as f: raw_news_pool = json.load(f)
    except: pass

f_weight = st.session_state.settings.get("filter_weight", 50)
news_list = [n for n in raw_news_pool if n.get("score", 0) >= f_weight]

if not raw_news_pool:
    if st.session_state.view_mode == "데일리 모닝 센싱":
        st.info("📭 수집된 뉴스가 없습니다.\n\n**데일리 모닝 센싱**은 매일 아침 지정된 시간에 자동으로 실행되어 글로벌 트렌드 뉴스를 수집합니다.")
    else:
        st.info("📭 수집된 뉴스가 없습니다.\n\n좌측 사이드바의 **[🚀 실시간 수동 센싱 시작]** 버튼을 눌러 관심 있는 뉴스를 실시간으로 수집해 보세요.")
elif not news_list:
    st.warning(f"📭 수집은 완료되었으나, 최소 점수({f_weight}점)를 넘는 기사가 없습니다.")
    st.info(f"💡 전체 수집된 **총 {len(raw_news_pool)}개 기사**의 점수 분포를 확인하고 좌측 슬라이더를 조절해 보세요.")
    
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
    news_list = news_list[:st.session_state.settings.get("max_articles", 50)]
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
                cluster.append(item); added = True; break
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
    global_ratio = st.session_state.settings.get("top_picks_global_ratio", 70) / 100.0
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
                    buzz_badge = f"<span class='badge badge-buzz' title='커뮤니티 언급: {', '.join(item.get('buzz_words', []))}'>💬 긱(Geek) 화제</span>" if item.get('community_buzz') else ""
                    
                    html_content = (
                        '<div class="hero-img-box">'
                        f'<a href="{item.get("link", "#")}" target="_blank" style="display:block; width:100%; height:100%;">'
                        f'<img src="{img_src}" class="hero-bg" onerror="this.src=\'https://via.placeholder.com/800x600/1a1a1a/ffffff?text=MUST+KNOW\';">'
                        '<div class="hero-overlay"></div>'
                        '</a>'
                        '<div class="hero-content">'
                        f'<span class="badge badge-fire">{dup_badge}</span> '
                        f'<span class="badge badge-score">MATCH {item.get("score", 0)}%</span> '
                        f'{buzz_badge}'
                        f'<div class="hero-title">{item.get("insight_title", item.get("title_en", ""))}</div>'
                        '</div></div>'
                    )
                    st.markdown(html_content, unsafe_allow_html=True)
                    
                    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
                    act_c1, act_space, act_c2, act_c3 = st.columns([7.8, 2.0, 3.2, 3.5])
                    with act_c1:
                        st.markdown(f"""
                        <div style='display: flex; flex-direction: column; justify-content: center;'>
                            <a href='{item.get("link", "#")}' target='_blank' style='color:#1E293B; font-weight:800; font-size: 0.85rem; text-decoration:none; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.2;'>📰 {item.get("source", "Source")}</a>
                            <span style='font-size: 0.7rem; color: #64748B; margin-top: 3px;'>{item.get("date", "")}</span>
                        </div>
                        """, unsafe_allow_html=True)
                    with act_c2:
                        if st.button("공유", key=f"share_mk_{item['id']}_{i}", type="tertiary", use_container_width=True):
                            show_share_modal(item)
                    with act_c3:
                        if st.button("AI 분석", key=f"btn_mk_{item['id']}_{i}", type="secondary", use_container_width=True):
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
                    cat_badge = "<span class='badge badge-global'>🌐 Global</span>" if item['category'] == 'Global Innovation' else ("<span class='badge badge-china'>🇨🇳 China</span>" if item['category'] == 'China & East Asia' else f"<span class='badge' style='background:#7f8c8d;'>{item['category'][:6]}</span>")
                    buzz_badge = f"<span class='badge badge-buzz' title='커뮤니티 언급: {', '.join(item.get('buzz_words', []))}'>💬 커뮤니티 화제</span>" if item.get('community_buzz') else ""
                    
                    html_content = (
                        '<div class="hero-img-box">'
                        f'<a href="{item.get("link", "#")}" target="_blank" style="display:block; width:100%; height:100%;">'
                        f'<img src="{img_src}" class="hero-bg" onerror="this.src=\'https://via.placeholder.com/800x600/1a1a1a/ffffff?text=TOP+PICK\';">'
                        '<div class="hero-overlay"></div>'
                        '</a>'
                        '<div class="hero-content">'
                        f'{cat_badge} '
                        f'<span class="badge badge-score">MATCH {item.get("score", 0)}%</span> '
                        f'{buzz_badge}'
                        f'<div class="hero-title">{item.get("insight_title", item.get("title_en", ""))}</div>'
                        '</div></div>'
                    )
                    st.markdown(html_content, unsafe_allow_html=True)
                    
                    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
                    act_c1, act_space, act_c2, act_c3 = st.columns([7.8, 2.0, 3.2, 3.5])
                    with act_c1:
                        st.markdown(f"""
                        <div style='display: flex; flex-direction: column; justify-content: center;'>
                            <a href='{item.get("link", "#")}' target='_blank' style='color:#1E293B; font-weight:800; font-size: 0.85rem; text-decoration:none; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.2;'>📰 {item.get("source", "Source")}</a>
                            <span style='font-size: 0.7rem; color: #64748B; margin-top: 3px;'>{item.get("date", "")}</span>
                        </div>
                        """, unsafe_allow_html=True)
                    with act_c2:
                        if st.button("공유", key=f"share_tp_{item['id']}_{i}", type="tertiary", use_container_width=True):
                            show_share_modal(item)
                    with act_c3:
                        if st.button("AI 분석", key=f"btn_tp_{item['id']}_{i}", type="secondary", use_container_width=True):
                            show_analysis_modal(item, st.session_state.settings.get("api_key", "").strip(), GEMS_PERSONA, st.session_state.settings['ai_prompt'])

    # ==========================
    # 🌊 Section 3: Sensing Stream 
    # ==========================
    if stream_news:
        st.markdown("<br><div class='section-header'>🌊 Sensing Stream <span class='section-desc'>기타 관심 동향 타임라인</span></div>", unsafe_allow_html=True)
        
        filter_options = ["전체보기", "글로벌 혁신", "중국 동향", "일본/로보틱스", "커뮤니티 화제"]
        selected_filter = st.radio("필터", filter_options, horizontal=True, label_visibility="collapsed", key="stream_filter")
        st.markdown('<br>', unsafe_allow_html=True)
        
        filtered_stream = []
        for item in stream_news:
            if selected_filter == "전체보기":
                filtered_stream.append(item)
            elif selected_filter == "글로벌 혁신" and item.get('category') == 'Global Innovation':
                filtered_stream.append(item)
            elif selected_filter == "중국 동향" and item.get('category') == 'China & East Asia':
                filtered_stream.append(item)
            elif selected_filter == "일본/로보틱스" and item.get('category') == 'Japan & Robotics':
                filtered_stream.append(item)
            elif selected_filter == "커뮤니티 화제" and item.get('community_buzz'):
                filtered_stream.append(item)

        if not filtered_stream:
            st.info("해당 조건에 맞는 기사가 없습니다.")
        else:
            stream_cols = st.columns(3)
            for i, item in enumerate(filtered_stream):
                with stream_cols[i % 3]:
                    with st.container(border=True):
                        img_src = item.get('thumbnail') if item.get('thumbnail') else f"https://s.wordpress.com/mshots/v1/{item['link']}?w=600"
                        buzz_tag = "<span style='background:#f39c12; color:white; padding:2px 6px; border-radius:8px; font-size:0.65rem; font-weight:bold; margin-left:5px;'>💬 화제</span>" if item.get('community_buzz') else ""
                        
                        html_content = (
                            '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">'
                            '<div style="display:flex; align-items:center; gap:8px;">'
                            '<div style="width:24px; height:24px; background:#f0f2f5; border-radius:50%; display:flex; justify-content:center; align-items:center; font-size:12px;">📰</div>'
                            f'<a href="{item.get("link", "#")}" target="_blank" style="font-weight:800; font-size:0.95rem; color:#1E293B; text-decoration:none;">{item.get("source", "Source")}</a>'
                            '</div><div>'
                            f'<span style="background-color:#E3F2FD; color:#1565C0; padding:4px 8px; border-radius:12px; font-size:0.7rem; font-weight:700;">MATCH {item.get("score", 0)}%</span> '
                            f'{buzz_tag}'
                            '</div></div>'
                            f'<a href="{item.get("link", "#")}" target="_blank">'
                            f'<img src="{img_src}" style="width:100%; aspect-ratio:16/9; object-fit:cover; border-radius:8px; display:block; margin-bottom:12px;" onerror="this.src=\'https://via.placeholder.com/600x338?text=No+Image\';">'
                            f'</a>'
                            f'<div style="font-weight:700; font-size:1.05rem; line-height:1.4; color:#262626; margin-bottom:8px;">💡 {item.get("insight_title", item.get("title_en", ""))}</div>'
                            f'<div style="font-size:0.85rem; color:#444; line-height:1.5; margin-bottom:12px;">{item.get("core_summary", item.get("summary_ko", ""))}</div>'
                        )
                        st.markdown(html_content, unsafe_allow_html=True)
                        
                        st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
                        act_c1, act_space, act_c2, act_c3 = st.columns([7.8, 2.0, 3.2, 3.5])
                        with act_c1:
                            st.markdown(f"""
                            <div style='display: flex; flex-direction: column; justify-content: center;'>
                                <span style='font-size: 0.7rem; color: #64748B; margin-top: 3px;'>{item.get("date", "")}</span>
                            </div>
                            """, unsafe_allow_html=True)
                        with act_c2:
                            if st.button("공유", key=f"share_st_{item['id']}_{i}", type="tertiary", use_container_width=True):
                                show_share_modal(item)
                        with act_c3:
                            if st.button("AI 분석", key=f"btn_st_{item['id']}_{i}", type="secondary", use_container_width=True):
                                show_analysis_modal(item, st.session_state.settings.get("api_key", "").strip(), GEMS_PERSONA, st.session_state.settings['ai_prompt'])
