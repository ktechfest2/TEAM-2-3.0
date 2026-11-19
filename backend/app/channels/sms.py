"""SMS query commands.

Inbound messages are parsed, answered from the shared information service and logged
with a message reference. The sender's number is stored only as a keyed hash. Sending
the reply is a gateway concern: the simulator returns it in the HTTP response, and a
real deployment plugs a provider client in behind `SmsOutbound`."""

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.channels.info import InfoService, Level, UnknownLocationError, normalise_code
from app.channels.text import SMS_MAX_CHARS, sms_parts, truncate
from app.core.rate_limit import SlidingWindowLimiter
from app.db.models import SmsMessage

PARTS_PER_REPLY = 3
PENDING_TTL_SECONDS = 15 * 60
MAX_INBOUND_CHARS = 160
COMMAND_LEVEL: dict[str, Level] = {
    "RESULT": "polling_unit",
    "STATUS": "polling_unit",
    "WARD": "ward",
    "LGA": "lga",
    "STATE": "state",
}
NO_ARGUMENT = ("NATIONAL", "UPDATES", "HELP", "MORE")
HELP_TEXT = [
    "VoteTrace commands:",
    "RESULT <PU code>",
    "STATUS <PU code>",
    "WARD <code>",
    "LGA <code>",
    "STATE <code>",
    "NATIONAL",
    "UPDATES",
]
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


@dataclass(frozen=True)
class IncomingSms:
    provider: str
    provider_message_id: str | None
    sender_hash: str
    text: str


@dataclass(frozen=True)
class SmsResult:
    message_ref: str
    command: str
    argument: str | None
    outcome: str
    parts: list[str]
    duplicate: bool
    has_more: bool


class SmsOutbound(Protocol):
    """Delivers reply parts through a telecom provider, configured from the environment,
    never from code. `app.channels.africastalking.AfricasTalkingSms` implements it."""

    def send(self, phone_number: str, parts: list[str]) -> None: ...


class PendingPages:
    """Remaining reply parts per sender, for the MORE command. In memory, short-lived."""

    def __init__(self) -> None:
        self._items: dict[str, tuple[float, list[str]]] = {}
        self._lock = threading.Lock()

    def put(self, sender_hash: str, parts: list[str]) -> None:
        with self._lock:
            if parts:
                self._items[sender_hash] = (time.monotonic(), parts)
            else:
                self._items.pop(sender_hash, None)
            cutoff = time.monotonic() - PENDING_TTL_SECONDS
            for key in [k for k, (at, _) in self._items.items() if at < cutoff]:
                del self._items[key]

    def take(self, sender_hash: str) -> list[str]:
        with self._lock:
            entry = self._items.pop(sender_hash, None)
        if entry is None or time.monotonic() - entry[0] > PENDING_TTL_SECONDS:
            return []
        return entry[1]


def new_message_ref() -> str:
    return "SMS-" + "".join(secrets.choice(_ALPHABET) for _ in range(10))


@dataclass(frozen=True)
class ParsedCommand:
    command: str
    argument: str | None
    error: str | None = None


def parse(text: str) -> ParsedCommand:
    words = text.strip().upper().split()
    if not words:
        return ParsedCommand("EMPTY", None, "Empty message.")
    if len(text) > MAX_INBOUND_CHARS:
        return ParsedCommand("INVALID", None, "Message too long.")
    command, rest = words[0], words[1:]
    if command in NO_ARGUMENT:
        if rest:
            return ParsedCommand(command, None, f"{command} takes no code.")
        return ParsedCommand(command, None)
    if command in COMMAND_LEVEL:
        if len(rest) != 1:
            return ParsedCommand(command, None, f"Send {command} followed by one code.")
        code = normalise_code(rest[0])
        if code is None:
            return ParsedCommand(command, rest[0][:40], "That code is not valid.")
        return ParsedCommand(command, code)
    return ParsedCommand("UNKNOWN", None, "Unknown command.")


class SmsService:
    def __init__(
        self,
        db: Session,
        info: InfoService,
        limiter: SlidingWindowLimiter,
        pending: PendingPages,
    ) -> None:
        self.db = db
        self.info = info
        self.limiter = limiter
        self.pending = pending

    def handle(self, message: IncomingSms) -> SmsResult:
        if message.provider_message_id:
            existing = self.db.scalar(
                select(SmsMessage).where(
                    SmsMessage.provider == message.provider,
                    SmsMessage.provider_message_id == message.provider_message_id,
                )
            )
            if existing is not None:
                return self._result(existing, duplicate=True, has_more=False)

        allowed, retry_after = self.limiter.check(message.sender_hash)
        if not allowed:
            minutes = max(1, round(retry_after / 60))
            return self._save(
                message,
                ParsedCommand("LIMITED", None),
                "rate_limited",
                [f"Too many messages. Please try again in {minutes} min."],
                has_more=False,
            )

        parsed = parse(message.text)
        outcome, lines = self._answer(parsed, message.sender_hash)
        if outcome == "more":
            parts = self.pending.take(message.sender_hash)
            if not parts:
                return self._save(
                    message, parsed, "invalid", ["Nothing more to send. Send HELP."], False
                )
            return self._send_parts(message, parsed, "ok", parts)
        return self._send_parts(message, parsed, outcome, sms_parts(lines))

    def _send_parts(
        self, message: IncomingSms, parsed: ParsedCommand, outcome: str, parts: list[str]
    ) -> SmsResult:
        now, later = parts[:PARTS_PER_REPLY], parts[PARTS_PER_REPLY:]
        self.pending.put(message.sender_hash, later)
        if later:
            suffix = " Reply MORE"
            now[-1] = truncate(now[-1], SMS_MAX_CHARS - len(suffix)) + suffix
        return self._save(message, parsed, outcome, now, has_more=bool(later))

    def _answer(self, parsed: ParsedCommand, sender_hash: str) -> tuple[str, list[str]]:
        if parsed.error:
            return "invalid", [parsed.error, "Send HELP for the list of commands."]
        command = parsed.command
        if command == "HELP":
            return "ok", HELP_TEXT
        if command == "MORE":
            return "more", []
        if command == "NATIONAL":
            return "ok", self.info.area_lines("national", None)
        if command == "UPDATES":
            items, _ = self.info.updates(1, 3)
            if not items:
                return "ok", ["No election updates yet."]
            return "ok", [self.info.update_headline(item) for item in items]
        level = COMMAND_LEVEL[command]
        assert parsed.argument is not None
        try:
            area_id = self.info.find(level, parsed.argument)
        except UnknownLocationError as exc:
            noun = "polling unit" if level == "polling_unit" else level.upper()
            if level == "state":
                noun = "state"
            return "unknown_location", [
                f"No {noun} found with code {exc.code}.",
                "Check the code and try again.",
            ]
        if command == "STATUS":
            return "ok", self.info.status_lines(area_id)
        if level == "polling_unit":
            return "ok", self.info.polling_unit_lines(area_id)
        return "ok", self.info.area_lines(level, area_id)

    def _save(
        self,
        message: IncomingSms,
        parsed: ParsedCommand,
        outcome: str,
        parts: list[str],
        has_more: bool,
    ) -> SmsResult:
        row = SmsMessage(
            message_ref=new_message_ref(),
            provider=message.provider,
            provider_message_id=message.provider_message_id,
            sender_hash=message.sender_hash,
            command=parsed.command[:20],
            argument=(parsed.argument or None) and parsed.argument[:40],
            outcome=outcome,
            response_parts=parts,
        )
        self.db.add(row)
        try:
            self.db.commit()
        except IntegrityError:
            # The same provider message arrived twice at once; answer from the first.
            self.db.rollback()
            existing = self.db.scalar(
                select(SmsMessage).where(
                    SmsMessage.provider == message.provider,
                    SmsMessage.provider_message_id == message.provider_message_id,
                )
            )
            if existing is None:
                raise
            return self._result(existing, duplicate=True, has_more=False)
        return self._result(row, duplicate=False, has_more=has_more)

    @staticmethod
    def _result(row: SmsMessage, duplicate: bool, has_more: bool) -> SmsResult:
        return SmsResult(
            message_ref=row.message_ref,
            command=row.command,
            argument=row.argument,
            outcome=row.outcome,
            parts=list(row.response_parts),
            duplicate=duplicate,
            has_more=has_more,
        )
