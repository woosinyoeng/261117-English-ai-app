import asyncio
import io
import json
import os
import time
import uuid
import edge_tts
import streamlit as st
from google import genai
from google.genai import types
from google.genai.errors import APIError

st.set_page_config(page_title="AI English Tutor", page_icon="🗣️", layout="centered")

CORRECT_PASSWORD = "1786"
SAVE_DIR = ".chat_history_cache"
os.makedirs(SAVE_DIR, exist_ok=True)
TTS_VOICE = "en-US-JennyNeural"

SCENARIO_GREETINGS = {
    "Free Conversation": "Hi there! How is your day going so far? What would you like to talk about today?",
    "Ordering at a Cafe": "Welcome to Sunny Cafe! What can I get started for you today?",
    "Job Interview": "Hello! Thank you for coming in today. Could you start by telling me a little bit about yourself?",
    "Airport Immigration": "Good morning. May I see your passport and boarding pass, please? What is the purpose of your visit?",
}


@st.cache_resource
def get_memory_store() -> dict:
    return {}


def _file_path(chat_id: str) -> str:
    safe_id = "".join(c for c in chat_id if c.isalnum() or c in ("-", "_"))
    return os.path.join(SAVE_DIR, f"{safe_id}.json")


def load_saved_data(chat_id: str) -> dict:
    store = get_memory_store()
    if chat_id in store and store[chat_id].get("messages"):
        return {
            "scenario": store[chat_id].get("scenario", "Free Conversation"),
            "messages": list(store[chat_id].get("messages", [])),
        }

    path = _file_path(chat_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                store[chat_id] = data
                return {
                    "scenario": data.get("scenario", "Free Conversation"),
                    "messages": list(data.get("messages", [])),
                }
        except Exception:
            pass

    if chat_id in store:
        return {
            "scenario": store[chat_id].get("scenario", "Free Conversation"),
            "messages": list(store[chat_id].get("messages", [])),
        }

    return {"scenario": "Free Conversation", "messages": []}


def save_data(chat_id: str, scenario: str, messages: list) -> None:
    payload = {"scenario": scenario, "messages": list(messages)}
    get_memory_store()[chat_id] = payload
    try:
        with open(_file_path(chat_id), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def text_to_speech_bytes(text: str, voice: str = TTS_VOICE) -> bytes | None:
    lines = [line for line in text.splitlines() if not line.strip().startswith("🎧")]
    clean_text = " ".join(lines).replace("*", "").replace("#", "").strip()
    if not clean_text:
        return None

    async def _synthesize() -> bytes:
        buf = io.BytesIO()
        communicate = edge_tts.Communicate(clean_text, voice)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        return buf.getvalue()

    try:
        return asyncio.run(_synthesize())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_synthesize())
        finally:
            loop.close()
    except Exception:
        return None


# 1. URL 쿼리 파라미터로 chat_id 유지
if "chat_id" not in st.query_params or not st.query_params["chat_id"]:
    st.query_params["chat_id"] = str(uuid.uuid4())[:8]
chat_id = str(st.query_params["chat_id"])

# 2. 비밀번호 인증
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

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

# 3. API 키 및 클라이언트
api_key = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))
if not api_key:
    st.error("⚠️ GEMINI_API_KEY가 Streamlit Secrets에 설정되지 않았습니다.")
    st.stop()

client = genai.Client(api_key=api_key)


def safe_generate(contents_payload) -> str:
    models_to_try = ["gemini-3.8-flash"]
    last_error = None

    for model_name in models_to_try:
        for attempt in range(4):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents_payload,
                )
                return response.text or ""
            except APIError as e:
                last_error = e
                if e.code == 404:
                    break
                if e.code in (429, 503):
                    time.sleep(2 * (attempt + 1))
                    continue
                raise e

    raise RuntimeError(f"구글 AI 서버가 바빠 응답이 지연되고 있습니다. 잠시 후 다시 시도해 주세요. ({last_error})")


# 4. 저장된 데이터 복원 및 상태 초기화
if "loaded_chat_id" not in st.session_state or st.session_state.loaded_chat_id != chat_id:
    saved = load_saved_data(chat_id)
    st.session_state.loaded_chat_id = chat_id
    st.session_state.scenario = saved.get("scenario", "Free Conversation")
    st.session_state.messages = saved.get("messages", [])

if "mic_key" not in st.session_state:
    st.session_state.mic_key = 0
if "pending_audio" not in st.session_state:
    st.session_state.pending_audio = None

# 5. 사이드바 설정
with st.sidebar:
    st.title("⚙️ Settings")
    scenarios = list(SCENARIO_GREETINGS.keys())
    current_idx = scenarios.index(st.session_state.scenario) if st.session_state.scenario in scenarios else 0

    new_scenario = st.selectbox("Choose Scenario", scenarios, index=current_idx)
    if new_scenario != st.session_state.scenario:
        st.session_state.scenario = new_scenario
        st.session_state.messages = []
        st.session_state.pending_audio = None
        st.session_state.mic_key += 1
        save_data(chat_id, st.session_state.scenario, st.session_state.messages)
        st.rerun()

    auto_tts = st.toggle("AI 답변 자동 음성 재생 (edge-tts)", value=True)
    voice_choice = st.selectbox(
        "Tutor Voice",
        ["en-US-JennyNeural", "en-US-GuyNeural", "en-GB-SoniaNeural"],
        index=0,
    )

    st.caption(f"저장된 메시지 수: {len(st.session_state.messages)}개 · ID: `{chat_id}`")

    if st.button("Clear Chat History"):
        st.session_state.messages = []
        st.session_state.pending_audio = None
        st.session_state.mic_key += 1
        save_data(chat_id, st.session_state.scenario, st.session_state.messages)
        st.rerun()

st.title("🗣️ AI English Conversation")
st.caption(f"Current Scenario: **{st.session_state.scenario}** · Session: `{chat_id}`")

# 6. 첫 인사
if len(st.session_state.messages) == 0:
    greeting = SCENARIO_GREETINGS.get(st.session_state.scenario, SCENARIO_GREETINGS["Free Conversation"])
    st.session_state.messages.append({"role": "assistant", "content": greeting})
    save_data(chat_id, st.session_state.scenario, st.session_state.messages)

# 7. 기존 대화 출력
for idx, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant" and st.button("🔊 듣기", key=f"tts_{idx}"):
            mp3_data = text_to_speech_bytes(message["content"], voice_choice)
            if mp3_data:
                st.audio(mp3_data, format="audio/mp3", autoplay=True)

# 8. 보류 중인 음성 입력이 있으면 먼저 처리
user_display_text = None
audio_part = None

if st.session_state.pending_audio is not None:
    audio_raw, audio_mime = st.session_state.pending_audio
    st.session_state.pending_audio = None
    user_display_text = "🎙️ (Voice message)"
    audio_part = types.Part.from_bytes(data=audio_raw, mime_type=audio_mime)
else:
    mic_audio = st.audio_input("🎙️ 영어로 말해보세요", key=f"mic_{st.session_state.mic_key}")
    text_input = st.chat_input("또는 영어로 메시지를 입력하세요...")

    if mic_audio is not None:
        st.session_state.pending_audio = (mic_audio.getvalue(), mic_audio.type or "audio/wav")
        st.session_state.mic_key += 1
        st.rerun()
    elif text_input:
        user_display_text = text_input

if user_display_text is not None:
    st.session_state.messages.append({"role": "user", "content": user_display_text})
    save_data(chat_id, st.session_state.scenario, st.session_state.messages)

    with st.chat_message("user"):
        st.markdown(user_display_text)

    history_lines = []
    for m in st.session_state.messages[:-1]:
        role_label = "Tutor" if m["role"] == "assistant" else "User"
        history_lines.append(f"{role_label}: {m['content']}")
    history_text = "\n".join(history_lines)

    if audio_part is not None:
        prompt_instruction = (
            f"You are an English conversation tutor in the scenario: '{st.session_state.scenario}'.\n"
            f"Previous conversation:\n{history_text}\n\n"
            "The user just replied via voice audio (attached).\n"
            "1. Start your response with a single line: '🎧 **You said:** \"<transcribe what the user said>\"'\n"
            "2. Then reply naturally in English to move the conversation forward (do NOT repeat your previous question), "
            "and briefly give 1 gentle grammar/expression tip if needed."
        )
        gemini_contents = [prompt_instruction, audio_part]
    else:
        prompt_instruction = (
            f"You are an English conversation tutor in the scenario: '{st.session_state.scenario}'.\n"
            f"Previous conversation:\n{history_text}\n\n"
            f"User's latest message: \"{user_display_text}\"\n\n"
            "Reply naturally in English to move the conversation forward based on what the user just said "
            "(do NOT repeat your previous question), and briefly give 1 gentle grammar/expression tip if needed."
        )
        gemini_contents = prompt_instruction

    with st.chat_message("assistant"):
        with st.spinner("AI is thinking..."):
            try:
                ai_response = safe_generate(gemini_contents)
                st.markdown(ai_response)
                st.session_state.messages.append({"role": "assistant", "content": ai_response})
                save_data(chat_id, st.session_state.scenario, st.session_state.messages)

                if auto_tts:
                    mp3_data = text_to_speech_bytes(ai_response, voice_choice)
                    if mp3_data:
                        st.audio(mp3_data, format="audio/mp3", autoplay=True)
            except Exception as e:
                st.error(f"응답 생성 중 에러가 발생했습니다: {e}")
