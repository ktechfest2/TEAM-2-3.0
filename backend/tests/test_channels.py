"""USSD and SMS access. All results are generated TEST DATA for the fictional demo register;
no shortcode or telecom provider is involved."""

import json
from collections.abc import Iterator

import pytest
from sqlalchemy import func, inspect, select, text

from app.analytics.registry import registry_for
from app.channels import security
from app.channels import sms as sms_module
from app.channels.sms import parse
from app.channels.text import SMS_MAX_CHARS, USSD_MAX_CHARS, paginate, sms_parts
from app.core.config import get_settings
from app.db.models import SmsMessage
from tests.evidence_support import actor
from tests.platform_support import CHANNEL_ELECTION, DIRECTORY, Platform, unit_by_code

PU = "FC1-A1"
PU_UNIT = unit_by_code(PU)
_REG = registry_for(DIRECTORY, CHANNEL_ELECTION)
WARD_CODE = _REG.wards[PU_UNIT.ward.id].code
LGA_CODE = _REG.lgas[PU_UNIT.lga.id].code
LGA_NAME = _REG.lgas[PU_UNIT.lga.id].name
STATE_CODE = _REG.states[PU_UNIT.state.id].code
SECRET = "test-gateway-secret-" + "x" * 24

@pytest.fixture()
def platform(tmp_path) -> Iterator[Platform]:
    p = Platform(tmp_path)
    with p.client:
        yield p
    get_settings.cache_clear()

@pytest.fixture()
def gateway_mode(monkeypatch):
    """Simulator off, gateway secrets configured: callbacks must be signed."""
    monkeypatch.setenv("CHANNEL_SIMULATOR_ENABLED", "false")
    monkeypatch.setenv("SMS_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("USSD_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("CHANNEL_HASH_SECRET", "hash-secret-" + "y" * 30)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

def dial(p: Platform) -> dict:
    response = p.client.post("/api/v1/ussd/sessions", json={"phone_number": "08030000000"})
    assert response.status_code == 201, response.text
    return response.json()

def send(p: Platform, session_id: str, value: str) -> dict:
    response = p.client.post(f"/api/v1/ussd/sessions/{session_id}/input", json={"input": value})
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["text"]) <= USSD_MAX_CHARS
    return body

def sms(p: Platform, message: str, sender: str = "+2348030000001", message_id: str | None = None):
    payload = {"from": sender, "text": message}
    if message_id:
        payload["message_id"] = message_id
    response = p.client.post("/api/v1/sms/incoming", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert all(len(part) <= SMS_MAX_CHARS for part in body["parts"])
    return body

def figure(lines: str, label: str) -> int:
    line = next(row for row in lines.split("\n") if row.startswith(label))
    return int(line.split(":")[1].split("(")[0].strip().replace(",", ""))

def test_pagination_and_sms_parts_respect_length_limits():
    lines = [f"Line {i} " + "x" * 50 for i in range(10)]
    pages = paginate(lines, 120)
    assert all(len(page) <= 120 for page in pages) and len(pages) > 1
    parts = sms_parts(lines)
    assert parts[0].startswith("(1/") and all(len(p) <= SMS_MAX_CHARS for p in parts)

def test_sms_parser_validates_commands_and_codes():
    assert parse("result fc1-a1").argument == "FC1-A1"
    assert parse("RESULT").error
    assert parse("RESULT a b").error
    assert parse("RESULT <script>").error == "That code is not valid."
    assert parse("NATIONAL now").error
    assert parse("VOTE APC").command == "UNKNOWN"
    assert parse("   ").command == "EMPTY"

def test_phone_numbers_are_normalised_and_hashed():
    settings = get_settings()
    assert security.normalise_phone("0803 000 0001") == "+2348030000001"
    assert security.hash_phone(settings, "08030000001") == security.hash_phone(
        settings, "+2348030000001"
    )
    assert "8030000001" not in security.hash_phone(settings, "08030000001")

def test_ussd_main_menu_and_area_navigation(platform):
    start = dial(platform)
    assert start["text"].startswith("Welcome to VoteTrace")
    assert "6. Election Updates" in start["text"] and start["end"] is False
    assert start["demo_label"] and "shortcode" in start["notice"]

    sid = start["session_id"]
    prompt = send(platform, sid, "3")
    assert prompt["text"].startswith("Enter LGA code")
    lga = send(platform, sid, LGA_CODE.lower())
    assert LGA_NAME in lga["text"]
    assert "Expected PUs:" in lga["text"]
    assert send(platform, sid, "0")["text"].startswith("Welcome")
    national = send(platform, sid, "5")
    assert "Expected PUs:" in national["text"]
    assert "Incomplete" in national["text"] or "98. More" in national["text"]
    goodbye = send(platform, sid, "00")
    assert goodbye["text"].startswith("Welcome")
    end = send(platform, sid, "0")
    assert end["end"] is True
    gone = platform.client.post(f"/api/v1/ussd/sessions/{sid}/input", json={"input": "1"})
    assert gone.status_code == 404

def test_ussd_results_paginate_with_more(platform):
    sid = dial(platform)["session_id"]
    send(platform, sid, "1")
    first = send(platform, sid, PU)
    assert PU in first["text"] and "98. More" in first["text"]
    pages = [first["text"]]
    while "98. More" in pages[-1]:
        pages.append(send(platform, sid, "98")["text"])
    joined = "\n".join(pages)
    assert "Incomplete" in joined and "Not INEC results." in joined
    assert "Sample data" in joined

def test_ussd_invalid_inputs_are_explained_then_end_the_session(platform):
    sid = dial(platform)["session_id"]
    assert send(platform, sid, "9")["text"].startswith("Invalid choice.")
    send(platform, sid, "1")
    unknown = send(platform, sid, "DEMO-99-99-99-999")
    assert "not found" in unknown["text"] and unknown["end"] is False
    final = send(platform, sid, "<>")
    assert final["end"] is True and "Too many invalid" in final["text"]
    too_long = platform.client.post(
        f"/api/v1/ussd/sessions/{dial(platform)['session_id']}/input", json={"input": "1" * 41}
    )
    assert too_long.status_code == 422

def test_ussd_sessions_time_out(platform):
    sid = dial(platform)["session_id"]
    platform.app.state.ussd_sessions.get(sid).last_seen -= 10_000
    reply = send(platform, sid, "5")
    assert reply["end"] is True and reply["timed_out"] is True
    assert "timed out" in reply["text"]

def test_ussd_election_updates_list_and_detail(platform):
    sid = dial(platform)["session_id"]
    listing = send(platform, sid, "6")
    assert listing["text"].startswith("Election updates")
    detail = send(platform, sid, "1")
    assert "Source:" in detail["text"] or "98. More" in detail["text"]
    back = send(platform, sid, "0")
    assert back["text"].startswith("Election updates")

def test_ussd_gateway_signs_and_replays_lost_sessions(platform, gateway_mode):
    def call(form: str, signature: str | None):
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if signature:
            headers[security.SIGNATURE_HEADER] = signature
        return platform.client.post("/api/v1/ussd/gateway", content=form, headers=headers)

    base = "sessionId=ATX1&phoneNumber=%2B2348030000002&serviceCode=SIMULATED"
    assert call(base + "&text=", None).status_code == 401
    assert call(base + "&text=", "sha256=" + "0" * 64).status_code == 401
    opened = call(base + "&text=", security.sign(SECRET, (base + "&text=").encode()))
    assert opened.status_code == 200 and opened.text.startswith("CON Welcome")

    platform.app.state.ussd_sessions.delete("gw:ATX1")
    replay = base + f"&text=3*{LGA_CODE}"
    reply = call(replay, security.sign(SECRET, replay.encode()))
    assert reply.text.startswith("CON ") and LGA_NAME in reply.text

    simulator = platform.client.post("/api/v1/ussd/sessions", json={})
    assert simulator.status_code == 404

def test_sms_commands_answer_from_the_shared_service(platform):
    help_reply = sms(platform, "help")
    assert help_reply["outcome"] == "ok" and "RESULT <PU code>" in " ".join(help_reply["parts"])
    result = sms(platform, f"RESULT {PU}")
    assert result["command"] == "RESULT" and result["outcome"] == "ok"
    assert PU in result["parts"][0]
    status = sms(platform, f"status {PU}")
    assert "Location:" in " ".join(status["parts"])
    for command, code in (
        ("WARD", WARD_CODE),
        ("LGA", LGA_CODE),
        ("STATE", STATE_CODE),
    ):
        reply = sms(platform, f"{command} {code}")
        assert reply["outcome"] == "ok" and "Expected PUs" in " ".join(reply["parts"])
    assert sms(platform, "NATIONAL")["outcome"] == "ok"
    assert sms(platform, "UPDATES")["outcome"] == "ok"
    assert result["message_ref"].startswith("SMS-")

def test_sms_unknown_codes_and_commands_are_handled(platform):
    unknown_pu = sms(platform, "RESULT DEMO-99-99-99-999")
    assert unknown_pu["outcome"] == "unknown_location"
    assert "No polling unit found" in unknown_pu["parts"][0]
    assert sms(platform, "VOTE NOW")["outcome"] == "invalid"
    assert sms(platform, "RESULT")["outcome"] == "invalid"
    assert sms(platform, "MORE")["parts"][0].startswith("Nothing more")

def test_sms_long_replies_continue_with_more(platform, monkeypatch):
    monkeypatch.setattr(sms_module, "PARTS_PER_REPLY", 1)
    first = sms(platform, f"RESULT {PU}", sender="+2348030000009")
    assert first["has_more"] is True and len(first["parts"]) == 1
    assert first["parts"][-1].endswith("Reply MORE")
    more = sms(platform, "MORE", sender="+2348030000009")
    assert more["outcome"] == "ok" and more["parts"][0].startswith("(2/")
    assert sms(platform, "MORE", sender="+2348030000010")["outcome"] == "invalid"

def test_sms_duplicate_message_ids_are_answered_once(platform):
    first = sms(platform, "NATIONAL", message_id="prov-123")
    again = sms(platform, "NATIONAL", message_id="prov-123")
    assert again["duplicate"] is True and again["message_ref"] == first["message_ref"]
    with platform.factory() as db:
        assert db.scalar(select(func.count()).select_from(SmsMessage)) == 1

def test_sms_senders_are_rate_limited(platform, monkeypatch):
    monkeypatch.setenv("SMS_MESSAGES_PER_WINDOW", "2")
    get_settings.cache_clear()
    platform.app.state.sms_limiter = None
    outcomes = [sms(platform, "HELP", sender="+2348031111111")["outcome"] for _ in range(3)]
    assert outcomes == ["ok", "ok", "rate_limited"]
    assert sms(platform, "HELP", sender="+2348032222222")["outcome"] == "ok"

def test_sms_log_keeps_no_phone_number_and_lookup_is_restricted(platform, monkeypatch):
    reply = sms(platform, "HELP", sender="+2348035555555")
    with platform.factory() as db:
        row = db.scalar(select(SmsMessage))
        assert "8035555555" not in json.dumps(
            {c: str(getattr(row, c)) for c in row.__table__.columns.keys()}
        )
    lookup = platform.client.get(f"/api/v1/sms/messages/{reply['message_ref']}")
    assert lookup.status_code == 200 and "sender" not in lookup.json()

    monkeypatch.setenv("CHANNEL_SIMULATOR_ENABLED", "false")
    get_settings.cache_clear()
    path = f"/api/v1/sms/messages/{reply['message_ref']}"
    assert platform.client.get(path).status_code == 403
    assert platform.client.get(path, headers=actor("observer").headers).status_code == 403
    assert platform.client.get(path, headers=actor("auditor").headers).status_code == 200

def test_sms_gateway_requires_a_valid_signature(platform, gateway_mode):
    body = json.dumps({"from": "+2348030000003", "text": "HELP", "message_id": "gw-1"}).encode()
    headers = {"Content-Type": "application/json"}
    assert (
        platform.client.post("/api/v1/sms/incoming", content=body, headers=headers).status_code
        == 401
    )
    forged = {**headers, security.SIGNATURE_HEADER: security.sign("wrong-secret-" + "z" * 30, body)}
    assert (
        platform.client.post("/api/v1/sms/incoming", content=body, headers=forged).status_code
        == 401
    )
    signed = {**headers, security.SIGNATURE_HEADER: security.sign(SECRET, body)}
    ok = platform.client.post("/api/v1/sms/incoming", content=body, headers=signed)
    assert ok.status_code == 200 and ok.json()["provider"] == "gateway"

def test_ussd_and_sms_figures_match_the_dashboard(platform):
    assert CHANNEL_ELECTION.election_label == "PRESIDENTIAL"
    ward_units = [u.code for u in (unit_by_code(PU),)]
    platform.seed_results(verified=ward_units, reported=["FC1-A2"])

    national = platform.client.get(
        "/api/v1/analytics/national", params={"election_id": str(CHANNEL_ELECTION.id)}
    ).json()["summary"]["coverage"]
    sms_text = "\n".join(
        line.split(") ", 1)[-1] if line.startswith("(") else line
        for line in sms(platform, "NATIONAL")["parts"]
    )
    assert figure(sms_text, "Reporting") == national["reporting_polling_units"] == 2
    assert figure(sms_text, "Verified") == national["verified_polling_units"] == 1

    sid = dial(platform)["session_id"]
    send(platform, sid, "4")
    state_screen = send(platform, sid, STATE_CODE)["text"]
    state = platform.client.get(
        f"/api/v1/analytics/states/{PU_UNIT.state.id}",
        params={"election_id": str(CHANNEL_ELECTION.id)},
    ).json()["summary"]["coverage"]
    assert figure(state_screen, "Expected PUs") == state["expected_polling_units"]
    assert figure(state_screen, "Reporting") == state["reporting_polling_units"]

    unit = " ".join(sms(platform, f"RESULT {PU}")["parts"])
    assert "Verified by VoteTrace reviewers" in unit
    reported = " ".join(sms(platform, "RESULT FC1-A2")["parts"])
    assert "Reported, not yet verified" in reported

def test_public_channels_never_modify_electoral_records(platform):
    platform.seed_results(verified=[PU], reported=[])
    engine = platform.factory.kw["bind"]

    def counts() -> dict[str, int]:
        with engine.connect() as conn:
            return {
                name: conn.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar_one()
                for name in inspect(engine).get_table_names()
            }

    before = counts()
    sid = dial(platform)["session_id"]
    for value in ("1", PU, "98", "0", "5", "0", "6", "1", "0"):
        send(platform, sid, value)
    for message in (f"RESULT {PU}", f"STATUS {PU}", "NATIONAL", "UPDATES", "VERIFY ALL", "MORE"):
        sms(platform, message)
    after = counts()
    changed = {name for name in before if before[name] != after[name]}
    assert changed == {"sms_messages"}

TOKEN = "callback-token-" + "t" * 30

@pytest.fixture()
def africastalking_mode(monkeypatch):
    """Simulator off; Africa's Talking authenticates with the callback token in the URL."""
    monkeypatch.setenv("CHANNEL_SIMULATOR_ENABLED", "false")
    monkeypatch.setenv("CHANNEL_CALLBACK_TOKEN", TOKEN)
    monkeypatch.setenv("CHANNEL_HASH_SECRET", "hash-secret-" + "y" * 30)
    monkeypatch.setenv("AFRICASTALKING_USERNAME", "sandbox")
    monkeypatch.setenv("AFRICASTALKING_API_KEY", "at-test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

def test_africastalking_ussd_needs_the_callback_token(platform, africastalking_mode):
    form = "sessionId=AT123&phoneNumber=%2B2348030000004&serviceCode=%2A384%2A1%23&text="
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    url = "/api/v1/ussd/gateway"
    assert platform.client.post(url, content=form, headers=headers).status_code == 401
    assert (
        platform.client.post(f"{url}?token=wrong", content=form, headers=headers).status_code == 401
    )
    opened = platform.client.post(f"{url}?token={TOKEN}", content=form, headers=headers)
    assert opened.status_code == 200 and opened.text.startswith("CON Welcome")
    step = form.replace("text=", "text=5")
    national = platform.client.post(f"{url}?token={TOKEN}", content=step, headers=headers)
    assert national.status_code == 200 and national.text.startswith(("CON ", "END "))

def test_africastalking_sms_replies_through_the_messaging_api(
    platform, africastalking_mode, monkeypatch
):
    import httpx

    from app.channels import africastalking

    sent: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["apiKey"] == "at-test-key"
        assert str(request.url) == africastalking.ENDPOINTS["sandbox"]
        sent.append(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(201, json={"SMSMessageData": {"Recipients": [{"status": "Success"}]}})

    real_client = httpx.Client
    monkeypatch.setattr(
        africastalking.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler)),
    )
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    form = "from=%2B2348030000005&to=12345&text=HELP&id=ATXid_1&linkId=link-1&date=2026-11-19"
    url = "/api/v1/sms/africastalking"
    assert platform.client.post(url, content=form, headers=headers).status_code == 401
    ok = platform.client.post(f"{url}?token={TOKEN}", content=form, headers=headers)
    assert ok.status_code == 200 and ok.text == "OK"
    assert sent and sent[0]["to"] == "+2348030000005" and sent[0]["username"] == "sandbox"
    assert sent[0]["linkId"] == "link-1" and "RESULT" in sent[0]["message"]

    count = len(sent)
    again = platform.client.post(f"{url}?token={TOKEN}", content=form, headers=headers)
    assert again.status_code == 200 and len(sent) == count

    with platform.factory() as db:
        row = db.scalar(select(SmsMessage).where(SmsMessage.provider_message_id == "ATXid_1"))
        assert row is not None and row.provider == "africastalking"
        assert "2348030000005" not in json.dumps(row.response_parts) + row.sender_hash
