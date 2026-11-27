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
from datetime import datetime
from zoneinfo import ZoneInfo

import edge_tts
import streamlit as st
import streamlit.components.v1 as components
from google import genai
from google.genai import types
from google.genai.errors import APIError

st.set_page_config(page_title="AI English Tutor", page_icon="🌸", layout="centered")

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
SAVE_DIR = ".chat_history_cache"
os.makedirs(SAVE_DIR, exist_ok=True)

REVIEW_DIR = ".review_cache"
os.makedirs(REVIEW_DIR, exist_ok=True)
REVIEW_FILE = os.path.join(REVIEW_DIR, "notes.json")

TTS_VOICE = "en-US-JennyNeural"
MAX_HISTORY_MESSAGES = 6

# 앞에서부터 순서대로 시도합니다. 없는 모델(404)이면 자동으로 다음 모델로 넘어가요.
MODEL_CANDIDATES = ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite"]

SCENARIO_GREETINGS = {
    "Overseas Buyer Meeting": "Hello, nice to meet you! I'm interested in your brand. Could you briefly introduce your best-selling product?",
    "Pop-up Store Guest": "Hi! This pop-up store looks so pretty. Can you tell me what this product is?",
    "Design Reference Talk": "Thanks for sharing the draft. Could you walk me through the concept behind this design?",
    "Free Conversation": "Hi there! How is your day going so far? What would you like to talk about today?",
    "Ordering at a Cafe": "Welcome to Sunny Cafe! What can I get started for you today?",
    "Job Interview": "Hello! Thank you for coming in today. Could you start by telling me a little bit about yourself?",
    "Airport Immigration": "Good morning. May I see your passport and boarding pass, please? What is the purpose of your visit?",
}

SCENARIO_ICONS = {
    "Overseas Buyer Meeting": "🤝",
    "Pop-up Store Guest": "🛍️",
    "Design Reference Talk": "🎨",
    "Free Conversation": "💬",
    "Ordering at a Cafe": "☕",
    "Job Interview": "💼",
    "Airport Immigration": "✈️",
}

# 첫 인사 아래에 보여줄 추천 답변 (초보자용)
SCENARIO_SUGGESTIONS = {
    "Overseas Buyer Meeting": [
        "It's our best-selling scalp care product.",
        "We focus on gentle, natural ingredients.",
        "Let me show you our catalog.",
    ],
    "Pop-up Store Guest": [
        "It's a toner pad for sensitive skin.",
        "Would you like to try a sample?",
        "What's your skin type?",
    ],
    "Design Reference Talk": [
        "We used soft pastel colors.",
        "The concept is clean and gentle.",
        "The target is women in their twenties.",
    ],
    "Free Conversation": ["I'm doing great, thanks!", "I'm a bit tired today.", "Let's talk about travel."],
    "Ordering at a Cafe": ["Can I have an iced latte, please?", "What do you recommend?", "I'd like a slice of cake."],
    "Job Interview": ["I'm a marketing designer.", "I have three years of experience.", "I'm a quick learner."],
    "Airport Immigration": ["Here is my passport.", "I'm here for sightseeing.", "I'll stay for five days."],
}

# 직무 맞춤 시나리오에서 AI가 맡을 역할
SCENARIO_ROLES = {
    "Overseas Buyer Meeting": (
        "Role-play as an overseas beauty retail buyer (for example from a drugstore chain in Southeast Asia or Taiwan) "
        "meeting a Korean cosmetics brand's marketing/design team member. "
        "Ask about products, key ingredients, packaging design, pricing, minimum order quantity, promotion plans and marketing materials."
    ),
    "Pop-up Store Guest": (
        "Role-play as a curious foreign tourist visiting a Korean cosmetics pop-up store. "
        "Ask about products, skin type recommendations, scents, textures, events, free samples, prices and how to use them."
    ),
    "Design Reference Talk": (
        "Role-play as an overseas marketing partner reviewing the learner's banner and detail-page design drafts. "
        "Ask about the concept, color palette, typography and target customers, and politely request revisions."
    ),
}


def build_system_prompt(scenario: str, short_mode: bool) -> str:
    role = SCENARIO_ROLES.get(scenario)
    if role:
        intro = (
            f"{role} Stay in character, but use simple, clear English for an intermediate learner. "
            "The learner is a Korean cosmetics marketing designer practicing for real work situations."
        )
    else:
        intro = f"You are a friendly English conversation tutor. Current scenario: '{scenario}'."

    if short_mode:
        length = "Reply with ONE or TWO short sentences and ask only ONE short question at a time."
    else:
        length = "Reply in 2-3 short, natural sentences to keep the conversation moving."

    return (
        f"{intro} {length} "
        "Never repeat your previous question. "
        "If the learner made a notable mistake, add one very brief tip in Korean on a new line starting with '💡'."
    )


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
    # 마크다운 <style>이 적용되지 않는 환경을 대비해, 페이지 <head>에 직접 주입 (rerun 때마다 내용만 교체)
    script = (
        "<script>"
        "const d = window.parent.document;"
        "let s = d.getElementById('app-theme-style');"
        "if (!s) { s = d.createElement('style'); s.id = 'app-theme-style'; d.head.appendChild(s); }"
        f"s.textContent = {json.dumps(css)};"
        "</script>"
    )
    try:
        if hasattr(st, "iframe"):  # 최신 Streamlit (components.html은 곧 제거 예정)
            st.iframe(script, height=1)
        else:
            components.html(script, height=0)
    except Exception:
        pass  # 실패해도 위의 <style> 주입이 있으니 앱은 계속 동작


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


def list_saved_chats(limit: int = 20) -> list:
    """저장된 대화 파일들을 최근 순으로 읽어 요약 정보를 반환."""
    items = []
    try:
        names = os.listdir(SAVE_DIR)
    except Exception:
        return items
    for name in names:
        if not name.endswith(".json"):
            continue
        path = os.path.join(SAVE_DIR, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            messages = data.get("messages", [])
            first_user = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
            items.append(
                {
                    "id": name[:-5],
                    "scenario": data.get("scenario", "Free Conversation"),
                    "count": len(messages),
                    "preview": first_user.replace("\n", " ").strip(),
                    "mtime": os.path.getmtime(path),
                }
            )
        except Exception:
            continue
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items[:limit]


def delete_chat(target_id: str) -> None:
    get_memory_store().pop(target_id, None)
    try:
        os.remove(_file_path(target_id))
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
    lines = [line for line in text.splitlines() if not line.strip().startswith(("🎧", "💡"))]
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
    configs = []
    try:
        # 1순위: 생각(thinking) 끄기 → 가장 빠름
        configs.append(
            types.GenerateContentConfig(**base, thinking_config=types.ThinkingConfig(thinking_budget=0))
        )
    except Exception:
        pass
    configs += [
        # 2순위: 모델이 thinking 설정을 지원하지 않거나 빈 응답이 올 때
        types.GenerateContentConfig(system_instruction=system_prompt, max_output_tokens=1500, temperature=0.7),
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
                    if started:
                        st.session_state.last_model = model_name
                        return
                    # 에러는 없는데 텍스트가 비어 있는 경우 → 다음 설정/모델로 재시도
                    last_error = RuntimeError(f"{model_name}: 빈 응답")
                    break
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
                except Exception as e:
                    last_error = e
                    if started:
                        raise
                    break
            if model_missing:
                break

    raise RuntimeError(f"구글 AI 서버가 바빠 응답이 지연되고 있습니다. 잠시 후 다시 시도해 주세요. ({last_error})")


# ──────────────────────────────────────────────
# 힌트 / 복습 문장
# ──────────────────────────────────────────────
def generate_json(prompt: str, system: str) -> dict:
    """Gemini가 JSON으로 답하게 하고 파싱해서 반환. 모델/설정 폴백 포함."""
    cfgs = []
    try:
        cfgs.append(
            types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.4,
                max_output_tokens=800,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            )
        )
    except Exception:
        pass
    cfgs.append(
        types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.4,
            max_output_tokens=2500,
            response_mime_type="application/json",
        )
    )

    last_error = None
    for model_name in MODEL_CANDIDATES:
        for cfg in cfgs:
            try:
                resp = client.models.generate_content(model=model_name, contents=prompt, config=cfg)
                text = (resp.text or "").strip()
                if text.startswith("```"):
                    text = text.strip("`").strip()
                    if text.lower().startswith("json"):
                        text = text[4:].strip()
                if not text:
                    last_error = RuntimeError(f"{model_name}: 빈 응답")
                    continue
                data = json.loads(text)
                st.session_state.last_model = model_name
                return data
            except APIError as e:
                last_error = e
                if e.code in (429, 503):
                    time.sleep(1.5)
                if e.code == 404:
                    break
            except Exception as e:
                last_error = e
    raise RuntimeError(f"AI 응답을 가져오지 못했어요. 잠시 후 다시 시도해 주세요. ({last_error})")


def get_hints(korean_text: str, last_tutor: str, scenario: str) -> list:
    system = "You are a supportive English coach for a Korean learner. Output valid JSON only."
    idea = korean_text.strip() or "(the learner has no idea what to say; suggest good replies)"
    prompt = (
        f"Scenario: {scenario}\n"
        f'The other person just said: "{last_tutor}"\n'
        f'The learner wants to say this (rough idea in Korean): "{idea}"\n\n'
        "Give exactly 3 natural English replies the learner can say next, each at most 2 short sentences: "
        "(1) simplest, (2) natural and polite, (3) a bit richer. "
        'Return JSON: {"options":[{"level":"쉬움","en":"...","ko":"한국어 뜻"},'
        '{"level":"자연스럽게","en":"...","ko":"..."},{"level":"풍부하게","en":"...","ko":"..."}]}'
    )
    data = generate_json(prompt, system)
    options = data.get("options", []) if isinstance(data, dict) else []
    return [o for o in options if isinstance(o, dict) and o.get("en")]


def load_reviews() -> list:
    try:
        with open(REVIEW_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_reviews(items: list) -> None:
    try:
        with open(REVIEW_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def add_reviews(new_items: list, scenario: str) -> int:
    items = load_reviews()
    existing = {str(i.get("en", "")).strip().lower() for i in items}
    today = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
    added = 0
    for n in new_items:
        if not isinstance(n, dict):
            continue
        en = str(n.get("en", "")).strip()
        if not en or en.lower() in existing:
            continue
        items.append(
            {
                "id": uuid.uuid4().hex[:8],
                "en": en,
                "ko": str(n.get("ko", "")).strip(),
                "note": str(n.get("note", "")).strip(),
                "scenario": scenario,
                "created": today,
                "reviewed": 0,
            }
        )
        existing.add(en.lower())
        added += 1
    save_reviews(items)
    return added


def pick_today_reviews(items: list, n: int = 5) -> list:
    """아직 졸업(3회 외움)하지 않은 문장 중 덜 복습한 것/오래된 것부터 n개."""
    active = [i for i in items if i.get("reviewed", 0) < 3]
    active.sort(key=lambda i: (i.get("reviewed", 0), i.get("created", "")))
    return active[:n]


def mark_reviewed(item_id: str) -> None:
    items = load_reviews()
    for it in items:
        if it.get("id") == item_id:
            it["reviewed"] = it.get("reviewed", 0) + 1
    save_reviews(items)


def delete_review(item_id: str) -> None:
    save_reviews([i for i in load_reviews() if i.get("id") != item_id])


def extract_and_save_reviews(messages: list, scenario: str) -> int:
    lines = []
    for m in messages[-16:]:
        label = "Tutor" if m["role"] == "assistant" else "Learner"
        lines.append(f"{label}: {m['content']}")
    transcript = "\n".join(lines)
    system = "You are an English tutor for a Korean learner. Output valid JSON only."
    prompt = (
        f"Scenario: {scenario}\n"
        f"Conversation:\n{transcript}\n\n"
        "Pick up to 5 short sentences (under 15 words each) worth reviewing: improved or corrected versions "
        "of the learner's own sentences, and useful expressions from the tutor that the learner can reuse in this scenario. "
        'Return JSON: {"items":[{"en":"English sentence","ko":"한국어 뜻","note":"짧은 한국어 설명"}]}'
    )
    data = generate_json(prompt, system)
    items = data.get("items", []) if isinstance(data, dict) else []
    return add_reviews(items, scenario)


def render_review_panel() -> None:
    reviews = load_reviews()
    if not reviews:
        return
    due = pick_today_reviews(reviews)
    with st.expander(f"🔁 오늘의 복습 문장 ({len(due)}개 · 전체 {len(reviews)}개)", expanded=False):
        if not due:
            st.caption("🎉 오늘 복습할 문장을 모두 외웠어요! 새 대화에서 또 뽑아 보세요.")
        else:
            st.caption("한국어를 보고 영어로 말해 본 뒤 '영어 보기'로 확인하세요. '외웠어요'를 3번 누르면 졸업!")
        for it in due:
            st.markdown(f"**{it.get('ko') or '(뜻 없음)'}**")
            c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
            show_key = f"rv_show_{it['id']}"
            if c1.button("👀 영어 보기", key=f"rv_btn_show_{it['id']}", use_container_width=True):
                st.session_state[show_key] = not st.session_state.get(show_key, False)
            if c2.button("✅ 외웠어요", key=f"rv_btn_done_{it['id']}", use_container_width=True):
                mark_reviewed(it["id"])
                st.rerun()
            play = c3.button("🔊", key=f"rv_btn_play_{it['id']}")
            if c4.button("🗑", key=f"rv_btn_del_{it['id']}"):
                delete_review(it["id"])
                st.rerun()
            if st.session_state.get(show_key):
                st.markdown(f"> {it['en']}")
                if it.get("note"):
                    st.caption(it["note"])
            if play:
                mp3 = tts_cached(it["en"], voice_choice)
                if mp3:
                    st.audio(mp3, format="audio/mp3", autoplay=True)
            st.divider()


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
st.session_state.setdefault("hint_result", None)
st.session_state.setdefault("hint_key", 0)


def switch_chat(new_id: str) -> None:
    """다른 대화로 전환 (저장된 내용은 위의 복원 로직이 불러옴)."""
    st.session_state.hint_result = None
    st.query_params["chat_id"] = new_id
    st.session_state.loaded_chat_id = None
    st.session_state.processed_audio_id = None
    st.session_state.latest_tts_audio = None
    st.session_state.mic_key += 1
    st.rerun()


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
    short_mode = st.toggle("✂️ 짧게, 한 번에 한 문장씩", value=True)
    voice_choice = st.selectbox(
        "Tutor Voice",
        ["en-US-JennyNeural", "en-US-GuyNeural", "en-GB-SoniaNeural"],
        index=0,
    )

    st.caption(f"현재 대화 메시지: {len(st.session_state.messages)}개 · ID: `{chat_id}`")
    st.caption(f"최근 응답 모델: {st.session_state.get('last_model', '-')}")

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

    st.divider()
    st.markdown("##### 🔁 복습 문장")
    if st.button("📝 이 대화에서 복습 문장 뽑기", use_container_width=True):
        user_turns = [m for m in st.session_state.messages if m["role"] == "user"]
        if not user_turns:
            st.warning("먼저 대화를 조금 해보세요!")
        else:
            with st.spinner("복습 문장 고르는 중..."):
                try:
                    added = extract_and_save_reviews(st.session_state.messages, st.session_state.scenario)
                    if added:
                        st.success(f"{added}개 저장했어요! 위쪽 '오늘의 복습 문장'에서 확인하세요.")
                    else:
                        st.info("새로 저장할 문장이 없었어요 (이미 저장됐거나 비어 있어요).")
                except Exception as e:
                    st.error(f"복습 문장 생성에 실패했어요: {e}")

    st.divider()
    st.markdown("##### 📚 이전 대화")
    saved_chats = [c for c in list_saved_chats() if c["count"] > 1 or c["id"] == chat_id]
    if not saved_chats:
        st.caption("아직 저장된 대화가 없어요.")
    for c in saved_chats:
        is_current = c["id"] == chat_id
        icon = SCENARIO_ICONS.get(c["scenario"], "💬")
        preview = c["preview"] or "새 대화"
        if len(preview) > 14:
            preview = preview[:14] + "…"
        when = datetime.fromtimestamp(c["mtime"], ZoneInfo("Asia/Seoul")).strftime("%m/%d %H:%M")
        label = f"{'▶ ' if is_current else ''}{icon} {preview} · {when}"

        col_open, col_del = st.columns([5, 1])
        if col_open.button(label, key=f"open_{c['id']}", use_container_width=True, help=f"메시지 {c['count']}개"):
            if not is_current:
                switch_chat(c["id"])
        if col_del.button("🗑", key=f"del_{c['id']}", help="이 대화 삭제"):
            delete_chat(c["id"])
            if is_current:
                switch_chat(str(uuid.uuid4())[:8])
            else:
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

render_review_panel()

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
# 🆘 막힐 때: 한국어로 말하고 영어 힌트 받기
# ──────────────────────────────────────────────
with st.expander("🆘 막힐 때: 한국어로 말하고 영어 힌트 받기", expanded=bool(st.session_state.hint_result)):
    hint_ko = st.text_area(
        "한국어로 대충 말해보세요 (비워두면 추천 답변을 드려요)",
        key=f"hint_ko_{st.session_state.hint_key}",
        height=80,
        placeholder="예: 이 제품은 민감한 피부에도 순하고 향이 은은하다고 말하고 싶어요",
    )
    if st.button("💡 힌트 받기", key="hint_btn"):
        last_tutor = next(
            (m["content"] for m in reversed(st.session_state.messages) if m["role"] == "assistant"), ""
        )
        last_tutor = "\n".join(
            ln for ln in last_tutor.splitlines() if not ln.strip().startswith(("🎧", "💡"))
        )
        with st.spinner("힌트 만드는 중..."):
            try:
                st.session_state.hint_result = get_hints(hint_ko, last_tutor, st.session_state.scenario)
            except Exception as e:
                st.session_state.hint_result = None
                st.error(f"힌트를 가져오지 못했어요: {e}")

    for i, opt in enumerate(st.session_state.hint_result or []):
        st.markdown(f"**{opt.get('level', '')}** · {opt.get('en', '')}")
        if opt.get("ko"):
            st.caption(opt["ko"])
        if st.button("➡️ 이 문장으로 말하기", key=f"hint_use_{i}"):
            st.session_state.pending_text = opt["en"]
            st.session_state.hint_result = None
            st.session_state.hint_key += 1
            st.rerun()

# ──────────────────────────────────────────────
# 입력 처리 (마이크 음성 / 텍스트 / 추천 칩)
# ──────────────────────────────────────────────
user_display_text = None
audio_part = None

pending_text = st.session_state.pop("pending_text", None)
mic_audio = st.audio_input("🎙️ 영어로 말해보세요", key=f"mic_{st.session_state.mic_key}")
text_input = st.chat_input("또는 영어로 메시지를 입력하세요...") or pending_text

if text_input:
    user_display_text = text_input

elif mic_audio is not None:
    audio_raw = mic_audio.getvalue()
    current_audio_id = hashlib.md5(audio_raw).hexdigest()
    if current_audio_id != st.session_state.processed_audio_id:
        st.session_state.processed_audio_id = current_audio_id
        user_display_text = "🎙️ (Voice message)"
        audio_part = types.Part.from_bytes(data=audio_raw, mime_type=mic_audio.type or "audio/wav")

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

    system_prompt = build_system_prompt(st.session_state.scenario, short_mode)

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
            st.session_state.hint_result = None
            st.rerun()
        except Exception as e:
            st.error(f"응답 생성 중 에러가 발생했습니다: {e}")
