import feedparser
from google import genai
from bs4 import BeautifulSoup
import json
import os
import re
from datetime import datetime, timedelta
import time
from deep_translator import GoogleTranslator
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter

# 외부 프롬프트
from prompts import DEFAULT_FILTER_PROMPT

# 💡 추가됨: 팀장님의 선호 학습 규칙을 불러오는 함수
def load_prefs():
    pref_file = "learned_preferences.json"
    if os.path.exists(pref_file):
        try:
            with open(pref_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []

def run_morning_batch():
    print("🌅 [모닝 센싱] 자동화 봇 작동을 시작합니다...")
    
    # 1. GitHub Secrets 등 환경변수에서 API 키를 가져옵니다.
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("🚨 에러: GEMINI_API_KEY 환경변수가 없습니다.")
        return

    # 2. 채널 파일 읽기
    try:
        with open("channels.json", "r", encoding="utf-8") as f:
            channels_data = json.load(f)
    except Exception as e:
        print(f"🚨 에러: channels.json 파일을 읽을 수 없습니다. {e}")
        return

    # 최근 3일치 기사만 1차 수집
    limit = datetime.now() - timedelta(days=3)
    active_tasks = []
    for cat, feeds in channels_data.items():
        for f in feeds:
            if f.get("active", True):
                active_tasks.append((cat, f, limit))

    raw_news = []
    
    def fetch_worker(args):
        cat, f, lim = args
        articles = []
        try:
            d = feedparser.parse(f["url"])
            if not d.entries: return []
            for entry in d.entries[:15]:
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

    print(f"📡 {len(active_tasks)}개의 채널에서 기사 수집 중...")
    with ThreadPoolExecutor(max_workers=20) as executor:
        for f in as_completed([executor.submit(fetch_worker, t) for t in active_tasks]):
            raw_news.extend(f.result())
            
    # AI 할당량 관리를 위해 100개만 자르기
    raw_news = sorted(raw_news, key=lambda x: x['date_obj'], reverse=True)[:100]
    print(f"✅ 총 {len(raw_news)}개 기사 1차 확보 완료. AI 채점을 시작합니다.")

    # 💡💡💡 핵심 추가: 학습된 선호 기사 규칙 병합
    base_prompt = DEFAULT_FILTER_PROMPT
    learned_rules = load_prefs()
    if learned_rules:
        print(f"🧠 [RLHF] 팀장님이 지시한 {len(learned_rules)}개의 학습 규칙을 AI의 두뇌에 주입합니다.")
        rules_text = "\n".join([f"- {r}" for r in learned_rules])
        base_prompt += f"\n\n[🚨 최우선 가중치 (팀장님 선호 학습 규칙)]\n아래 규칙에 부합하는 기사는 반드시 높은 가산점(80점 이상)을 부여하여 핵심 이슈로 선정하세요:\n{rules_text}"
    else:
        print("ℹ️ 적용된 추가 학습 규칙이 없습니다. 기본 프롬프트로 진행합니다.")

    client = genai.Client(api_key=api_key)
    processed_items = []
    
    def ai_scoring_worker(item):
        try:
            import random
            time.sleep(random.uniform(0.5, 1.5)) # API 제한 회피
            
            # 💡 수정됨: DEFAULT_FILTER_PROMPT 대신 규칙이 병합된 base_prompt 사용
            score_query = f"{base_prompt}\n\n[평가 대상]\n매체: {item['source']}\n링크: {item['link']}\n제목: {item['title_en']}\n요약: {item['summary_en'][:200]}"
            response = client.models.generate_content(model="gemini-2.5-flash", contents=score_query)
            
            json_match = re.search(r'\{.*\}', response.text.strip(), re.DOTALL)
            if json_match:
                parsed_data = json.loads(json_match.group())
                url_lower = item['link'].lower()
                source_lower = item['source'].lower()
                community_domains = ['reddit', 'v2ex', 'hacker news', 'ycombinator', 'clien', 'dcinside', 'blind']
                
                if any(d in url_lower or d in source_lower for d in community_domains):
                    item['content_type'] = 'community'
                else:
                    item['content_type'] = parsed_data.get('content_type', 'news')
                
                item['score'] = int(parsed_data.get('score', 0)) if item['content_type'] == 'news' else 0
                item['insight_title'] = parsed_data.get('insight_title') or item['title_en']
                item['core_summary'] = parsed_data.get('core_summary') or item['summary_en'][:100]
                item['keywords'] = parsed_data.get('keywords', [])
            else: raise ValueError("No JSON")
        except:
            item['content_type'] = 'news'
            item['score'] = 50 
            item['insight_title'] = item['title_en']
            item['core_summary'] = item['summary_en'][:100]
            item['keywords'] = []
            
        # 영문 번역 (무료 번역기 한도 우회)
        try:
            item['insight_title'] = GoogleTranslator(source='auto', target='ko').translate(item['insight_title'])
            item['core_summary'] = GoogleTranslator(source='auto', target='ko').translate(item['core_summary'])
        except: pass
        
        return item

    with ThreadPoolExecutor(max_workers=5) as executor:
        for i, future in enumerate(as_completed({executor.submit(ai_scoring_worker, item): item for item in raw_news})):
            processed_items.append(future.result())
            print(f"🧠 분석 진행 중... ({i+1}/{len(raw_news)})")

    # 소셜 리스닝 버즈 반영
    community_keywords = []
    for item in processed_items:
        if item.get('content_type') == 'community':
            community_keywords.extend([str(k).upper() for k in item.get('keywords', [])])
            
    comm_kw_counts = Counter(community_keywords)
    hot_comm_keywords = set([k for k, v in comm_kw_counts.items() if v >= 1])

    final_pool = []
    for item in processed_items:
        if item.get('content_type') == 'news':
            news_kws = set([str(k).upper() for k in item.get('keywords', [])])
            overlap = news_kws.intersection(hot_comm_keywords)
            if overlap:
                item['score'] = min(100, item['score'] + (len(overlap) * 5))
                item['community_buzz'] = True
                item['buzz_words'] = list(overlap)
            else:
                item['community_buzz'] = False
            final_pool.append(item)

    final_pool = sorted(final_pool, key=lambda x: x.get('score', 0), reverse=True)
    
    # 3. 파일 저장 (today_news.json은 앱이 바로 읽을 용도, archive는 날짜별 기록 용도)
    today_str = datetime.now().strftime("%Y-%m-%d")
    archive_dir = "archive"
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir)
        
    try:
        with open("today_news.json", "w", encoding="utf-8") as f:
            json.dump(final_pool, f, ensure_ascii=False, indent=4)
        print("✅ today_news.json 저장 완료")
        
        with open(f"{archive_dir}/morning_sensing_{today_str}.json", "w", encoding="utf-8") as f:
            json.dump(final_pool, f, ensure_ascii=False, indent=4)
        print(f"✅ 아카이브 저장 완료: morning_sensing_{today_str}.json")
    except Exception as e:
        print(f"🚨 저장 실패: {e}")

if __name__ == "__main__":
    run_morning_batch()
