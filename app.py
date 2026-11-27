import asyncio
import hashlib
import hmac
import html
import io
import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import edge_tts
import streamlit as st
from google import genai
from google.genai import types
from google.genai.errors import APIError

st.set_page_config(page_title="AI English Tutor", page_icon="🌸", layout="centered")

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
SAVE_DIR = ".chat_history_cache"
os.makedirs(SAVE_DIR, exist_ok=True)

TTS_VOICE = "en-US-JennyNeural"
MAX_HISTORY_MESSAGES = 6

# 앞에서부터 순서대로 시도합니다. 없는 모델(404)이면 자동으로 다음 모델로 넘어가요.
MODEL_CANDIDATES = ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite"]

SCENARIO_GREETINGS = {
    "Free Conversation": "Hi there! How is your day going so far? What would you like to talk about today?",
    "Ordering at a Cafe": "Welcome to Sunny Cafe! What can I get started for you today?",
    "Job Interview": "Hello! Thank you for coming in today. Could you start by telling me a little bit about yourself?",
    "Airport Immigration": "Good morning. May I see your passport and boarding pass, please? What is the purpose of your visit?",
}

SCENARIO_ICONS = {
    "Free Conversation": "💬",
    "Ordering at a Cafe": "☕",
    "Job Interview": "💼",
    "Airport Immigration": "✈️",
}

# 첫 인사 아래에 보여줄 추천 답변 (초보자용)
SCENARIO_SUGGESTIONS = {
    "Free Conversation": ["I'm doing great, thanks!", "I'm a bit tired today.", "Let's talk about travel."],
    "Ordering at a Cafe": ["Can I have an iced latte, please?", "What do you recommend?", "I'd like a slice of cake."],
    "Job Interview": ["I'm a marketing designer.", "I have three years of experience.", "I'm a quick learner."],
    "Airport Immigration": ["Here is my passport.", "I'm here for sightseeing.", "I'll stay for five days."],
}

USER_AVATAR = "💜"
TUTOR_AVATAR = "🌸"

# ──────────────────────────────────────────────
# 테마 (파스텔 핑크/퍼플 + 다크모드)
# ──────────────────────────────────────────────
THEMES = {
    "light": {
        "bg1": "#fff4fa",
        "bg2": "#f3edff",
        "text": "#4b3f5e",
        "muted": "#8b7fa0",
        "sidebar": "#fbf3ff",
        "card": "#ffffff",
        "border": "#ecdcff",
        "user-bg": "#ffe3f0",
        "user-border": "#ffc9e1",
        "accent": "#b794f6",
        "accent2": "#ff9ccf",
        "input-bg": "#ffffff",
        "shadow": "rgba(168, 130, 230, 0.15)",
    },
    "dark": {
        "bg1": "#1c1c1e",
        "bg2": "#232325",
        "text": "#f2f2f7",
        "muted": "#a1a1a6",
        "sidebar": "#161618",
        "card": "#2c2c2e",
        "border": "#3a3a3c",
        "user-bg": "#3a3a3c",
        "user-border": "#4a4a4d",
        "accent": "#c4a1ff",
        "accent2": "#ff9ccf",
        "input-bg": "#2c2c2e",
        "shadow": "rgba(0, 0, 0, 0.4)",
    },
}

STATIC_CSS = """
html, body, .stApp, [data-testid="stApp"], [data-testid="stAppViewContainer"] {
    background: linear-gradient(160deg, var(--bg1) 0%, var(--bg2) 100%) !important;
    background-attachment: fixed !important;
    color: var(--text) !important;
}
[data-testid="stMain"], [data-testid="stMainBlockContainer"], section.main, .main {
    background: transparent !important;
}
[data-testid="stHeader"], [data-testid="stToolbar"] { background: transparent !important; }
[data-testid="stBottom"], [data-testid="stBottom"] > div, [data-testid="stBottomBlockContainer"] {
    background: transparent !important;
}
[data-testid="stSidebar"], [data-testid="stSidebar"] > div, [data-testid="stSidebarContent"] {
    background: var(--sidebar) !important;
}
[data-testid="stSidebar"] { border-right: 1px solid var(--border); }
.block-container { max-width: 760px; padding-top: 2.2rem; padding-bottom: 6rem; }

h1, h2, h3, h4, p, li, label,
[data-testid="stMarkdownContainer"],
[data-testid="stWidgetLabel"] * { color: var(--text) !important; }
[data-testid="stCaptionContainer"], small { color: var(--muted) !important; }

/* 헤더 */
.hero { text-align: center; margin-bottom: 1.2rem; }
.hero-title {
    font-size: 2.1rem; font-weight: 800; letter-spacing: -0.5px;
    background: linear-gradient(90deg, var(--accent2), var(--accent));
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent;
}
.hero-sub { color: var(--muted); font-size: 0.95rem; margin-top: 4px; }
.chip {
    display: inline-block; padding: 4px 12px; margin: 8px 4px 0 4px;
    border-radius: 999px; font-size: 0.8rem;
    background: var(--card); border: 1px solid var(--border); color: var(--muted);
}

/* 말풍선 */
[data-testid="stChatMessage"], .stChatMessage {
    background: var(--card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 20px !important;
    padding: 14px 18px !important;
    margin-bottom: 12px;
    box-shadow: 0 4px 14px var(--shadow);
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]),
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    background: var(--user-bg) !important;
    border-color: var(--user-border) !important;
}

/* 입력창 */
[data-testid="stChatInput"] {
    background: var(--input-bg) !important;
    border: 1.5px solid var(--border) !important;
    border-radius: 26px !important;
    box-shadow: 0 4px 14px var(--shadow);
}
[data-testid="stChatInput"] textarea {
    background: transparent !important;
    color: var(--text) !important;
}
[data-testid="stChatInput"] button {
    background: linear-gradient(135deg, var(--accent2), var(--accent)) !important;
    color: #ffffff !important;
    border-radius: 50% !important;
}
.stTextInput input {
    background: var(--input-bg) !important;
    color: var(--text) !important;
    border-radius: 14px !important;
    border: 1.5px solid var(--border) !important;
}
[data-testid="stAudioInput"] > div {
    background: var(--input-bg) !important;
    border: 1.5px solid var(--border) !important;
    border-radius: 20px !important;
}

/* 셀렉트박스 */
[data-baseweb="select"] > div {
    background: var(--input-bg) !important;
    border-color: var(--border) !important;
    border-radius: 14px !important;
}
[data-baseweb="select"] * { color: var(--text) !important; }
[data-baseweb="popover"] ul, [data-baseweb="popover"] li, [data-baseweb="menu"] {
    background: var(--card) !important;
    color: var(--text) !important;
}

/* 버튼 */
.stButton > button {
    background: var(--card);
    color: var(--text);
    border: 1.5px solid var(--border);
    border-radius: 999px;
    padding: 0.35rem 1rem;
    transition: all 0.15s ease;
}
.stButton > button:hover {
    border-color: var(--accent2);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px var(--shadow);
}
.stButton > button:hover p { color: var(--accent2) !important; }

/* 오디오 플레이어 */
audio { width: 100%; border-radius: 999px; }
"""


def apply_theme(dark: bool) -> None:
    palette = THEMES["dark" if dark else "light"]
    variables = "\n".join(f"--{k}: {v};" for k, v in palette.items())
    scheme = "dark" if dark else "light"
    css = f":root {{ {variables} color-scheme: {scheme}; }} {STATIC_CSS}"
    # 빈 줄/들여쓰기가 있으면 마크다운 파서가 <style>을 중간에 끊을 수 있어 한 줄로 압축
    css = " ".join(line.strip() for line in css.splitlines() if line.strip())
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


# ──────────────────────────────────────────────
# 저장/불러오기
# ──────────────────────────────────────────────
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


# ──────────────────────────────────────────────
# TTS (edge-tts) + 캐싱
# ──────────────────────────────────────────────
def _run_async(coro_factory):
    """이미 이벤트 루프가 돌고 있어도 안전하게 실행."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())
    with ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(lambda: asyncio.run(coro_factory())).result()


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
        data = _run_async(_synthesize)
        return data or None
    except Exception:
        return None


@st.cache_data(show_spinner=False, max_entries=100)
def _cached_tts(text: str, voice: str) -> bytes:
    data = text_to_speech_bytes(text, voice)
    if not data:
        # 실패 결과는 캐시되지 않도록 예외로 처리
        raise RuntimeError("TTS failed")
    return data


def tts_cached(text: str, voice: str) -> bytes | None:
    try:
        return _cached_tts(text, voice)
    except Exception:
        return None


# ──────────────────────────────────────────────
# 시크릿
# ──────────────────────────────────────────────
def get_secret(name: str) -> str:
    try:
        value = st.secrets[name]
        if value:
            return str(value)
    except Exception:
        pass
    return os.environ.get(name, "")


# ──────────────────────────────────────────────
# URL 쿼리 파라미터 / 테마 초기화
# ──────────────────────────────────────────────
if "chat_id" not in st.query_params or not st.query_params["chat_id"]:
    st.query_params["chat_id"] = "default"
chat_id = str(st.query_params["chat_id"])

if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = st.query_params.get("theme") == "dark"

# ──────────────────────────────────────────────
# 비밀번호 인증
# ──────────────────────────────────────────────
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    apply_theme(st.session_state.dark_mode)
    st.markdown(
        '<div class="hero"><div class="hero-title">🌸 AI English Tutor</div>'
        '<div class="hero-sub">Please log in to start chatting</div></div>',
        unsafe_allow_html=True,
    )
    correct_password = get_secret("APP_PASSWORD")
    if not correct_password:
        try:
            found = ", ".join(st.secrets.keys()) or "(없음)"
        except Exception:
            found = "(secrets를 읽을 수 없음)"
        st.error(
            "⚠️ APP_PASSWORD를 찾지 못했어요. Secrets에 `APP_PASSWORD = \"비밀번호\"` 형태로 "
            f"저장했는지, 저장 후 앱을 Reboot 했는지 확인해 주세요. (현재 인식된 키: {found})"
        )

    password_input = st.text_input("Access Password", type="password")
    if st.button("Login"):
        if not correct_password:
            st.error("비밀번호가 설정되지 않아 로그인할 수 없어요.")
        elif hmac.compare_digest(password_input.encode(), correct_password.encode()):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("❌ Incorrect password.")
    st.stop()

# ──────────────────────────────────────────────
# API 클라이언트
# ──────────────────────────────────────────────
api_key = get_secret("GEMINI_API_KEY")
if not api_key:
    st.error("⚠️ GEMINI_API_KEY가 Streamlit Secrets에 설정되지 않았습니다.")
    st.stop()

client = genai.Client(api_key=api_key)


def stream_generate(contents_payload, system_prompt: str):
    """답변을 글자 단위로 스트리밍. 모델/설정 문제 시 자동 폴백."""
    base = dict(system_instruction=system_prompt, max_output_tokens=400, temperature=0.7)
    configs = [
        # 1순위: 생각(thinking) 끄기 → 가장 빠름
        types.GenerateContentConfig(**base, thinking_config=types.ThinkingConfig(thinking_budget=0)),
        # 2순위: 모델이 thinking 설정을 지원하지 않을 때
        types.GenerateContentConfig(**base),
    ]
    last_error = None

    for model_name in MODEL_CANDIDATES:
        model_missing = False
        for cfg in configs:
            for attempt in range(2):
                started = False
                try:
                    for chunk in client.models.generate_content_stream(
                        model=model_name, contents=contents_payload, config=cfg
                    ):
                        if chunk.text:
                            started = True
                            yield chunk.text
                    return
                except APIError as e:
                    last_error = e
                    if started:
                        raise
                    if e.code in (429, 503) and attempt == 0:
                        time.sleep(1.5)
                        continue
                    if e.code == 404:
                        model_missing = True
                    break
            if model_missing:
                break

    raise RuntimeError(f"구글 AI 서버가 바빠 응답이 지연되고 있습니다. 잠시 후 다시 시도해 주세요. ({last_error})")


# ──────────────────────────────────────────────
# 저장된 데이터 복원 및 상태 초기화
# ──────────────────────────────────────────────
if "loaded_chat_id" not in st.session_state or st.session_state.loaded_chat_id != chat_id:
    saved = load_saved_data(chat_id)
    st.session_state.loaded_chat_id = chat_id
    st.session_state.scenario = saved.get("scenario", "Free Conversation")
    st.session_state.messages = saved.get("messages", [])

st.session_state.setdefault("mic_key", 0)
st.session_state.setdefault("processed_audio_id", None)
st.session_state.setdefault("latest_tts_audio", None)

# ──────────────────────────────────────────────
# 사이드바
# ──────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Settings")

    dark_mode = st.toggle("🌙 다크 모드", key="dark_mode")
    st.query_params["theme"] = "dark" if dark_mode else "light"

    scenarios = list(SCENARIO_GREETINGS.keys())
    current_idx = scenarios.index(st.session_state.scenario) if st.session_state.scenario in scenarios else 0

    new_scenario = st.selectbox(
        "Choose Scenario",
        scenarios,
        index=current_idx,
        format_func=lambda s: f"{SCENARIO_ICONS.get(s, '💬')} {s}",
    )
    if new_scenario != st.session_state.scenario:
        st.session_state.scenario = new_scenario
        st.session_state.messages = []
        st.session_state.processed_audio_id = None
        st.session_state.latest_tts_audio = None
        st.session_state.mic_key += 1
        save_data(chat_id, st.session_state.scenario, st.session_state.messages)
        st.rerun()

    auto_tts = st.toggle("AI 답변 자동 음성 재생 (edge-tts)", value=False)
    voice_choice = st.selectbox(
        "Tutor Voice",
        ["en-US-JennyNeural", "en-US-GuyNeural", "en-GB-SoniaNeural"],
        index=0,
    )

    st.caption(f"저장된 메시지 수: {len(st.session_state.messages)}개 · ID: `{chat_id}`")

    if st.button("➕ 새 대화 시작"):
        new_id = str(uuid.uuid4())[:8]
        st.query_params["chat_id"] = new_id
        st.session_state.loaded_chat_id = None
        st.session_state.messages = []
        st.session_state.processed_audio_id = None
        st.session_state.latest_tts_audio = None
        st.session_state.mic_key += 1
        st.rerun()

    if st.button("🧹 Clear Chat History"):
        st.session_state.messages = []
        st.session_state.processed_audio_id = None
        st.session_state.latest_tts_audio = None
        st.session_state.mic_key += 1
        save_data(chat_id, st.session_state.scenario, st.session_state.messages)
        st.rerun()

apply_theme(dark_mode)

# ──────────────────────────────────────────────
# 헤더
# ──────────────────────────────────────────────
scenario_icon = SCENARIO_ICONS.get(st.session_state.scenario, "💬")
st.markdown(
    f"""
    <div class="hero">
        <div class="hero-title">🌸 AI English Conversation</div>
        <div class="hero-sub">말하고, 듣고, 편하게 연습해요</div>
        <span class="chip">{scenario_icon} {html.escape(st.session_state.scenario)}</span>
        <span class="chip">Session {html.escape(chat_id)}</span>
    </div>
    """,
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────
# 첫 인사
# ──────────────────────────────────────────────
if len(st.session_state.messages) == 0:
    greeting = SCENARIO_GREETINGS.get(st.session_state.scenario, SCENARIO_GREETINGS["Free Conversation"])
    st.session_state.messages.append({"role": "assistant", "content": greeting})
    save_data(chat_id, st.session_state.scenario, st.session_state.messages)

# 방금 생성된 자동 TTS 음성이 있으면 1회 재생
if st.session_state.latest_tts_audio:
    st.audio(st.session_state.latest_tts_audio, format="audio/mp3", autoplay=True)
    st.session_state.latest_tts_audio = None

# ──────────────────────────────────────────────
# 기존 대화 출력
# ──────────────────────────────────────────────
for idx, message in enumerate(st.session_state.messages):
    avatar = TUTOR_AVATAR if message["role"] == "assistant" else USER_AVATAR
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])
        if message["role"] == "assistant" and st.button("🔊 듣기", key=f"tts_{idx}"):
            with st.spinner("음성 만드는 중..."):
                mp3_data = tts_cached(message["content"], voice_choice)
            if mp3_data:
                st.audio(mp3_data, format="audio/mp3", autoplay=True)
            else:
                st.warning("음성 생성에 실패했어요. 잠시 후 다시 시도해 주세요.")

# ──────────────────────────────────────────────
# 추천 답변 칩 (대화 시작 직후에만)
# ──────────────────────────────────────────────
chips_slot = st.empty()
if len(st.session_state.messages) == 1:
    suggestions = SCENARIO_SUGGESTIONS.get(st.session_state.scenario, [])
    if suggestions:
        with chips_slot.container():
            st.caption("💡 이렇게 답해볼까요?")
            cols = st.columns(len(suggestions))
            for i, (col, text) in enumerate(zip(cols, suggestions)):
                if col.button(text, key=f"chip_{st.session_state.scenario}_{i}", use_container_width=True):
                    st.session_state.pending_text = text
                    st.rerun()

# ──────────────────────────────────────────────
# 입력 처리 (마이크 음성 / 텍스트 / 추천 칩)
# ──────────────────────────────────────────────
user_display_text = None
audio_part = None

pending_text = st.session_state.pop("pending_text", None)
mic_audio = st.audio_input("🎙️ 영어로 말해보세요", key=f"mic_{st.session_state.mic_key}")
text_input = st.chat_input("또는 영어로 메시지를 입력하세요...") or pending_text

if mic_audio is not None:
    audio_raw = mic_audio.getvalue()
    current_audio_id = hashlib.md5(audio_raw).hexdigest()
    if current_audio_id != st.session_state.processed_audio_id:
        st.session_state.processed_audio_id = current_audio_id
        user_display_text = "🎙️ (Voice message)"
        audio_part = types.Part.from_bytes(data=audio_raw, mime_type=mic_audio.type or "audio/wav")

elif text_input:
    user_display_text = text_input

if user_display_text is not None:
    chips_slot.empty()

    st.session_state.messages.append({"role": "user", "content": user_display_text})
    save_data(chat_id, st.session_state.scenario, st.session_state.messages)

    recent_messages = st.session_state.messages[-(MAX_HISTORY_MESSAGES + 1):-1]
    history_lines = []
    for m in recent_messages:
        role_label = "Tutor" if m["role"] == "assistant" else "User"
        history_lines.append(f"{role_label}: {m['content']}")
    history_text = "\n".join(history_lines)

    system_prompt = (
        f"You are a friendly English conversation tutor. Current scenario: '{st.session_state.scenario}'. "
        "Reply in 2-3 short, natural sentences to keep the conversation moving. "
        "Never repeat your previous question. "
        "If needed, add at most ONE brief, gentle grammar or expression tip at the end."
    )

    if audio_part is not None:
        prompt_instruction = (
            f"Recent conversation:\n{history_text}\n\n"
            "The user just replied via voice audio (attached).\n"
            "1. Start your response with a single line: '🎧 **You said:** \"<transcribe what the user said>\"'\n"
            "2. Then reply naturally in English to move the conversation forward."
        )
        gemini_contents = [prompt_instruction, audio_part]
    else:
        prompt_instruction = (
            f"Recent conversation:\n{history_text}\n\n"
            f"User's latest message: \"{user_display_text}\"\n\n"
            "Reply naturally based on what the user just said."
        )
        gemini_contents = prompt_instruction

    # 내 메시지를 즉시 표시
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(user_display_text)

    # 답변을 스트리밍으로 표시
    with st.chat_message("assistant", avatar=TUTOR_AVATAR):
        try:
            ai_response = st.write_stream(stream_generate(gemini_contents, system_prompt))
            st.session_state.messages.append({"role": "assistant", "content": ai_response})
            save_data(chat_id, st.session_state.scenario, st.session_state.messages)

            if auto_tts:
                st.session_state.latest_tts_audio = tts_cached(ai_response, voice_choice)

            st.session_state.mic_key += 1
            st.rerun()
        except Exception as e:
            st.error(f"응답 생성 중 에러가 발생했습니다: {e}")
