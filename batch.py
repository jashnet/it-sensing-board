import feedparser
from google import genai
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

# 👇 새롭게 추가된 마법의 1줄! (여기엔 필터 프롬프트만 필요합니다)
from prompts import DEFAULT_FILTER_PROMPT

# 💡 GitHub Secrets에서 API 키를 가져옵니다.
API_KEY = os.environ.get("GEMINI_API_KEY")

# ==========================================
# ❌ [기존 코드 삭제] 아래에 있던 길고 긴 
# DEFAULT_FILTER_PROMPT 텍스트 덩어리를 
# 전부 통째로 지워주세요! 
# ==========================================

def safe_translate(text):
    if not text: return ""
    try: return GoogleTranslator(source='auto', target='ko').translate(text)
    except: return text

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
                "category": cat, "date_obj": p_date.isoformat(), # JSON 저장을 위해 문자열 변환
                "date": p_date.strftime("%Y.%m.%d"),
                "summary_en": BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:300],
                "thumbnail": thumbnail
            })
    except: pass
    return articles

def run_batch_sensing():
    print("🚀 배치 센싱 작업을 시작합니다...")
    if not API_KEY:
        print("❌ API 키가 없습니다. 작업을 중단합니다.")
        return

    # 채널 로드
    try:
        with open("channels.json", "r", encoding="utf-8") as f:
            channels_data = json.load(f)
    except:
        print("❌ channels.json 파일을 찾을 수 없습니다.")
        return

    # 설정값 (고정)
    sensing_period = 3
    max_articles = 60
    filter_weight = 70
    limit = datetime.now() - timedelta(days=sensing_period)

    active_tasks = []
    for cat, feeds in channels_data.items():
        for f in feeds:
            if f.get("active", True):
                active_tasks.append((cat, f, limit))

    raw_news = []
    print(f"📡 {len(active_tasks)}개 채널에서 뉴스를 수집합니다...")
    with ThreadPoolExecutor(max_workers=40) as executor:
        futures = [executor.submit(fetch_raw_news, t) for t in active_tasks]
        for f in as_completed(futures): raw_news.extend(f.result())

    raw_news = sorted(raw_news, key=lambda x: x['date_obj'], reverse=True)[:max_articles]
    
    client = genai.Client(api_key=API_KEY)
    filtered_list = []

    def ai_scoring_worker(item):
        try:
            score_query = f"{DEFAULT_FILTER_PROMPT}\n\n[평가 대상]\n제목: {item['title_en']}\n요약: {item['summary_en'][:200]}"
            response = client.models.generate_content(model="gemini-2.5-flash", contents=score_query)
            res = response.text.strip()
            if res.startswith("```json"): res = res[7:-3].strip()
            elif res.startswith("```"): res = res[3:-3].strip()
            
            parsed_data = json.loads(res)
            item['score'] = int(parsed_data.get('score', 50))
            item['insight_title'] = parsed_data.get('insight_title') or safe_translate(item['title_en'])
            item['core_summary'] = parsed_data.get('core_summary') or safe_translate(item['summary_en'])
        except Exception:
            item['score'] = 50 
            item['insight_title'] = safe_translate(item['title_en'])
            item['core_summary'] = safe_translate(item['summary_en'])
        return item

    print(f"🧠 {len(raw_news)}개 기사에 대해 AI 필터링을 시작합니다...")
    with ThreadPoolExecutor(max_workers=30) as executor:
        future_to_item = {executor.submit(ai_scoring_worker, item): item for item in raw_news}
        for future in as_completed(future_to_item):
            item = future.result()
            if item['score'] >= filter_weight:
                filtered_list.append(item)

    final_news = sorted(filtered_list, key=lambda x: x.get('score', 0), reverse=True)
    
    # 💾 결과물을 JSON 파일로 저장합니다.
    with open("today_news.json", "w", encoding="utf-8") as f:
        json.dump(final_news, f, ensure_ascii=False, indent=4)
        
    print(f"✅ 배치 작업 완료! 총 {len(final_news)}개의 기사가 today_news.json에 저장되었습니다.")

if __name__ == "__main__":
    run_batch_sensing()
