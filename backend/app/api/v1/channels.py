"""USSD and SMS routes. Read-only for electoral information: these handlers can only
call the shared information service, which reads aggregates, the register and updates.

Simulator calls (no signature) are accepted only while simulator mode is on. Gateway
callbacks must carry `X-VoteTrace-Signature: sha256=<HMAC-SHA256 of the raw body>`, or,
for providers that cannot sign (Africa's Talking), `?token=<CHANNEL_CALLBACK_TOKEN>`."""

from typing import Annotated
from urllib.parse import parse_qsl

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels import africastalking, security
from app.channels.info import DEMO_TAG, InfoService, channel_election
from app.channels.sms import IncomingSms, PendingPages, SmsService
from app.channels.ussd import (
    CumulativeTextAdapter,
    InMemoryUssdSessionStore,
    SessionNotFoundError,
    UssdReply,
    UssdSessionHandler,
    UssdSessionStore,
)
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.rate_limit import SlidingWindowLimiter
from app.core.security import Principal, get_optional_principal
from app.db.enums import INCIDENT_STAFF_ROLES
from app.db.models import SmsMessage
from app.directory.repository import DirectoryRepository, get_directory
from app.evidence.db import get_evidence_db
from app.schemas.common import ApiModel
from app.schemas.evidence import UtcDateTime

ussd_router = APIRouter(prefix="/ussd", tags=["ussd"])
sms_router = APIRouter(prefix="/sms", tags=["sms"])

Db = Annotated[Session, Depends(get_evidence_db)]
Directory = Annotated[DirectoryRepository, Depends(get_directory)]
AppSettings = Annotated[Settings, Depends(get_settings)]
MaybePrincipal = Annotated[Principal | None, Depends(get_optional_principal)]
Signature = Annotated[str | None, Header(alias=security.SIGNATURE_HEADER, max_length=200)]
CallbackToken = Annotated[str | None, Query(max_length=200)]

SIMULATOR_NOTICE = (
    "Simulator. No telecom gateway or shortcode is connected; replies are returned here "
    "instead of being sent to a phone."
)
_ussd_adapter = CumulativeTextAdapter()

def _shared(request: Request, name: str, factory):
    state = request.app.state
    value = getattr(state, name, None)
    if value is None:
        value = factory()
        setattr(state, name, value)
    return value

def _session_store(request: Request, settings: AppSettings) -> UssdSessionStore:
    return _shared(
        request,
        "ussd_sessions",
        lambda: InMemoryUssdSessionStore(settings.ussd_session_timeout_seconds),
    )

def _info(db: Db, directory: Directory, settings: AppSettings) -> InfoService:
    return InfoService(db, directory, channel_election(directory, settings))

Info = Annotated[InfoService, Depends(_info)]
Store = Annotated[UssdSessionStore, Depends(_session_store)]

class UssdStartIn(ApiModel):
    phone_number: str | None = Field(default=None, max_length=20)

class UssdInputIn(ApiModel):
    input: str = Field(max_length=40)

class UssdOut(ApiModel):
    session_id: str
    text: str
    end: bool
    timed_out: bool
    timeout_seconds: int
    election: str
    demo_label: str | None
    notice: str = SIMULATOR_NOTICE

def _ussd_out(reply: UssdReply, info: InfoService, settings: Settings) -> UssdOut:
    demo = info.election.is_demo or info.directory.source.kind == "demo"
    return UssdOut(
        session_id=reply.session_id,
        text=reply.text,
        end=reply.end,
        timed_out=reply.timed_out,
        timeout_seconds=settings.ussd_session_timeout_seconds,
        election=info.election.name,
        demo_label=DEMO_TAG if demo else None,
    )

@ussd_router.post("/sessions", response_model=UssdOut, status_code=201)
def start_ussd_session(
    payload: UssdStartIn, info: Info, store: Store, settings: AppSettings
) -> UssdOut:
    """Simulator: dial in. Returns the main menu and a session identifier."""
    security.require_simulator(settings)
    phone_hash = security.hash_phone(settings, payload.phone_number or "+2340000000000")
    reply = UssdSessionHandler(store, info).start(phone_hash)
    return _ussd_out(reply, info, settings)

@ussd_router.post("/sessions/{session_id}/input", response_model=UssdOut)
def ussd_input(
    session_id: str, payload: UssdInputIn, info: Info, store: Store, settings: AppSettings
) -> UssdOut:
    """Simulator: send one menu choice or code."""
    security.require_simulator(settings)
    if len(session_id) > 64:
        raise SessionNotFoundError()
    reply = UssdSessionHandler(store, info).respond(session_id, payload.input)
    return _ussd_out(reply, info, settings)

@ussd_router.post("/gateway", response_class=PlainTextResponse)
async def ussd_gateway(
    request: Request,
    info: Info,
    store: Store,
    settings: AppSettings,
    signature: Signature = None,
    token: CallbackToken = None,
) -> PlainTextResponse:
    """Telecom gateway callback (form-encoded, cumulative `text`). Replies `CON`/`END`.

    This is the Africa's Talking USSD format. Set the provider's callback URL to
    `https://<public host>/api/v1/ussd/gateway?token=<CHANNEL_CALLBACK_TOKEN>`."""
    body = await request.body()
    if len(body) > 4096:
        raise AppError("invalid_gateway_payload", "The USSD callback is too large.", 413)
    security.verify_origin(settings, settings.ussd_webhook_secret, body, signature, token)
    form = dict(parse_qsl(body.decode("utf-8", errors="replace"), keep_blank_values=True))
    call = _ussd_adapter.parse(form)
    handler = UssdSessionHandler(store, info)
    phone_hash = security.hash_phone(settings, call.phone_number)
    if call.user_input is None:
        reply = handler.start(phone_hash, call.session_id)
    elif store.get(call.session_id) is None:
        reply = handler.replay(phone_hash, call.session_id, call.history)
    else:
        reply = handler.respond(call.session_id, call.user_input)
    return PlainTextResponse(_ussd_adapter.render(reply))

class SmsIn(ApiModel):
    sender: str = Field(alias="from", max_length=20)
    text: str = Field(max_length=480)
    message_id: str | None = Field(default=None, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")

    model_config = ApiModel.model_config | {"populate_by_name": True}

class SmsOut(ApiModel):
    message_ref: str
    command: str
    outcome: str
    parts: list[str]
    has_more: bool
    duplicate: bool
    provider: str
    notice: str = SIMULATOR_NOTICE

class SmsMessageOut(ApiModel):
    message_ref: str
    provider: str
    command: str
    argument: str | None
    outcome: str
    parts: list[str]
    received_at: UtcDateTime

def _sms_limiter(request: Request, settings: AppSettings) -> SlidingWindowLimiter:
    return _shared(
        request,
        "sms_limiter",
        lambda: SlidingWindowLimiter(settings.sms_messages_per_window, settings.sms_window_seconds),
    )

def _pending(request: Request) -> PendingPages:
    return _shared(request, "sms_pending", PendingPages)

@sms_router.post("/incoming", response_model=SmsOut)
async def sms_incoming(
    request: Request,
    db: Db,
    info: Info,
    settings: AppSettings,
    limiter: Annotated[SlidingWindowLimiter, Depends(_sms_limiter)],
    pending: Annotated[PendingPages, Depends(_pending)],
    signature: Signature = None,
) -> SmsOut:
    """An inbound SMS (JSON: from, text, message_id). The reply is returned in the
    response; a production gateway integration also hands it to an `SmsOutbound`."""
    body = await request.body()
    if len(body) > 4096:
        raise AppError("invalid_gateway_payload", "The SMS callback is too large.", 413)
    origin = security.verify_origin(settings, settings.sms_webhook_secret, body, signature)
    try:
        payload = SmsIn.model_validate_json(body)
    except ValueError as exc:
        raise AppError("validation_error", "The SMS payload is invalid.", 422) from exc
    message = IncomingSms(
        provider=origin,
        provider_message_id=payload.message_id,
        sender_hash=security.hash_phone(settings, payload.sender),
        text=payload.text,
    )
    result = SmsService(db, info, limiter, pending).handle(message)
    return SmsOut(
        message_ref=result.message_ref,
        command=result.command,
        outcome=result.outcome,
        parts=result.parts,
        has_more=result.has_more,
        duplicate=result.duplicate,
        provider=origin,
    )

@sms_router.post("/africastalking", response_class=PlainTextResponse)
async def sms_africastalking(
    request: Request,
    background: BackgroundTasks,
    db: Db,
    info: Info,
    settings: AppSettings,
    limiter: Annotated[SlidingWindowLimiter, Depends(_sms_limiter)],
    pending: Annotated[PendingPages, Depends(_pending)],
    token: CallbackToken = None,
) -> PlainTextResponse:
    """Africa's Talking inbound SMS callback (form-encoded). Set the provider's callback URL
    to `https://<public host>/api/v1/sms/africastalking?token=<CHANNEL_CALLBACK_TOKEN>`.

    The reply is sent back through the Africa's Talking messaging API after the response,
    so the provider gets its 200 quickly. Duplicate deliveries are answered from the log
    and not sent again."""
    if not security.verify_callback_token(settings, token):
        raise AppError("unauthorized", "The gateway callback token is required.", 401)
    body = await request.body()
    if len(body) > 4096:
        raise AppError("invalid_gateway_payload", "The SMS callback is too large.", 413)
    inbound = africastalking.parse_inbound(
        dict(parse_qsl(body.decode("utf-8", errors="replace"), keep_blank_values=True))
    )
    message = IncomingSms(
        provider=africastalking.PROVIDER,
        provider_message_id=inbound.message_id,
        sender_hash=security.hash_phone(settings, inbound.sender),
        text=inbound.text,
    )
    result = SmsService(db, info, limiter, pending).handle(message)
    if not result.duplicate and result.parts and africastalking.is_configured(settings):
        sender = africastalking.AfricasTalkingSms(settings)
        background.add_task(sender.send, inbound.sender, result.parts, inbound.link_id)
    return PlainTextResponse("OK")

@sms_router.get("/messages/{message_ref}", response_model=SmsMessageOut)
def sms_message(
    message_ref: str, db: Db, settings: AppSettings, principal: MaybePrincipal
) -> SmsMessageOut:
    """A logged message and its reply. Open while the simulator is on; staff only otherwise.
    The sender's number is never returned (only a keyed hash is stored)."""
    is_staff = principal is not None and any(r in INCIDENT_STAFF_ROLES for r in principal.roles)
    if not (settings.simulator_enabled or is_staff):
        raise AppError("forbidden", "You do not have access to this resource.", 403)
    row = db.scalar(select(SmsMessage).where(SmsMessage.message_ref == message_ref[:24].upper()))
    if row is None:
        raise AppError("not_found", "No message has that reference.", 404)
    return SmsMessageOut(
        message_ref=row.message_ref,
        provider=row.provider,
        command=row.command,
        argument=row.argument,
        outcome=row.outcome,
        parts=list(row.response_parts),
        received_at=row.received_at,
    )
