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

# 외부 프롬프트
from prompts import DEFAULT_FILTER_PROMPT

# 💡 Tier 1 주요 매체 리스트 (MUST KNOW 권위 판별용)
TIER1_SOURCES = ['techcrunch', 'verge', 'wired', 'bloomberg', 'cnbc', 'wsj', 'reuters', 'engadget', 'nikkei', 'gizmodo', 'the information']

def load_prefs():
    pref_file = "learned_preferences.json"
    if os.path.exists(pref_file):
        try:
            with open(pref_file, "r", encoding="utf-8") as f: return json.load(f)
        except: return []
    return []

def run_morning_batch():
    print("🌅 [NGEPT 모닝 센싱 V2] 파이프라인 가동 시작...")
    
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("🚨 에러: GEMINI_API_KEY가 없습니다.")
        return
    client = genai.Client(api_key=api_key)

    try:
        with open("channels.json", "r", encoding="utf-8") as f: channels_data = json.load(f)
    except Exception as e:
        print(f"🚨 에러: channels.json 읽기 실패 {e}")
        return

    limit = datetime.now() - timedelta(days=3)
    community_domains = ['reddit', 'v2ex', 'hacker news', 'ycombinator', 'clien', 'dcinside', 'blind']
    
    news_tasks = []
    comm_tasks = []
    
    for cat, feeds in channels_data.items():
        for f in feeds:
            if f.get("active", True):
                if any(d in f["url"].lower() for d in community_domains):
                    comm_tasks.append((cat, f, limit))
                else:
                    news_tasks.append((cat, f, limit))

    def fetch_worker(args):
        cat, f, lim = args
        articles = []
        try:
            d = feedparser.parse(f["url"])
            if not d.entries: return []
            # 💡 [해결 3] 최신 30개까지 긁어와 모수를 최대한 넓힙니다.
            for entry in d.entries[:30]:
                dt = entry.get('published_parsed') or entry.get('updated_parsed')
                if not dt: continue
                p_date = datetime.fromtimestamp(time.mktime(dt))
                if p_date < lim: continue
                
                thumbnail = ""
                if 'media_content' in entry and len(entry.media_content) > 0: thumbnail = entry.media_content[0].get('url', '')
                elif 'media_thumbnail' in entry and len(entry.media_thumbnail) > 0: thumbnail = entry.media_thumbnail[0].get('url', '')
                if not thumbnail:
                    html_content = str(entry.get('content', [{}])[0].get('value', '')) + str(entry.get('summary', ''))
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
        except: pass
        return articles

    # ==========================================
    # 📡 TRACK A: 커뮤니티 소셜 리스닝 (morning_buzz.json 생성)
    # ==========================================
    raw_comm = []
    print(f"📡 커뮤니티 데이터 수집 중... (채널 {len(comm_tasks)}개)")
    with ThreadPoolExecutor(max_workers=10) as executor:
        for f in as_completed([executor.submit(fetch_worker, t) for t in comm_tasks]):
            raw_comm.extend(f.result())
            
    print(f"💬 수집된 커뮤니티 글: {len(raw_comm)}개. AI 핫 키워드 추출 시작...")
    hot_buzz_keywords = []
    if raw_comm:
        # 최근 100개 글 제목을 뭉쳐서 AI에게 전달
        comm_titles = "\n".join([f"- {item['title_en']}" for item in raw_comm[:100]])
        buzz_prompt = f"당신은 IT 트렌드 분석가입니다. 아래는 오늘 새벽 글로벌 긱(Geek) 커뮤니티에 올라온 게시글 제목들입니다.\n이 중에서 가장 많이 언급되고 화제가 되는 특정 기업, 제품, 기술, 폼팩터 키워드 15개를 추출하여 JSON 리스트 형태로만 반환하세요.\n[게시글]\n{comm_titles}\n\n[출력 형식]\n{{\"keywords\": [\"Apple\", \"AR Glass\", ...]}}"
        try:
            res = client.models.generate_content(model="gemini-2.5-flash", contents=buzz_prompt, config=types.GenerateContentConfig(response_mime_type="application/json"))
            json_match = re.search(r'\{.*\}', res.text.strip(), re.DOTALL)
            if json_match:
                hot_buzz_keywords = json.loads(json_match.group()).get("keywords", [])
                hot_buzz_keywords = [k.upper() for k in hot_buzz_keywords]
        except Exception as e: print(f"버즈 추출 실패: {e}")

    # 💡 [해결 5] 수동 센싱에서도 쓸 수 있도록 Buzz 파일 별도 저장!
    try:
        with open("morning_buzz.json", "w", encoding="utf-8") as f:
            json.dump({"date": datetime.now().isoformat(), "keywords": hot_buzz_keywords}, f, ensure_ascii=False)
        print(f"🔥 morning_buzz.json 저장 완료 (핫 키워드: {len(hot_buzz_keywords)}개)")
    except Exception as e: print(f"버즈 저장 실패: {e}")

    # ==========================================
    # 📡 TRACK B: 뉴스 Pre-Filtering (초벌 채점)
    # ==========================================
    raw_news = []
    print(f"📡 공식 뉴스 데이터 수집 중... (채널 {len(news_tasks)}개)")
    with ThreadPoolExecutor(max_workers=20) as executor:
        for f in as_completed([executor.submit(fetch_worker, t) for t in news_tasks]):
            raw_news.extend(f.result())
            
    print(f"📰 수집된 전체 원본 기사: {len(raw_news)}개. (시간순 무식한 컷오프 폐지!)")
    
    # 💡 [해결 3&4] 시간순이 아닌 '제목 기반 Pre-filter' 적용 (단어 필터링으로 300개 압축 후 AI 분석)
    learned_rules = load_prefs()
    rule_str = ", ".join(learned_rules)
    
    # 1차 초스피드 로컬 텍스트 필터링 (가벼운 연관도 검사)
    target_keywords = ['ai', 'apple', 'meta', 'google', 'wearable', 'ring', 'glass', 'robot', 'ux', 'release', 'launch']
    target_keywords.extend([r.lower() for r in rule_str.split()])
    
    for n in raw_news:
        text_lower = (n['title_en'] + " " + n['summary_en']).lower()
        n['pre_score'] = sum(2 for k in target_keywords if k in text_lower)
        # 💡 [해결 6] Tier 1 매체에는 태생적으로 강력한 가점 부여
        if any(t in n['source'].lower() for t in TIER1_SOURCES):
            n['pre_score'] += 10 
            n['is_tier1'] = True
        else:
            n['is_tier1'] = False
            
    # 연관도 점수 기반으로 150개만 남기기 (여기서 영양가 없는 기사 대거 탈락)
    candidate_news = sorted(raw_news, key=lambda x: (x.get('pre_score', 0), x['date_obj']), reverse=True)[:150]
    print(f"✂️ 제목/매체 연관도 Pre-filter 통과 기사: {len(candidate_news)}개")

    # ==========================================
    # 🧠 TRACK C: 정예 150개 기사 Deep Scoring
    # ==========================================
    base_prompt = DEFAULT_FILTER_PROMPT
    if learned_rules:
        rules_text = "\n".join([f"- {r}" for r in learned_rules])
        base_prompt += f"\n\n[🚨 최우선 가중치 (팀장님 선호 학습 규칙)]\n아래 규칙에 부합하는 기사는 반드시 높은 가산점(80점 이상)을 부여하여 핵심 이슈로 선정하세요:\n{rules_text}"

    processed_items = []
    
    def ai_scoring_worker(item):
        try:
            import random
            time.sleep(random.uniform(0.5, 1.5))
            score_query = f"{base_prompt}\n\n[평가 대상]\n매체: {item['source']}\n링크: {item['link']}\n제목: {item['title_en']}\n요약: {item['summary_en'][:200]}"
            response = client.models.generate_content(model="gemini-2.5-flash", contents=score_query)
            
            json_match = re.search(r'\{.*\}', response.text.strip(), re.DOTALL)
            if json_match:
                parsed_data = json.loads(json_match.group())
                item['content_type'] = 'news'
                item['score'] = int(parsed_data.get('score', 0))
                item['insight_title'] = parsed_data.get('insight_title') or item['title_en']
                item['core_summary'] = parsed_data.get('core_summary') or item['summary_en'][:100]
                item['keywords'] = parsed_data.get('keywords', [])
                
                # 💡 [해결 6] Tier 1 매체 + 높은 점수면 'Headline' 등급 부여
                if item.get('is_tier1') and item['score'] >= 80:
                    item['score'] = min(100, item['score'] + 5) # 최종 부스팅
            else: raise ValueError("No JSON")
        except:
            item['content_type'] = 'news'
            item['score'] = 40 # 실패 시 기본 점수 하향
            item['insight_title'] = item['title_en']
            item['core_summary'] = item['summary_en'][:100]
            item['keywords'] = []
            
        try:
            item['insight_title'] = GoogleTranslator(source='auto', target='ko').translate(item['insight_title'])
            item['core_summary'] = GoogleTranslator(source='auto', target='ko').translate(item['core_summary'])
        except: pass
        return item

    print("🧠 정예 기사 150개 AI 심층 채점 시작...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        for i, future in enumerate(as_completed({executor.submit(ai_scoring_worker, item): item for item in candidate_news})):
            processed_items.append(future.result())

    # ==========================================
    # 🎯 TRACK D: 소셜 버즈 융합 & 퍼블리싱
    # ==========================================
    final_pool = []
    for item in processed_items:
        news_kws = set([str(k).upper() for k in item.get('keywords', [])])
        overlap = news_kws.intersection(set(hot_buzz_keywords))
        if overlap:
            item['score'] = min(100, item['score'] + (len(overlap) * 5))
            item['community_buzz'] = True
            item['buzz_words'] = list(overlap)
        else:
            item['community_buzz'] = False
        final_pool.append(item)

    final_pool = sorted(final_pool, key=lambda x: x.get('score', 0), reverse=True)
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    archive_dir = "archive"
    if not os.path.exists(archive_dir): os.makedirs(archive_dir)
        
    try:
        with open("today_news.json", "w", encoding="utf-8") as f:
            json.dump(final_pool, f, ensure_ascii=False, indent=4)
        with open(f"{archive_dir}/morning_sensing_{today_str}.json", "w", encoding="utf-8") as f:
            json.dump(final_pool, f, ensure_ascii=False, indent=4)
        print("✅ 모든 파이프라인 완료 및 데이터 저장 성공!")
    except Exception as e:
        print(f"🚨 저장 실패: {e}")

if __name__ == "__main__":
    run_morning_batch()
