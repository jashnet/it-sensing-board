import streamlit as st
import feedparser
import google.generativeai as genai
from datetime import datetime

# 1. 화면 설정
st.set_page_config(page_title="NOD IT Sensing Dashboard", layout="wide")

# 2. AI 설정 (Gemini API 연결)
# 사용자가 나중에 설정 화면에서 키를 입력하도록 만듭니다.
api_key = st.sidebar.text_input("Gemini API Key를 입력하세요", type="password")

if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')

# 3. 사이드바 - 센싱 타겟 설정
st.sidebar.title("🔍 Sensing Control")
target_source = st.sidebar.selectbox("센싱 채널 선택", ["Product Hunt (Global)", "36Kr (China Tech)", "The Verge (Tech News)"])

rss_urls = {
    "Product Hunt (Global)": "https://www.producthunt.com/feed",
    "36Kr (China Tech)": "https://36kr.com/feed",
    "The Verge (Tech News)": "https://www.theverge.com/rss/index.xml"
}

# 4. 메인 화면 UI
st.title("🚀 NOD 프로젝트: 글로벌 IT 센싱 대시보드")
st.write(f"현재 데이터 소스: **{target_source}** (업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M')})")

# 5. 데이터 가져오기 및 AI 분석
feed = feedparser.parse(rss_urls[target_source])

if not feed.entries:
    st.error("데이터를 가져오지 못했습니다. 뉴스 피드 URL을 확인해주세요.")
else:
    for entry in feed.entries[:5]: # 최신 뉴스 5개만 먼저 봅니다.
        with st.container():
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.subheader(entry.title)
                st.write(f"원문 링크: [바로가기]({entry.link})")
                st.caption(f"발행일: {entry.published if 'published' in entry else 'N/A'}")
            
            with col2:
                if st.button(f"AI 전략 분석 수행", key=entry.link):
                    if not api_key:
                        st.warning("먼저 왼쪽 사이드바에 API Key를 입력해주세요.")
                    else:
                        with st.spinner("AI가 분석 중입니다..."):
                            # AI에게 던지는 질문(프롬프트)
                            prompt = f"""
                            너는 우리 회사의 '차세대 경험 기획팀'의 전략가야. 
                            아래 IT 뉴스 내용을 읽고 분석해줘.
                            내용: {entry.title} - {entry.description}
                            
                            분석 형식:
                            1. 핵심 요약 (한 줄)
                            2. 이 제품/서비스의 신기한 점
                            3. 우리 회사가 벤치마킹하거나 적용해볼 수 있는 아이디어 2가지
                            """
                            response = model.generate_content(prompt)
                            st.success("✅ 분석 완료")
                            st.markdown(response.text)
            st.divider()
