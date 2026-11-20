import json
import os
import time
import uuid
import streamlit as st
from google import genai
from google.genai.errors import APIError

st.set_page_config(page_title="AI English Tutor", page_icon="🗣️", layout="centered")

CORRECT_PASSWORD = "1786"
SAVE_DIR = ".chat_history_cache"
os.makedirs(SAVE_DIR, exist_ok=True)


@st.cache_resource
def get_memory_store() -> dict:
    """앱이 살아있는 동안 세션별 대화 데이터를 메모리에 보관합니다."""
    return {}


def _file_path(chat_id: str) -> str:
    safe_id = "".join(c for c in chat_id if c.isalnum() or c in ("-", "_"))
    return os.path.join(SAVE_DIR, f"{safe_id}.json")


def load_saved_data(chat_id: str) -> dict:
    """메모리 또는 파일에서 저장된 시나리오와 대화 기록을 불러옵니다."""
    store = get_memory_store()
    if chat_id in store:
        return store[chat_id]

    path = _file_path(chat_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                store[chat_id] = data
                return data
        except Exception:
            pass

    default_data = {"scenario": "Free Conversation", "messages": []}
    store[chat_id] = default_data
    return default_data


def save_data(chat_id: str, scenario: str, messages: list) -> None:
    """대화 기록과 시나리오를 메모리와 JSON 파일에 저장합니다."""
    payload = {"scenario": scenario, "messages": messages}
    get_memory_store()[chat_id] = payload
    try:
        with open(_file_path(chat_id), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# 1. URL 쿼리 파라미터로 chat_id 유지 (새로고침해도 주소창에 남음)
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

# 3. API 키 로드 및 클라이언트 초기화
api_key = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))
if not api_key:
    st.error("⚠️ GEMINI_API_KEY가 Streamlit Secrets에 설정되지 않았습니다.")
    st.stop()

client = genai.Client(api_key=api_key)


def safe_generate(prompt_text: str) -> str:
    models_to_try = ["gemini-3.8-flash", "gemini-3.8-flash-lite"]
    for model_name in models_to_try:
        for _ in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt_text,
                )
                return response.text
            except APIError as e:
                if e.code == 503:
                    time.sleep(1.5)
                    continue
                raise e
    raise RuntimeError("현재 구글 AI 서버에 접속자가 많습니다. 잠시 후 다시 시도해주세요.")


# 4. 저장된 데이터로 세션 상태 복원
saved = load_saved_data(chat_id)
if "scenario" not in st.session_state:
    st.session_state.scenario = saved.get("scenario", "Free Conversation")
if "messages" not in st.session_state:
    st.session_state.messages = saved.get("messages", [])

# 5. 사이드바 설정
with st.sidebar:
    st.title("⚙️ Settings")
    scenarios = ["Free Conversation", "Ordering at a Cafe", "Job Interview", "Airport Immigration"]
    current_idx = scenarios.index(st.session_state.scenario) if st.session_state.scenario in scenarios else 0

    new_scenario = st.selectbox("Choose Scenario", scenarios, index=current_idx)
    if new_scenario != st.session_state.scenario:
        st.session_state.scenario = new_scenario
        st.session_state.messages = []
        save_data(chat_id, st.session_state.scenario, st.session_state.messages)
        st.rerun()

    if st.button("Clear Chat History"):
        st.session_state.messages = []
        save_data(chat_id, st.session_state.scenario, st.session_state.messages)
        st.rerun()

st.title("🗣️ AI English Conversation")
st.caption(f"Current Scenario: **{st.session_state.scenario}** · Session: `{chat_id}`")

# 6. 첫 인사 생성 및 저장
if len(st.session_state.messages) == 0:
    initial_prompt = (
        f"System: You are an English conversation tutor. Greet the user warmly in English "
        f"and start a roleplay based on the scenario: {st.session_state.scenario}."
    )
    try:
        ai_greeting = safe_generate(initial_prompt)
        st.session_state.messages.append({"role": "assistant", "content": ai_greeting})
        save_data(chat_id, st.session_state.scenario, st.session_state.messages)
    except Exception as e:
        st.error(f"API 연결 에러 발생: {e}")
        st.stop()

# 7. 기존 대화 출력
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 8. 새 메시지 입력 및 저장
if user_input := st.chat_input("Type your message in English..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    save_data(chat_id, st.session_state.scenario, st.session_state.messages)
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("AI is thinking..."):
            try:
                chat_history_str = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
                full_prompt = (
                    f"Scenario: {st.session_state.scenario}\n"
                    f"Conversation History:\n{chat_history_str}\n\n"
                    "Respond to the user naturally in English, correcting grammar if needed, and continue the conversation."
                )
                ai_response = safe_generate(full_prompt)
                st.markdown(ai_response)
                st.session_state.messages.append({"role": "assistant", "content": ai_response})
                save_data(chat_id, st.session_state.scenario, st.session_state.messages)
            except Exception as e:
                st.error(f"응답 생성 중 에러가 발생했습니다: {e}")
