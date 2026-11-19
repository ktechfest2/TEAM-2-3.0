"""Session-based USSD menu.

`UssdSessionHandler` is transport-neutral: the simulator API and any telecom gateway
adapter call the same `start` and `respond` methods. Replies stay within 182
characters. No shortcode is allocated; the simulator does not use one."""

import re
import threading
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from app.channels.info import LEVEL_NAME, InfoService, Level, UnknownLocationError
from app.channels.text import USSD_MAX_CHARS, ascii_text, paginate, truncate
from app.core.errors import AppError

MAIN_MENU = (
    "Welcome to VoteTrace\n"
    "1. Polling Unit Results\n"
    "2. Ward Results\n"
    "3. LGA Results\n"
    "4. State Results\n"
    "5. National Results\n"
    "6. Election Updates\n"
    "0. Exit"
)
MENU_LEVELS: dict[str, Level] = {"1": "polling_unit", "2": "ward", "3": "lga", "4": "state"}
MORE, BACK, HOME = "98", "0", "00"
UPDATES_PER_PAGE = 3
MAX_INVALID = 3
GOODBYE = "Thank you for using VoteTrace."
TIMED_OUT = "Session timed out. Please dial again."
TOO_MANY = "Too many invalid entries. Please dial again."
_INPUT = re.compile(r"^[0-9A-Za-z#*-]{0,40}$")

class Screen(StrEnum):
    MAIN = "main"
    AWAIT_CODE = "await_code"
    RESULT = "result"
    UPDATES = "updates"
    UPDATE_DETAIL = "update_detail"

@dataclass
class UssdSession:
    id: str
    phone_hash: str
    created_at: float
    last_seen: float
    screen: Screen = Screen.MAIN
    level: Level | None = None
    pages: list[str] = field(default_factory=list)
    page_index: int = 0
    updates_page: int = 1
    update_ids: list[str] = field(default_factory=list)
    invalid_count: int = 0

@dataclass(frozen=True)
class UssdReply:
    session_id: str
    text: str
    end: bool
    timed_out: bool = False

class SessionNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__("session_not_found", "No USSD session has that identifier.", 404)

class UssdSessionStore(Protocol):
    """Session state. A multi-instance deployment needs a shared store (for example Redis)."""

    timeout_seconds: float

    def get(self, session_id: str) -> UssdSession | None: ...
    def save(self, session: UssdSession) -> None: ...
    def delete(self, session_id: str) -> None: ...

class InMemoryUssdSessionStore:
    def __init__(self, timeout_seconds: float, max_sessions: int = 10_000) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_sessions = max_sessions
        self._sessions: dict[str, UssdSession] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str) -> UssdSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def save(self, session: UssdSession) -> None:
        with self._lock:
            if session.id not in self._sessions and len(self._sessions) >= self.max_sessions:
                cutoff = time.monotonic() - self.timeout_seconds
                for key in [k for k, s in self._sessions.items() if s.last_seen < cutoff]:
                    del self._sessions[key]
                if len(self._sessions) >= self.max_sessions:
                    raise AppError("ussd_busy", "The service is busy. Please try again.", 503)
            self._sessions[session.id] = session

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

class UssdSessionHandler:
    def __init__(self, store: UssdSessionStore, info: InfoService) -> None:
        self.store = store
        self.info = info

    def start(self, phone_hash: str, session_id: str | None = None) -> UssdReply:
        now = time.monotonic()
        session = UssdSession(
            id=session_id or uuid.uuid4().hex, phone_hash=phone_hash, created_at=now, last_seen=now
        )
        self.store.save(session)
        return self._reply(session, MAIN_MENU)

    def replay(self, phone_hash: str, session_id: str, history: tuple[str, ...]) -> UssdReply:
        """Rebuild a session from the gateway's input history (for example after this
        instance restarted mid-session) and answer the latest input."""
        reply = self.start(phone_hash, session_id)
        for value in history[:20]:
            if reply.end:
                break
            reply = self.respond(session_id, value)
        return reply

    def respond(self, session_id: str, raw_input: str) -> UssdReply:
        session = self.store.get(session_id)
        if session is None:
            raise SessionNotFoundError()
        now = time.monotonic()
        if now - session.last_seen > self.store.timeout_seconds:
            self.store.delete(session_id)
            return UssdReply(session_id, TIMED_OUT, end=True, timed_out=True)
        session.last_seen = now
        value = raw_input.strip()
        if not _INPUT.fullmatch(value):
            return self._invalid(session, "Invalid input.")
        if value == HOME:
            return self._main(session)
        handler = {
            Screen.MAIN: self._on_main,
            Screen.AWAIT_CODE: self._on_code,
            Screen.RESULT: self._on_result,
            Screen.UPDATES: self._on_updates,
            Screen.UPDATE_DETAIL: self._on_update_detail,
        }[session.screen]
        return handler(session, value)

    def _reply(self, session: UssdSession, text: str, end: bool = False) -> UssdReply:
        if end:
            self.store.delete(session.id)
        else:
            self.store.save(session)
        return UssdReply(session.id, truncate(ascii_text(text), USSD_MAX_CHARS), end=end)

    def _main(self, session: UssdSession, prefix: str = "") -> UssdReply:
        session.screen, session.level, session.pages, session.page_index = Screen.MAIN, None, [], 0
        text = MAIN_MENU if not prefix else prefix + "\n" + MAIN_MENU.split("\n", 1)[1]
        return self._reply(session, text)

    def _invalid(self, session: UssdSession, message: str) -> UssdReply:
        session.invalid_count += 1
        if session.invalid_count >= MAX_INVALID:
            return self._reply(session, TOO_MANY, end=True)
        if session.screen == Screen.MAIN:
            return self._main(session, message)
        if session.screen == Screen.AWAIT_CODE and session.level:
            return self._reply(session, f"{message}\n{self._code_prompt(session.level)}")
        if session.screen == Screen.UPDATES:
            return self._updates_screen(session, message)
        return self._page(session, message)

    def _code_prompt(self, level: Level) -> str:
        example = self.info.example_code(level)
        hint = f"\n(e.g. {example})" if example else ""
        return f"Enter {LEVEL_NAME[level]} code{hint}\n0. Back"

    def _on_main(self, session: UssdSession, value: str) -> UssdReply:
        if value == BACK:
            return self._reply(session, GOODBYE, end=True)
        if value in MENU_LEVELS:
            session.screen, session.level = Screen.AWAIT_CODE, MENU_LEVELS[value]
            return self._reply(session, self._code_prompt(session.level))
        if value == "5":
            return self._show(session, self.info.area_lines("national", None))
        if value == "6":
            session.screen, session.updates_page = Screen.UPDATES, 1
            return self._updates_screen(session)
        return self._invalid(session, "Invalid choice.")

    def _on_code(self, session: UssdSession, value: str) -> UssdReply:
        if value == BACK:
            return self._main(session)
        level = session.level
        assert level is not None
        try:
            area_id = self.info.find(level, value)
        except UnknownLocationError as exc:
            return self._invalid(session, f"{exc.code} not found.")
        lines = (
            self.info.polling_unit_lines(area_id)
            if level == "polling_unit"
            else self.info.area_lines(level, area_id)
        )
        return self._show(session, lines)

    def _show(self, session: UssdSession, lines: list[str]) -> UssdReply:
        session.screen = Screen.RESULT
        session.pages = paginate(lines, USSD_MAX_CHARS - 26)
        session.page_index = 0
        session.invalid_count = 0
        return self._page(session)

    def _page(self, session: UssdSession, prefix: str = "") -> UssdReply:
        page = session.pages[session.page_index] if session.pages else ""
        last = session.page_index >= len(session.pages) - 1
        back = "0. Back" if session.screen == Screen.UPDATE_DETAIL else "0. Main menu"
        footer = back if last else f"98. More\n{back}"
        body = f"{prefix}\n{page}" if prefix else page
        limit = USSD_MAX_CHARS - len(footer) - 1
        return self._reply(session, f"{truncate(body, limit)}\n{footer}")

    def _on_result(self, session: UssdSession, value: str) -> UssdReply:
        if value == BACK:
            return self._main(session)
        if value == MORE and session.page_index < len(session.pages) - 1:
            session.page_index += 1
            return self._page(session)
        return self._invalid(session, "Invalid choice.")

    def _updates_screen(self, session: UssdSession, prefix: str = "") -> UssdReply:
        items, total_pages = self.info.updates(session.updates_page, UPDATES_PER_PAGE)
        session.update_ids = [str(item.id) for item in items]
        if not items:
            lines = ["No election updates yet."]
        else:
            width = (USSD_MAX_CHARS - 40) // max(1, len(items)) - 4
            lines = [
                f"{i}. {truncate(self.info.update_headline(item), width)}"
                for i, item in enumerate(items, start=1)
            ]
        footer = ["98. More"] if session.updates_page < total_pages else []
        text = "\n".join(([prefix] if prefix else ["Election updates"]) + lines + footer)
        return self._reply(session, f"{text}\n0. Main menu")

    def _on_updates(self, session: UssdSession, value: str) -> UssdReply:
        if value == BACK:
            return self._main(session)
        _, total_pages = self.info.updates(session.updates_page, UPDATES_PER_PAGE)
        if value == MORE and session.updates_page < total_pages:
            session.updates_page += 1
            return self._updates_screen(session)
        if value.isdigit() and 1 <= int(value) <= len(session.update_ids):
            wanted = session.update_ids[int(value) - 1]
            items, _ = self.info.updates(session.updates_page, UPDATES_PER_PAGE)
            update = next((u for u in items if str(u.id) == wanted), None)
            if update is not None:
                session.screen = Screen.UPDATE_DETAIL
                session.pages = paginate(self.info.update_lines(update), USSD_MAX_CHARS - 26)
                session.page_index = 0
                return self._page(session)
        return self._invalid(session, "Invalid choice.")

    def _on_update_detail(self, session: UssdSession, value: str) -> UssdReply:
        if value == BACK:
            session.screen = Screen.UPDATES
            return self._updates_screen(session)
        if value == MORE and session.page_index < len(session.pages) - 1:
            session.page_index += 1
            return self._page(session)
        return self._invalid(session, "Invalid choice.")

@dataclass(frozen=True)
class GatewayUssdRequest:
    session_id: str
    phone_number: str
    user_input: str | None
    # Every input so far, oldest first, when the gateway sends the full history.
    history: tuple[str, ...] = ()

class UssdGatewayAdapter(Protocol):
    """Translates one telecom gateway's callback format to and from the handler."""

    name: str

    def parse(self, form: Mapping[str, str]) -> GatewayUssdRequest: ...
    def render(self, reply: UssdReply) -> str: ...

class CumulativeTextAdapter:
    """The widely used callback shape: `sessionId`, `phoneNumber`, `serviceCode` and
    `text`, where `text` holds every input so far joined by `*`. Replies start with
    `CON ` (expect more input) or `END ` (close the session)."""

    name = "cumulative-text"

    def parse(self, form: Mapping[str, str]) -> GatewayUssdRequest:
        session_id = (form.get("sessionId") or "").strip()
        phone = (form.get("phoneNumber") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", session_id) or not phone:
            raise AppError("invalid_gateway_payload", "The USSD callback is incomplete.", 422)
        text = form.get("text") or ""
        if len(text) > 400:
            raise AppError("invalid_gateway_payload", "The USSD input is too long.", 422)
        history = tuple(text.split("*")) if text else ()
        return GatewayUssdRequest(
            f"gw:{session_id}", phone, history[-1] if history else None, history
        )

    def render(self, reply: UssdReply) -> str:
        return ("END " if reply.end else "CON ") + reply.text
