import os
import streamlit as st
from google import genai
import edge_tts
import asyncio
from PIL import Image
import io

# 페이지 설정
st.set_page_config(page_title="AI English Tutor", page_icon="🗣️", layout="centered")

# 비밀번호 설정 (원하시는 비밀번호로 변경하세요)
CORRECT_PASSWORD = "1786"

# 세션 상태 초기화
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "messages" not in st.session_state:
    st.session_state.messages = []
if "scenario" not in st.session_state:
    st.session_state.scenario = "Free Conversation"

# 1. 비밀번호 인증 화면
if not st.session_state.authenticated:
    st.markdown("## 🔐 AI English Tutor Login")
    password_input = st.text_input("Access Password", type="password")
    if st.button("Login"):
        if password_input == CORRECT_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("❌ Incorrect password.")
    st.stop()

# 2. API 키 설정 (Streamlit Secrets 우선 참조)
api_key = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))

if not api_key:
    st.error("⚠️ GEMINI_API_KEY가 Streamlit Secrets에 설정되지 않았습니다.")
    st.stop()

# GenAI 클라이언트 초기화
client = genai.Client(api_key=api_key)

# 사이드바 설정
with st.sidebar:
    st.title("⚙️ Settings")
    new_scenario = st.selectbox(
        "Choose Scenario",
        ["Free Conversation", "Ordering at a Cafe", "Job Interview", "Airport Immigration"]
    )
    
    if new_scenario != st.session_state.scenario:
        st.session_state.scenario = new_scenario
        st.session_state.messages = [] # 시나리오 변경 시 대화 초기화
        st.rerun()
        
    if st.button("Clear Chat History"):
        st.session_state.messages = []
        st.rerun()

st.title("🗣️ AI English Conversation")
st.caption(f"Current Scenario: **{st.session_state.scenario}**")

# 최초 접속 시 혹은 대화가 없을 때 AI의 첫 인사 생성
if len(st.session_state.messages) == 0:
    initial_prompt = f"System: You are an English conversation tutor. Greet the user warmly in English and start a roleplay based on the scenario: {st.session_state.scenario}."
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=initial_prompt
        )
        ai_greeting = response.text
        st.session_state.messages.append({"role": "assistant", "content": ai_greeting})
    except Exception as e:
        st.error(f"API 연결 에러 발생: {e}")
        st.stop()

# 대화 기록 출력
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 사용자 입력 처리
if user_input := st.chat_input("Type your message in English..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # AI 응답 생성 (안전한 단건 호출 방식)
    with st.chat_message("assistant"):
        with st.spinner("AI is thinking..."):
            try:
                # 대화 맥락을 포함하여 요청
                chat_history_str = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
                full_prompt = f"Scenario: {st.session_state.scenario}\nConversation History:\n{chat_history_str}\n\nRespond to the user naturally in English, correcting grammar if needed, and continue the conversation."
                
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=full_prompt
                )
                ai_response = response.text
                st.markdown(ai_response)
                st.session_state.messages.append({"role": "assistant", "content": ai_response})
            except Exception as e:
                st.error(f"응답 생성 중 에러가 발생했습니다: {e}")
