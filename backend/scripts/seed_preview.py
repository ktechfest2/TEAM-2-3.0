"""Fill a separate preview API with sample activity, through the public HTTP endpoints.

Run it only against a preview instance started with DIRECTORY_SOURCE=demo and its own
DEV_DATABASE_PATH (see scripts/preview.sh). It refuses to touch a non-demo election.

What it does, as real users would:
  * the system admin creates sample accounts (observer, party agent, reviewer, auditor,
    election admin);
  * the observer and party agent photograph result sheets: the script renders readable
    sheet images, uploads them through POST /evidence and runs OCR through /process;
  * people file incident reports through POST /incidents.

Nothing is written straight to the database, so every record carries its normal audit trail.

    python scripts/seed_preview.py --api http://127.0.0.1:8001/api/v1 \
        --admin-email admin@verivote.ng --admin-password '...'
"""

from __future__ import annotations

import argparse
import io
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

SAMPLE_PASSWORD = "Preview-Sample-2026"
SAMPLE_ACCOUNTS = [
    ("observer@preview.verivote.ng", "Sample Observer", ["observer"]),
    ("agent@preview.verivote.ng", "Sample Party Agent", ["party_agent"]),
    ("reviewer@preview.verivote.ng", "Sample Reviewer", ["reviewer"]),
    ("auditor@preview.verivote.ng", "Sample Auditor", ["auditor"]),
    ("elections@preview.verivote.ng", "Sample Election Admin", ["election_admin"]),
]
FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

@dataclass
class Sheet:
    registered: int
    accredited: int
    rejected: int
    party_votes: dict[str, int]
    # Deliberately wrong total, to show the arithmetic check flagging a sheet.
    valid_override: int | None = None

    @property
    def valid(self) -> int:
        return (
            self.valid_override
            if self.valid_override is not None
            else sum(self.party_votes.values())
        )

    @property
    def cast(self) -> int:
        return sum(self.party_votes.values()) + self.rejected

def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)

def render_sheet(code: str, label: str, sheet: Sheet) -> bytes:
    """A plain, legible sheet laid out like the generic template. Not an INEC form."""
    image = Image.new("RGB", (1400, 1500), "white")
    draw = ImageDraw.Draw(image)
    title, body = _font(44), _font(40)
    draw.text((80, 60), "POLLING UNIT RESULT SHEET", fill="black", font=title)
    draw.text((80, 120), "SAMPLE FOR PREVIEW ONLY", fill="black", font=_font(28))
    rows = [
        f"Election: {label}",
        f"Polling unit code: {code}",
        f"Voters on the register: {sheet.registered}",
        f"Accredited voters: {sheet.accredited}",
    ]
    rows += [f"{party}      {votes}" for party, votes in sheet.party_votes.items()]
    rows += [
        f"Total valid votes: {sheet.valid}",
        f"Rejected votes: {sheet.rejected}",
        f"Total votes cast: {sheet.cast}",
    ]
    y = 220
    for row in rows:
        draw.text((80, y), row, fill="black", font=body)
        y += 100
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()

def _check(response: httpx.Response, what: str) -> dict:
    if response.status_code >= 400:
        sys.exit(f"{what} failed ({response.status_code}): {response.text[:400]}")
    return response.json()

def sign_in(client: httpx.Client, email: str, password: str) -> dict[str, str]:
    body = _check(client.post("/auth/login", json={"email": email, "password": password}), email)
    return {"Authorization": f"Bearer {body['access_token']}"}

def ensure_accounts(client: httpx.Client, admin: dict[str, str]) -> None:
    existing = {a["email"] for a in _check(client.get("/admin/users", headers=admin), "users")}
    for email, name, roles in SAMPLE_ACCOUNTS:
        if email in existing:
            print(f"  account exists: {email}")
            continue
        _check(
            client.post(
                "/admin/users",
                headers=admin,
                json={
                    "email": email,
                    "display_name": name,
                    "roles": roles,
                    "password": SAMPLE_PASSWORD,
                },
            ),
            f"create {email}",
        )
        print(f"  created {roles[0]}: {email}")

def upload_sheet(
    client: httpx.Client,
    headers: dict[str, str],
    election: dict,
    unit: dict,
    sheet: Sheet,
    minutes_ago: int,
) -> None:
    image = render_sheet(unit["code"], election["election_label"], sheet)
    captured = (datetime.now(UTC) - timedelta(minutes=minutes_ago)).replace(microsecond=0)
    receipt = _check(
        client.post(
            "/evidence",
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            data={
                "election_id": election["id"],
                "polling_unit_id": unit["id"],
                "captured_at": captured.isoformat(),
                "capture_source": "camera",
            },
            files={"file": (f"{unit['code'].replace('/', '-')}.png", image, "image/png")},
        ),
        f"upload for {unit['code']}",
    )
    submission_id = receipt["item"]["id"]
    extraction = _check(
        client.post(f"/evidence/{submission_id}/process", headers=headers, timeout=180),
        f"OCR for {unit['code']}",
    )
    fields = extraction.get("fields", [])
    read = [f for f in fields if f.get("value") not in (None, "")]
    print(
        f"  {unit['code']}: uploaded, OCR read {len(read)}/{len(fields)} fields"
        f" (provider {extraction.get('provider', '?')})"
    )

INCIDENTS = [
    ("delayed_officials", "Polling officials had not arrived by 9:30am and voters were waiting."),
    ("voting_disruption", "The card reader stopped working for about forty minutes before noon."),
    ("accessibility", "There was no ramp, and elderly voters struggled to reach the voting point."),
    ("vote_buying", "People near the queue were seen offering small items to voters. Unconfirmed."),
    (
        "misinformation",
        "A message circulating says this unit moved, but it is still at the school.",
    ),
    ("intimidation", "A group was shouting at voters near the entrance; security was called."),
]

def file_incidents(
    client: httpx.Client, headers: dict[str, str], election: dict, units: list[dict]
) -> None:
    for index, (category, description) in enumerate(INCIDENTS):
        unit = units[index % len(units)]
        occurred = (datetime.now(UTC) - timedelta(hours=index + 1)).replace(microsecond=0)
        receipt = _check(
            client.post(
                "/incidents",
                headers={
                    **(headers if index % 2 == 0 else {}),
                    "Idempotency-Key": str(uuid.uuid4()),
                },
                data={
                    "election_id": election["id"],
                    "category": category,
                    "description": description,
                    "state_id": unit["state"]["id"],
                    "lga_id": unit["lga"]["id"],
                    "ward_id": unit["ward"]["id"],
                    "polling_unit_id": unit["id"],
                    "occurred_at": occurred.isoformat(),
                    "time_is_approximate": "true",
                    "protect_identity": "true" if index % 3 == 0 else "false",
                },
            ),
            f"incident {category}",
        )
        print(f"  {category}: {receipt.get('reference', receipt.get('item', {}).get('id'))}")

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", default="http://127.0.0.1:8001/api/v1")
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-password", required=True)
    args = parser.parse_args()

    with httpx.Client(base_url=args.api, timeout=60) as client:
        elections = _check(client.get("/elections"), "elections")["items"]
        election = next((e for e in elections if e["election_label"] == "PRESIDENTIAL"), None)
        if election is None or not election.get("is_demo"):
            sys.exit("Refusing to seed: this API is not serving the demo directory.")
        print(f"Preview election: {election['name']}")

        admin = sign_in(client, args.admin_email, args.admin_password)
        print("Accounts")
        ensure_accounts(client, admin)

        observer = sign_in(client, SAMPLE_ACCOUNTS[0][0], SAMPLE_PASSWORD)
        agent = sign_in(client, SAMPLE_ACCOUNTS[1][0], SAMPLE_PASSWORD)

        page = _check(
            client.get(
                "/analytics/polling-units",
                params={"election_id": election["id"], "status": "not_reporting"},
            ),
            "not reporting units",
        )
        units = page["items"]
        if len(units) < 3:
            print("Fewer than 3 units are still waiting for results; skipping sheet uploads.")
        else:
            print("Result sheets (uploaded and read by OCR)")
            parties = [p["code"] for p in election["parties"]]
            sheets = [
                Sheet(720, 412, 9, dict(zip(parties, [168, 131, 74, 30], strict=True))),
                Sheet(655, 380, 6, dict(zip(parties, [97, 154, 88, 35], strict=True))),
                Sheet(810, 503, 12, dict(zip(parties, [201, 143, 97, 50], strict=True)), 520),
            ]
            for index, sheet in enumerate(sheets):
                upload_sheet(client, observer, election, units[index], sheet, 90 - index * 20)
            # A second, independent photo of the first sheet from a party agent.
            upload_sheet(client, agent, election, units[0], sheets[0], 25)

        print("Incident reports")
        file_incidents(client, observer, election, units or page["items"])
        print(f"\nSample accounts share the password {SAMPLE_PASSWORD!r}.")

if __name__ == "__main__":
    main()
