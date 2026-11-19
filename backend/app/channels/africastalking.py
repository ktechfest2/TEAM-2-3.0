"""Africa's Talking: outbound SMS delivery and the inbound SMS callback format.

Credentials come only from the environment (AFRICASTALKING_USERNAME and
AFRICASTALKING_API_KEY). The sandbox environment is free and works with Africa's
Talking's web simulator; "live" sends real messages to real phones and is billed."""

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass

import httpx

from app.core.config import Settings
from app.core.errors import AppError

logger = logging.getLogger("verivote.channels")

ENDPOINTS = {
    "sandbox": "https://api.sandbox.africastalking.com/version1/messaging",
    "live": "https://api.africastalking.com/version1/messaging",
}
PROVIDER = "africastalking"


@dataclass(frozen=True)
class InboundSms:
    sender: str
    text: str
    message_id: str | None
    link_id: str | None


def parse_inbound(form: Mapping[str, str]) -> InboundSms:
    """Africa's Talking posts form fields: from, to, text, date, id, linkId."""
    sender = (form.get("from") or "").strip()
    text = form.get("text") or ""
    message_id = (form.get("id") or "").strip() or None
    link_id = (form.get("linkId") or "").strip() or None
    if not sender:
        raise AppError("invalid_gateway_payload", "The SMS callback has no sender.", 422)
    if len(text) > 480:
        raise AppError("invalid_gateway_payload", "The SMS text is too long.", 422)
    if message_id and not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", message_id):
        raise AppError("invalid_gateway_payload", "The SMS message id is invalid.", 422)
    if link_id and len(link_id) > 200:
        raise AppError("invalid_gateway_payload", "The SMS link id is invalid.", 422)
    return InboundSms(sender, text, message_id, link_id)


def is_configured(settings: Settings) -> bool:
    return bool(settings.africastalking_username and settings.africastalking_api_key)


class AfricasTalkingSms:
    """Sends reply parts as separate messages, in order."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if not is_configured(settings):
            raise AppError(
                "channel_unavailable", "Africa's Talking credentials are not configured.", 503
            )
        assert settings.africastalking_api_key is not None
        self._username = settings.africastalking_username or ""
        self._key = settings.africastalking_api_key.get_secret_value()
        self._sender = settings.africastalking_sender_id
        self._url = ENDPOINTS[settings.africastalking_environment]
        self._client = client or httpx.Client(timeout=10.0)

    def send(self, phone_number: str, parts: list[str], link_id: str | None = None) -> int:
        """Returns how many parts the provider accepted. Never logs the number or text."""
        accepted = 0
        for part in parts:
            data = {"username": self._username, "to": phone_number, "message": part}
            if self._sender:
                data["from"] = self._sender
            if link_id:
                data["linkId"] = link_id
                data["bulkSMSMode"] = "0"
            try:
                response = self._client.post(
                    self._url,
                    data=data,
                    headers={"apiKey": self._key, "Accept": "application/json"},
                )
            except httpx.HTTPError:
                logger.warning("africastalking sms send failed: network error")
                break
            if response.status_code >= 400:
                logger.warning("africastalking sms send failed: status=%s", response.status_code)
                break
            recipients = (
                response.json().get("SMSMessageData", {}).get("Recipients", [])
                if response.headers.get("content-type", "").startswith("application/json")
                else []
            )
            if not any(r.get("status") == "Success" for r in recipients):
                logger.warning("africastalking sms send rejected")
                break
            accepted += 1
        return accepted
