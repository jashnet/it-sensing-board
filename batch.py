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

# 💡 GitHub Secrets에서 API 키를 가져옵니다.
API_KEY = os.environ.get("GEMINI_API_KEY")

DEFAULT_FILTER_PROMPT = """귀하는 삼성전자 차세대경험기획팀의 뉴스 필터링 AI 에이전트입니다.
주어진 뉴스의 제목과 요약을 보고, 2~3년 뒤 출시할 '소비자 중심의 차세대 스마트 디바이스 및 UX 기획'에 얼마나 중요한 시그널인지 0~100점으로 평가하세요.

[우선순위 가중치 규칙]
- +가중치: 제품/디바이스 또는 명확한 앱/서비스 중심내용, AI 기술이 결합된 경험 변화, 생태계 전반을 흔드는 파급력, 주요 빅테크(Apple, MS, Meta, Google, OpenAI 등)의 핵심 동향, 미국에 도전하는 중국의 극단적 하드웨어/AI 변형 시도.
- -감점/배제: 단순 실적/재무 발표, 정책/법률/특허 소송, 기업 인사 동정, 광고성 이벤트, 순수 B2B/산업용 기술, 단순 데이터 관련 정보
- 조건부 허용: 자동차, 이동수단, 스마트홈 등은 그 자체로는 점수가 낮으나, '스마트 디바이스(폰, 웨어러블)와의 연동을 통한 새로운 UX 창출' 내용이라면 높은 점수를 부여함.

[출력 형식 - 반드시 아래 JSON 형식으로만 출력할 것]
{
    "score": [0~100 사이의 정수],
    "insight_title": "[원문 번역이 아닌, 차세대경험기획팀 기획자 관점에서 바라본 의미 해석을 담은 매력적인 1줄 인사이트 제목(한국어)]",
    "core_summary": "[실제 기사 내용이 무엇인지 팩트 위주로 파악할 수 있는 2~3줄 요약(한국어)]"
}
"""

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
