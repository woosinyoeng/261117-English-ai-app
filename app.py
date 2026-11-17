import asyncio
import os
import tempfile
import streamlit as st
from google import genai
import edge_tts

# 페이지 설정
st.set_page_config(
    page_title="SINYOM AI 영어 회화 스튜디오",
    page_icon="🌸",
    layout="centered",
    initial_sidebar_state="expanded"
)

# 🔒 [보안 기능] 비밀번호 인증 함수
def check_password():
    # 💡 원하는 비밀번호로 변경하세요! (예: "mysecret1234")
    CORRECT_PASSWORD = "1786"

    def password_entered():
        if st.session_state["password"] == CORRECT_PASSWORD:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # 세션에서 비밀번호 문자열 삭제
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # 첫 접속 시 비밀번호 입력 화면 출력
        st.markdown("<h2 style='text-align: center; color: #d88395;'>🔒 프라이빗 영어 회화 스튜디오</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #666;'>접속하려면 비밀번호를 입력하세요.</p>", unsafe_allow_html=True)
        st.text_input("비밀번호", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.markdown("<h2 style='text-align: center; color: #d88395;'>🔒 프라이빗 영어 회화 스튜디오</h2>", unsafe_allow_html=True)
        st.text_input("비밀번호", type="password", on_change=password_entered, key="password")
        st.error("😕 비밀번호가 일치하지 않습니다. 다시 입력해주세요.")
        return False
    else:
        return True

# 비밀번호가 틀렸다면 여기서 앱 실행을 멈춤
if not check_password():
    st.stop()


# ==========================================
# 여기부터는 인증된 사용자만 볼 수 있는 메인 앱 영역입니다
# ==========================================

# 커스텀 파스텔 디자인 및 UI CSS 적용
st.markdown("""
    <style>
    /* 전체 배경 및 폰트 감성 */
    .stApp {
        background: linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%);
    }
    
    /* 메인 타이틀 스타일 */
    .main-title {
        text-align: center;
        color: #d88395;
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 0px;
        letter-spacing: -0.5px;
    }
    .sub-title {
        text-align: center;
        color: #7f8c8d;
        font-size: 0.95rem;
        margin-bottom: 1.5rem;
    }
    
    /* 대화 버블 스타일 */
    .chat-bubble {
        padding: 1rem 1.2rem;
        border-radius: 1.2rem;
        margin-bottom: 1rem;
        line-height: 1.6;
        font-size: 0.95rem;
        box-shadow: 0 4px 15px rgba(0,0,0,0.03);
    }
    .user-bubble {
        background-color: #d0caec;
        color: #2c3e50;
        border-top-right-radius: 0.3rem;
    }
    .ai-bubble {
        background-color: #ffffff;
        color: #2c3e50;
        border: 1px solid #f0f0f0;
        border-top-left-radius: 0.3rem;
    }
    
    /* 피드백 노트 카드 스타일 */
    .feedback-card {
        background: #fff9fb;
        border-left: 4px solid #d88395;
        padding: 12px 16px;
        border-radius: 0.5rem;
        margin-bottom: 10px;
        font-size: 0.9rem;
        color: #4a4a4a;
        box-shadow: 0 2px 8px rgba(216, 131, 149, 0.08);
    }
    
    /* 사이드바 스타일링 */
    [data-testid="stSidebar"] {
        background-color: #f7f6fc;
        border-right: 1px solid #e8e4f5;
    }
    </style>
""", unsafe_allow_html=True)

# 1. 사이드바 설정 (API 키 및 설정)
with st.sidebar:
    st.markdown("### ⚙️ 설정 & 페르소나")
    api_key_input = st.text_input("Gemini API Key", type="password", help="Google AI Studio API 키를 입력하세요.")
    
    selected_voice = st.selectbox(
        "원어민 음성 선택",
        ["en-US-AriaNeural (미국 여성)", "en-US-ChristopherNeural (미국 남성)", "en-GB-SoniaNeural (영국 여성)"],
        index=0
    )
    voice_code = selected_voice.split(" ")[0]
    
    st.markdown("---")
    st.markdown("💡 **Tip**: 스마트폰 브라우저에서 마이크 버튼을 눌러 바로 음성 대화를 즐겨보세요!")

if api_key_input:
    os.environ["GEMINI_API_KEY"] = api_key_input

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    st.warning("⚠️ 사이드바에 Gemini API Key를 입력해주세요.")
    st.stop()

client = genai.Client(api_key=api_key)

# 2. 세션 상태 초기화 (시나리오, 대화 기록, 피드백 노트)
if "scenario" not in st.session_state:
    st.session_state.scenario = "자유 대화 (Free Talking)"

if "messages" not in st.session_state:
    st.session_state.messages = []

if "feedbacks" not in st.session_state:
    st.session_state.feedbacks = []

if "chat_session" not in st.session_state:
    st.session_state.chat_session = None

# 시나리오 정의
SCENARIOS = {
    "자유 대화 (Free Talking)": "You are a friendly and encouraging English conversation tutor. Chat naturally with the user.",
    "☕ 카페 주문하기 (Cafe Ordering)": "You are a friendly barista at a cozy café. The user is a customer ordering drinks and food. Roleplay naturally.",
    "✈️ 공항 입국 심사 (Airport Immigration)": "You are a strict but polite airport immigration officer. Ask the user questions like purpose of visit, duration of stay, etc.",
    "🏨 호텔 체크인 (Hotel Check-in)": "You are a hotel front desk receptionist. Help the user check into their room and answer their questions.",
    "💼 비즈니스 미팅 (Business Meeting)": "You are a professional business partner discussing a new marketing project with the user."
}

# 시나리오 변경 감지 함수
def init_chat_session(scenario_name):
    st.session_state.scenario = scenario_name
    prompt = SCENARIOS[scenario_name]
    system_instruction = f"""
    {prompt}
    Always follow these two rules in your reply:
    1. Keep sentences natural, friendly, and appropriate for the context.
    2. If the user makes grammatical or awkward phrasing mistakes, append a tiny, gentle correction note at the very end of your response using this exact format: [CORRECTION: "틀린 표현" -> "올바른 표현" (간단한 이유)]. If there are no mistakes, omit this tag.
    """
    st.session_state.chat_session = client.chats.create(model="gemini-2.5-flash")
    initial_res = st.session_state.chat_session.send_message(f"System: Start the conversation based on your role. Greet the user warmly in English. (Scenario: {scenario_name})")
    
    st.session_state.messages = [
        {"role": "assistant", "content": initial_res.text}
    ]
    st.session_state.feedbacks = []

if st.session_state.chat_session is None:
    init_chat_session(st.session_state.scenario)

# 헤더 UI
st.markdown("<h1 class='main-title'>🌸 AI 영어 회화 스튜디오</h1>", unsafe_allow_html=True)
st.markdown("<p class='sub-title'>상황별 시나리오로 실전 감각을 익히고 피드백 노트로 실력을 키워보세요.</p>", unsafe_allow_html=True)

# 3. 메인 화면 탭 구성 (대화하기 vs 피드백 노트)
tab_chat, tab_feedback = st.tabs(["💬 회화 대화방", "📝 내 피드백 노트"])

with tab_chat:
    selected_scenario = st.selectbox(
        "🎯 학습 시나리오 선택",
        list(SCENARIOS.keys()),
        index=list(SCENARIOS.keys()).index(st.session_state.scenario)
    )
    
    if selected_scenario != st.session_state.scenario:
        init_chat_session(selected_scenario)
        st.rerun()

    st.markdown("---")

    for message in st.session_state.messages:
        if message["role"] == "user":
            with st.chat_message("user", avatar="👤"):
                st.markdown(f"<div class='chat-bubble user-bubble'>{message['content']}</div>", unsafe_allow_html=True)
        else:
            with st.chat_message("assistant", avatar="🤖"):
                raw_text = message['content']
                if "[CORRECTION:" in raw_text:
                    parts = raw_text.split("[CORRECTION:")
                    main_text = parts[0].strip()
                    correction_part = "[CORRECTION:" + parts[1].strip()
                else:
                    main_text = raw_text
                    correction_part = None

                st.markdown(f"<div class='chat-bubble ai-bubble'>{main_text}</div>", unsafe_allow_html=True)
                
                if correction_part:
                    st.markdown(f"<div style='font-size: 0.85rem; color: #d88395; margin-bottom: 8px;'>✨ 교정 팁: {correction_part.replace('[CORRECTION:', '').replace(']', '')}</div>", unsafe_allow_html=True)

                if "audio_path" in message and os.path.exists(message["audio_path"]):
                    st.audio(message["audio_path"], format="audio/mp3")

    input_tab1, input_tab2 = st.tabs(["🎙️ 마이크 음성 입력", "⌨️ 텍스트 입력"])

    user_input = None

    async def generate_tts(text, voice, output_path):
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)

    with input_tab1:
        st.caption("🎙️ 마이크 버튼을 눌러 영어로 말해보세요. (모바일/PC 지원)")
        audio_bytes = st.audio_input("음성 녹음")
        
        if audio_bytes:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
                temp_audio.write(audio_bytes.getvalue())
                temp_audio_path = temp_audio.name
            
            with st.spinner("🎧 음성을 분석하고 답변을 준비 중입니다..."):
                try:
                    audio_file_ref = client.files.upload(file=temp_audio_path)
                    response = st.session_state.chat_session.send_message(
                        [
                            audio_file_ref, 
                            "Listen to the user's spoken audio above. Reply naturally in English according to your persona and include correction tags if needed."
                        ]
                    )
                    client.files.delete(name=audio_file_ref.name)
                    os.unlink(temp_audio_path)
                    
                    user_input = "[Voice Message Recorded]"
                    ai_reply = response.text
                except Exception as e:
                    st.error(f"오류가 발생했습니다: {e}")
                    ai_reply = "I'm sorry, could you say that again?"

    with input_tab2:
        text_input_val = st.text_input("메시지 입력 (English):", placeholder="Type your message...", key="chat_input_box")
        if st.button("전송하기", type="primary"):
            if text_input_val:
                with st.spinner("💭 생각 중..."):
                    response = st.session_state.chat_session.send_message(text_input_val)
                    user_input = text_input_val
                    ai_reply = response.text

    if user_input:
        if user_input != "[Voice Message Recorded]":
            st.session_state.messages.append({"role": "user", "content": user_input})
        else:
            st.session_state.messages.append({"role": "user", "content": "🎙️ (음성 메시지 전송됨)"})

        clean_ai_reply = ai_reply
        if "[CORRECTION:" in ai_reply:
            try:
                parts = ai_reply.split("[CORRECTION:")
                clean_ai_reply = parts[0].strip()
                feedback_item = parts[1].replace("]", "").strip()
                if feedback_item not in st.session_state.feedbacks:
                    st.session_state.feedbacks.append(feedback_item)
            except Exception:
                pass

        temp_tts_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        temp_tts_path = temp_tts_file.name
        temp_tts_file.close()

        asyncio.run(generate_tts(clean_ai_reply, voice_code, temp_tts_path))

        st.session_state.messages.append({
            "role": "assistant", 
            "content": ai_reply,
            "audio_path": temp_tts_path
        })
        
        st.rerun()

with tab_feedback:
    st.markdown("### 📝 나의 문법 교정 및 표현 피드백 노트")
    st.caption("대화 중에 AI가 교정해 준 표현들이 자동으로 이곳에 기록됩니다. 복습용으로 활용해보세요!")
    
    if not st.session_state.feedbacks:
        st.info("💡 아직 기록된 피드백이 없습니다. 대화를 나누며 영어 회화 실력을 높여보세요!")
    else:
        for idx, fb in enumerate(st.session_state.feedbacks, 1):
            st.markdown(f"""
                <div class='feedback-card'>
                    <b>#{idx}</b> &nbsp; {fb}
                </div>
            """, unsafe_allow_html=True)
            
        if st.button("🧹 피드백 노트 비우기"):
            st.session_state.feedbacks = []
            st.rerun()