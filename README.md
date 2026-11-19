<div align="center">

<img src="frontend/public/favicon.svg" alt="VoteTrace logo" width="96" height="96" />

# VoteTrace

### Every Vote, Every Voice.

**Offline-first evidence capture and independent verification of polling-unit results in Nigeria.**

A result sheet photographed at a polling unit becomes a fingerprinted, OCR-read, arithmetic-checked, cross-compared and human-reviewed record. It then rolls up from Polling Unit to Ward, LGA, State and National, and anyone can check it on the web, by USSD or by SMS.

![React 19](https://img.shields.io/badge/React-19-149eca?logo=react&logoColor=white)
![TypeScript 6](https://img.shields.io/badge/TypeScript-6-3178c6?logo=typescript&logoColor=white)
![Vite 8](https://img.shields.io/badge/Vite-8-646cff?logo=vite&logoColor=white)
![Tailwind 4](https://img.shields.io/badge/Tailwind_CSS-4-38bdf8?logo=tailwindcss&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)
![Python 3.12](https://img.shields.io/badge/Python-3.12-3776ab?logo=python&logoColor=white)
![PostgreSQL + PostGIS](https://img.shields.io/badge/PostgreSQL-PostGIS-336791?logo=postgresql&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-hosted_Postgres-3ecf8e?logo=supabase&logoColor=white)
![PWA](https://img.shields.io/badge/PWA-offline_first-5a0fc8?logo=pwa&logoColor=white)
![Tests](https://img.shields.io/badge/tests-~300-3bb75e)

[Problem](#the-problem) ·
[Solution](#what-votetrace-does) ·
[Architecture](#system-architecture) ·
[AI](#ai-in-votetrace) ·
[Stack](#technology-stack) ·
[Quick start](#quick-start) ·
[API](#api-overview) ·
[Roadmap](#honest-scope-and-roadmap)

</div>

---

## Contents

1. [The problem](#the-problem)
2. [What VoteTrace does](#what-votetrace-does)
3. [Screenshots](#screenshots)
4. [How VoteTrace fits into Nigeria's election process](#how-votetrace-fits-into-nigerias-election-process)
5. [System architecture](#system-architecture)
6. [Evidence pipeline and state machine](#evidence-pipeline-and-state-machine)
7. [Offline-first capture](#offline-first-capture)
8. [Results aggregation](#results-aggregation)
9. [USSD and SMS access](#ussd-and-sms-access)
10. [AI in VoteTrace](#ai-in-votetrace)
11. [Roles and permissions](#roles-and-permissions)
12. [Data model](#data-model)
13. [Security and privacy](#security-and-privacy)
14. [Accessibility, languages and mobile](#accessibility-languages-and-mobile)
15. [Technology stack](#technology-stack)
16. [Quick start](#quick-start)
17. [API overview](#api-overview)
18. [Project structure](#project-structure)
19. [Testing and quality](#testing-and-quality)
20. [Deploy](#deploy-on-vercel-and-render)
21. [Honest scope and roadmap](#honest-scope-and-roadmap)
22. [Disclaimer](#disclaimer)

---

## The problem

Nigeria has more than 176,000 polling units. At each one, results are written on a paper result sheet (Form EC8A) and then collated upward through wards, LGAs and states. Citizens, observers and party agents routinely see that sheet, but they have few practical ways to:

- **preserve** what they saw in a form that cannot be quietly altered later,
- **check** that the figures on a sheet add up and match what other people photographed,
- **follow** a polling-unit figure as it moves up to the ward, LGA, state and national totals,
- **take part** at all when they have a basic phone, no data plan, or no signal at the polling unit.

Most tools that try to help either publish unverified crowd figures or rely on opaque "AI" that claims to detect fraud. Both erode trust.

## What VoteTrace does

VoteTrace is an independent civic check built on four principles:

| Principle | How it shows up in the product |
| --- | --- |
| **Evidence first** | Every figure traces back to a photographed sheet with a SHA-256 fingerprint and a hash-chained audit trail. |
| **Humans decide** | Software reads, checks and flags. Only people verify, and `verified` needs two different reviewers. Nobody can review their own submission. |
| **Honest status** | Reported, verified, conflicting and rejected figures are always kept apart. Conflicts are excluded from totals, and coverage is shown, never a winner. |
| **Reach everyone** | The app works offline as a PWA, and the same results are available over USSD and SMS for basic phones. |

### Feature highlights

- 📸 **Result-sheet capture** with camera or file upload, browser-side checks, HEIC-to-JPEG conversion, SHA-256 hashing and an offline upload queue with idempotency keys.
- 🔎 **Evidence engine** with content-based file validation, OpenCV preprocessing, OCR with per-field confidence, versioned human corrections, deterministic arithmetic checks and cross-submission comparison.
- 🤖 **VoteTrace AI** that combines OCR uncertainty, discrepancy detection and a statistical Isolation Forest. It only routes records to human review and never declares fraud.
- ✅ **Two-person verification**, an append-only review history and a hash-chained audit log.
- 📊 **National results dashboard** that drills down from National to State, LGA, Ward and Polling Unit, with live updates over Server-Sent Events.
- 🗺️ **Polling-unit finder** with cascading State, LGA and Ward search, provenance, and an OpenStreetMap map.
- 📢 **Election updates** labelled as officially confirmed, independently verified, or reported and awaiting verification.
- 🚨 **Incident reporting** across nine categories. Reporters can stay anonymous, photo metadata is stripped, phone numbers and emails are masked, and reports queue offline.
- 📱 **USSD and SMS** access, read-only and served by the same aggregation engine as the dashboard, with a built-in simulator.
- 🛡️ **Administrative console** for staff accounts and roles, the audit log, register import, election configuration, update publishing and a live health card.
- 🌍 **Five languages**: English, Hausa, Igbo, Yoruba and Nigerian Pidgin.

## Screenshots

Phone screens from the seeded preview. All data is fictional and labelled as such.

<table>
  <tr>
    <td align="center"><img src="docs/images/screens/home.jpg" width="200" alt="Home screen with bottom tab bar" /><br /><sub>Home</sub></td>
    <td align="center"><img src="docs/images/screens/results.jpg" width="200" alt="National results dashboard" /><br /><sub>Results dashboard</sub></td>
    <td align="center"><img src="docs/images/screens/submit-evidence.jpg" width="200" alt="Submit a result sheet" /><br /><sub>Submit evidence</sub></td>
    <td align="center"><img src="docs/images/screens/phone-access.jpg" width="200" alt="USSD simulator" /><br /><sub>USSD simulator</sub></td>
    <td align="center"><img src="docs/images/screens/more-sheet.jpg" width="200" alt="More menu as a bottom sheet" /><br /><sub>More menu</sub></td>
  </tr>
</table>

## How VoteTrace fits into Nigeria's election process

VoteTrace runs **alongside** the official process, not inside it. INEC declares results. VoteTrace keeps an independent, evidence-backed record of what was posted at each polling unit.

![How VoteTrace fits into Nigeria's election process](docs/images/election-process.svg)

```mermaid
flowchart LR
    subgraph Official["Official INEC process"]
        direction LR
        V[Voting and counting] --> E[Form EC8A posted<br/>at the polling unit]
        E --> C[Ward, LGA and<br/>State collation]
        C --> D[Declaration by INEC]
    end

    subgraph VT["VoteTrace independent check"]
        direction LR
        P[Photograph the<br/>posted sheet] --> H[Fingerprint<br/>SHA-256]
        H --> O[OCR and<br/>arithmetic checks]
        O --> X[Cross-check and<br/>AI review routing]
        X --> R[Two human<br/>reviewers]
        R --> A[Open results<br/>web, USSD, SMS]
    end

    E -. "citizens, observers<br/>and party agents" .-> P
    A -. "compare with" .-> D
```

## System architecture

![VoteTrace system design architecture](docs/images/architecture.svg)

Both infographics are generated from code by [`scripts/build-diagrams.mjs`](scripts/build-diagrams.mjs) using the project's own logo and Lucide icons, so they stay in sync with the repository. Rebuild them with `node scripts/build-diagrams.mjs`.

```mermaid
flowchart TB
    subgraph Users["Users and channels"]
        CIT[Citizen]
        OBS[Observer / party agent]
        STF[Reviewer, auditor, admin]
        FP[Basic phone]
    end

    subgraph Client["React 19 PWA"]
        PUB[Public site<br/>finder, results, updates]
        CAP[Evidence capture<br/>camera, SHA-256, offline queue]
        ADM[Admin console<br/>review, audit, register]
        SW[Service worker<br/>Workbox precache]
        IDB[(IndexedDB<br/>Dexie)]
    end

    subgraph API["FastAPI /api/v1"]
        AUTH[Auth and roles<br/>JWT, scrypt]
        EVD[Evidence engine]
        AI[VoteTrace AI]
        VER[Verification workflow]
        AGG[Aggregation engine]
        INC[Incidents]
        INFO[InfoService<br/>read-only]
        CH[USSD and SMS handlers]
        SSE[SSE live updates]
    end

    subgraph Data["Data layer"]
        PG[(PostgreSQL + PostGIS<br/>Supabase)]
        FS[(Private evidence storage)]
        AUD[(Hash-chained audit log)]
    end

    AT[Africa's Talking gateway]
    OSM[OpenStreetMap tiles]

    CIT --> PUB
    OBS --> CAP
    STF --> ADM
    FP --> AT --> CH
    CAP <--> IDB
    PUB <--> IDB
    SW -.-> Client
    PUB --> AGG
    PUB --> OSM
    CAP --> EVD
    ADM --> VER
    ADM --> AUTH
    EVD --> AI --> VER
    VER --> AGG
    AGG --> SSE --> PUB
    CH --> INFO --> AGG
    EVD --> FS
    EVD & VER & INC & AUTH --> AUD
    AGG & INC & AUTH --> PG
```

### Request lifecycle

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser (PWA)
    participant A as FastAPI
    participant M as Middleware
    participant S as Service layer
    participant D as PostgreSQL

    B->>A: HTTPS request /api/v1/...
    A->>M: CORS, rate limit, security headers
    M->>M: Decode JWT, check require_roles
    M->>S: Validated Pydantic model
    S->>D: SQLAlchemy transaction
    D-->>S: Rows
    S->>D: Append audit event (hash chained)
    S-->>A: Response model
    A-->>B: JSON, or a structured error with a code
```

## Evidence pipeline and state machine

Each submission moves through explicit, audited states. These are VoteTrace workflow states, not INEC declaration statuses.

```mermaid
stateDiagram-v2
    [*] --> received: Upload accepted and hashed
    received --> processing: Preprocess and OCR
    processing --> extracted: Fields read with confidence
    extracted --> arithmetic_validated: Totals add up
    extracted --> flagged_for_review: Low confidence or arithmetic error
    arithmetic_validated --> cross_checked: Compared with other submissions
    cross_checked --> flagged_for_review: Disagreement or AI alert
    cross_checked --> under_human_review
    flagged_for_review --> under_human_review
    under_human_review --> reviewed: First approval
    reviewed --> verified: Second approval by a different reviewer
    under_human_review --> rejected
    reviewed --> rejected
    verified --> [*]
    rejected --> [*]
```

```mermaid
flowchart LR
    U[Upload] --> V1{Content-based<br/>file check}
    V1 -- invalid --> X[Reject with reason]
    V1 -- ok --> H[SHA-256 and<br/>private storage]
    H --> PRE[OpenCV preprocessing<br/>CLAHE, denoise,<br/>deskew, perspective]
    PRE --> OCR[OCR<br/>Tesseract or RapidOCR]
    OCR --> F[Field mapping and<br/>per-field confidence]
    F --> AR[Deterministic<br/>arithmetic rules]
    AR --> CMP[Cross-submission<br/>comparison]
    CMP --> AI[VoteTrace AI<br/>review routing]
    AI --> Q[Human review queue]
    Q --> R1[Reviewer 1] --> R2[Reviewer 2<br/>must differ] --> OK[Verified]
```

The arithmetic rules check that party votes add up to valid votes, that valid plus rejected votes equal votes cast, and that votes cast do not exceed accredited voters, who in turn do not exceed registered voters. A rule failure is a reason for review, never an automatic rejection.

## Offline-first capture

Polling units often have weak or no signal. Capture never depends on a live connection.

```mermaid
sequenceDiagram
    autonumber
    actor O as Observer
    participant UI as Submit page
    participant Q as IndexedDB queue (Dexie)
    participant SW as Service worker
    participant API as FastAPI
    participant E as Evidence engine

    O->>UI: Take photo of the result sheet
    UI->>UI: Sniff type, convert HEIC to JPEG, check size and dimensions
    UI->>UI: SHA-256 in the browser
    UI->>Q: Save with an idempotency key
    alt Online
        Q->>API: POST /evidence (multipart, key)
    else Offline
        Q-->>UI: Show "Saved, will upload"
        SW-->>Q: Connection restored
        Q->>API: Replay POST /evidence (same key)
    end
    API->>API: Recompute SHA-256, compare with the client hash
    API->>E: Store the original privately, start processing
    API-->>Q: 201 received (or the existing record if the key was seen)
    Q-->>UI: Show "Received by server" only after confirmation
```

The app shell is precached by Workbox, public data is cached in IndexedDB with its last-synced time, and refreshes are replayed on reconnect. Incident reports use the same queue.

## Results aggregation

```mermaid
flowchart BT
    PU1[Polling unit] --> W[Ward]
    PU2[Polling unit] --> W
    PU3[Polling unit] --> W
    W --> L[LGA]
    W2[Ward] --> L
    L --> S[State]
    L2[LGA] --> S
    S --> N[National]
    S2[State] --> N
```

- **Each polling unit counts at most once.** Duplicate submissions of the same sheet collapse to one result.
- **Conflicts are excluded.** When accepted submissions for a unit disagree, the unit is listed under *Unresolved discrepancies* and left out of both totals until reviewers resolve it.
- **Reported and verified are separate.** The dashboard shows reporting coverage and verification coverage side by side.
- **Incremental and transactional.** The derived `polling_unit_results` and `polling_unit_result_metrics` tables are refreshed in the same transaction as the review decision, and changes are pushed to browsers over Server-Sent Events at `/api/v1/analytics/updates`.

More detail is in [docs/results-aggregation.md](docs/results-aggregation.md).

## USSD and SMS access

Basic phones get the same figures as the dashboard through a read-only `InfoService`. The channels cannot write data.

```mermaid
flowchart TD
    D[Dial the USSD code] --> M["Welcome to VoteTrace<br/>1 Polling Unit Results<br/>2 Ward  3 LGA  4 State<br/>5 National  6 Election Updates<br/>0 Exit"]
    M -- "1-4" --> C[Enter a location code]
    C --> R[Result screen<br/>at most 182 characters]
    M -- "5" --> R
    M -- "6" --> U[Updates list<br/>3 per page]
    U --> UD[Update detail]
    R -- "98 more" --> R
    R -- "0 back" --> C
    R -- "00 menu" --> M
    U -- "00 menu" --> M
    M -- "0" --> G[Goodbye]
```

```mermaid
flowchart LR
    SMS[Incoming SMS] --> SIG{Gateway signature<br/>HMAC valid?}
    SIG -- no --> DROP[Reject]
    SIG -- yes --> RL{Rate limit and<br/>duplicate check}
    RL --> P[Parse command]
    P --> C1["RESULT / STATUS code"]
    P --> C2["WARD / LGA / STATE code"]
    P --> C3["NATIONAL"]
    P --> C4["UPDATES / HELP / MORE"]
    C1 & C2 & C3 & C4 --> I[InfoService<br/>read-only]
    I --> OUT[Reply in 160-character parts]
```

Phone numbers are stored only as hashes. Africa's Talking is supported through a built-in adapter, but no shortcode is allocated, so the channels are demonstrated through the simulator at `/phone-access`. To connect a real provider, see [docs/incidents-and-channels.md](docs/incidents-and-channels.md#connecting-a-real-provider-africas-talking).

## AI in VoteTrace

### AI inside the product

VoteTrace uses AI in a narrow, explainable way. **AI never declares fraud and never verifies a result.** It reads sheets and decides which records a human should look at first.

| Component | Technology | What it does | Safeguard |
| --- | --- | --- | --- |
| **Image preprocessing** | OpenCV (computer vision) | CLAHE contrast enhancement, denoising, deskewing and perspective correction so sheets photographed at an angle can be read | The original file is stored unchanged and re-verified against its SHA-256 hash |
| **OCR, primary** | Tesseract LSTM via `pytesseract` | Reads handwritten and printed figures from the sheet, field by field | Each field carries a confidence score, and low-confidence fields are marked for manual entry |
| **OCR, fallback** | RapidOCR, which runs PaddleOCR models on ONNX Runtime | Same job with no system binary, selected by `OCR_PROVIDER=auto\|tesseract\|rapidocr\|none` | With no engine available, evidence is still accepted and every field goes to manual entry |
| **OCR uncertainty** | Rule-based scoring (`evidence/ai/uncertainty.py`) | Turns low per-field confidence into a review alert | Alerts are labelled as uncertainty, not wrongdoing |
| **Discrepancy detection** | Deterministic comparison (`evidence/ai/discrepancy.py`) | Flags submissions for the same unit that disagree | Conflicting units are excluded from totals until resolved |
| **Statistical anomaly detection** | scikit-learn **Isolation Forest** (`evidence/ai/statistical.py`) | Unsupervised. It learns what is typical from human-reviewed records of the same election, using four ratios: turnout of accredited voters, rejected-vote share, leading-party share and accreditation of registered voters | 200 trees, a fixed random seed for reproducibility, and a refusal to run below `ANOMALY_MIN_SAMPLES` (default 30). A record is flagged only when its empirical p-value is at most 0.05 among all records scored with it. It is never trained on fabricated fraud labels. A reproducible DEMO / SYNTHETIC dataset exercises it (`python -m app.evidence.ai.anomaly_demo report`, or `scripts/anomaly-demo.sh` for the dashboard) |
| **Explainability** | Robust z-scores (median and MAD) | Says *which* ratio was unusual and by how much, in plain language | Every alert says "Human review is required. An alert is not a finding of wrongdoing." |

```mermaid
flowchart LR
    REC[Extracted record] --> U[OCR uncertainty]
    REC --> D[Discrepancy check]
    REC --> S[Isolation Forest<br/>if at least 30 reviewed records]
    S --> Z[Robust z-score<br/>explanation]
    U & D & Z --> AL[Anomaly alert<br/>with model version]
    AL --> HQ[Human review queue]
    HQ --> HUM{Two reviewers}
    HUM --> V[Verified]
    HUM --> RJ[Rejected]
```

Every alert stores the model name, model version (scikit-learn version plus feature version), the variables used and the number of reference records, so any decision can be reproduced and audited.

## Roles and permissions

| Capability | Citizen (public) | Observer | Party agent | Reviewer | Auditor | Election admin | System admin |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| View results, finder and updates | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Report an incident (anonymous allowed) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Use USSD and SMS | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Submit result-sheet evidence | | ✅ | ✅ | | | ✅ | ✅ |
| See own submissions | | ✅ | ✅ | | | ✅ | ✅ |
| Enter the admin console | | | | ✅ | ✅ | ✅ | ✅ |
| Review and verify evidence and incidents | | | | ✅ | | | |
| Read every submission and the audit log | | | | ✅ | ✅ | ✅ | ✅ |
| Import the register, configure elections, publish updates | | | | | | ✅ | ✅ |
| Manage staff accounts and roles | | | | | | | ✅ |

Roles are enforced on the server with `require_roles` on every route. The frontend mirrors them (`frontend/src/features/auth/roles.ts`) only to hide links people cannot use.

```mermaid
flowchart LR
    subgraph Field
        OBS[Observer] & AG[Party agent] -->|submit| EV[(Evidence)]
    end
    subgraph Console["Admin console"]
        RV[Reviewer] -->|approve or reject| EV
        AU[Auditor] -.->|read only| EV
        EA[Election admin] -->|register, elections, updates| CFG[(Configuration)]
        SA[System admin] -->|accounts and roles| ACC[(Users)]
    end
```

## Data model

26 tables managed by 6 Alembic migrations (`0001_initial_schema` to `0006_portable_directory`). A simplified view:

```mermaid
erDiagram
    STATES ||--o{ LGAS : contains
    LGAS ||--o{ WARDS : contains
    WARDS ||--o{ POLLING_UNITS : contains
    ELECTIONS ||--o{ EVIDENCE_SUBMISSIONS : for
    POLLING_UNITS ||--o{ EVIDENCE_SUBMISSIONS : about
    USERS ||--o{ EVIDENCE_SUBMISSIONS : submits
    USERS ||--o{ ROLE_ASSIGNMENTS : has
    EVIDENCE_SUBMISSIONS ||--|| EVIDENCE_IMAGES : stores
    EVIDENCE_SUBMISSIONS ||--o{ OCR_EXTRACTIONS : read_by
    OCR_EXTRACTIONS ||--o{ EXTRACTED_RESULT_RECORDS : versions
    EXTRACTED_RESULT_RECORDS ||--o{ EXTRACTED_RESULT_FIELDS : has
    EVIDENCE_SUBMISSIONS ||--o{ RESULT_VALIDATIONS : checked_by
    EVIDENCE_SUBMISSIONS ||--o{ SUBMISSION_COMPARISONS : compared_in
    EVIDENCE_SUBMISSIONS ||--o{ ANOMALY_ALERTS : flagged_by
    EVIDENCE_SUBMISSIONS ||--o{ EVIDENCE_REVIEWS : reviewed_in
    EVIDENCE_SUBMISSIONS ||--o| VERIFICATION_RECORDS : verified_as
    POLLING_UNITS ||--o{ POLLING_UNIT_RESULTS : aggregates
    POLLING_UNITS ||--o{ POLLING_UNIT_NOTICES : official
    POLLING_UNITS ||--o{ RELOCATION_REPORTS : crowd
    POLLING_UNITS ||--o{ INCIDENT_REPORTS : at
    INCIDENT_REPORTS ||--o{ INCIDENT_ATTACHMENTS : has
    INCIDENT_REPORTS ||--o{ INCIDENT_REVIEWS : reviewed_in
    USERS ||--o{ AUDIT_EVENTS : acts_in
```

Other tables: `elections`, `election_updates`, `polling_unit_result_metrics`, `sms_messages` and `user_credentials`. Full details are in [docs/data-model.md](docs/data-model.md) and [docs/database.md](docs/database.md).

## Security and privacy

| Area | Measure |
| --- | --- |
| Evidence integrity | SHA-256 in the browser and again on the server. Originals are stored privately and re-verified on read |
| Audit | Hash-chained, append-only audit events for evidence, reviews, incidents and accounts, with a chain viewer in the console |
| Review history | Append-only (migration `0002_append_only_history`). Two distinct reviewers are required, and self-review is blocked |
| Authentication | Built-in staff accounts, scrypt password hashing from the standard library, JWT sessions, forced password change after a temporary password |
| Authorisation | `require_roles` on every protected route, plus Postgres row-level security statements in [docs/security.md](docs/security.md) |
| Abuse protection | Per-client rate limiting (`RATE_LIMIT_PER_MINUTE`, default 120), idempotency keys, duplicate SMS protection |
| Gateways | HMAC-signed USSD and SMS callbacks |
| Personal data | Hashed phone numbers, masking of phone numbers and emails in incident text, photo metadata stripping, optional anonymity, and `--no-access-log` so client IPs are not kept |
| Transport and headers | Strict CORS, HSTS in production, interactive API docs disabled in production |
| Safe startup | A production process refuses to start without `DATABASE_URL`, `AUTH_JWT_SECRET` and `CORS_ORIGINS` |
| Secrets | `VITE_` variables are public. The database URL, JWT secret and service-role key are never exposed to the browser |

## Accessibility, languages and mobile

- **Mobile app feel.** A bottom tab bar (Home, Results, Find, Report, More), a bottom-sheet menu, and full-width touch targets on phones.
- **Languages.** English, Hausa, Igbo, Yoruba and Nigerian Pidgin, chosen to cover the widest audience. The choice is remembered on the device.
- **Accessible by default.** Skip link, semantic landmarks, labelled form controls, visible focus states, screen-reader-only labels where icons stand alone, and status shown with text as well as colour.
- **Low bandwidth.** The map loads only on demand, the app shell is precached, and USSD and SMS need no data at all.

## Technology stack

### Frontend

| Technology | Purpose |
| --- | --- |
| React 19 + TypeScript 6 | UI and type safety |
| Vite 8 | Dev server and production build |
| Tailwind CSS 4 | Styling and design tokens |
| TanStack Query 5 | Server state, caching and retries |
| React Router 8 | Routing and role-guarded areas |
| react-hook-form + zod 4 | Forms and validation |
| Radix UI (Dialog, Label, Slot) | Accessible primitives |
| class-variance-authority, clsx, tailwind-merge | Component variants |
| lucide-react | Icons |
| Leaflet + OpenStreetMap | Polling-unit maps |
| Dexie (IndexedDB) | Offline queue and cached data |
| vite-plugin-pwa + Workbox | Service worker and installable app |
| Supabase JS | Optional Supabase client integration |
| Inter (Fontsource) | Typography |

### Backend

| Technology | Purpose |
| --- | --- |
| FastAPI + Uvicorn | Versioned REST API, SSE and OpenAPI docs |
| Pydantic 2 + pydantic-settings | Validation and configuration |
| SQLAlchemy 2 + Alembic | ORM and 6 migrations |
| psycopg 3 + GeoAlchemy2 | PostgreSQL and PostGIS |
| PyJWT | Session tokens |
| hashlib scrypt | Password hashing |
| Pillow, NumPy, OpenCV (headless) | Image handling and preprocessing |
| pytesseract (Tesseract LSTM) | Primary OCR |
| RapidOCR on ONNX Runtime (optional) | Fallback OCR with PaddleOCR models |
| scikit-learn | Isolation Forest anomaly detection |
| httpx | Gateway calls and tests |

### Data and infrastructure

| Technology | Purpose |
| --- | --- |
| PostgreSQL + PostGIS on Supabase | Production database with row-level security |
| SQLite | Zero-setup development and preview database |
| Local private storage | Original evidence files (`backend/var/`) |
| Africa's Talking (adapter) | USSD and SMS gateway |

### Testing and tooling

| Tool | Purpose |
| --- | --- |
| pytest | About 197 backend tests |
| Vitest + Testing Library + jsdom + fake-indexeddb | Frontend unit and component tests |
| Playwright | End-to-end smoke tests against the production build |
| Ruff | Python linting |
| ESLint + typescript-eslint | TypeScript linting |
| Node script with Lucide icon data | Generated architecture infographics |
| `scripts/preview.sh` | One-command seeded preview |
## Quick start

### Prerequisites

- Node.js 20.19 or newer
- Python 3.12
- Optional: Tesseract (`brew install tesseract` or `apt-get install tesseract-ocr`)

### Fastest: the seeded preview

```bash
PREVIEW_ADMIN_PASSWORD='choose-a-password' scripts/preview.sh
```

This starts a separate API on port 8001 and the web app on <http://localhost:5174>, backed by a fictional demo directory and its own database under `backend/var/preview`, which is rebuilt on every run. It seeds results through the real evidence workflow, uploads rendered result sheets through the upload API so OCR runs on them, and files incident reports.

| Account | Role | Password |
| --- | --- | --- |
| `observer@preview.verivote.ng` | Observer | `Preview-Sample-2026` |
| `agent@preview.verivote.ng` | Party agent | `Preview-Sample-2026` |
| `reviewer@preview.verivote.ng` | Reviewer | `Preview-Sample-2026` |
| `auditor@preview.verivote.ng` | Auditor | `Preview-Sample-2026` |
| `elections@preview.verivote.ng` | Election admin | `Preview-Sample-2026` |
| `admin@verivote.ng` | System admin | The `PREVIEW_ADMIN_PASSWORD` you chose |

Observers and party agents sign in at `/admin/sign-in` and land on `/evidence/submit`. Staff land in the admin console at `/admin`.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

The dev server runs at <http://localhost:5173>.

| Command | Purpose |
| --- | --- |
| `npm run dev` | Start the dev server |
| `npm run build` | Typecheck and build the production bundle |
| `npm test` | Run unit tests |
| `npm run lint` | Run ESLint |
| `npm run test:e2e` | Playwright smoke tests against the production build |

Leave `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` empty until a Supabase project exists. For local UI work only, set `VITE_ENABLE_ADMIN_PREVIEW=true` in `.env.local`. That flag is ignored in a production build, and the API still rejects admin requests that have no token.

`VITE_` variables are embedded in the public JavaScript. Never put the database URL, the JWT secret or the service-role key there.

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

`--no-access-log` matters: Uvicorn's access log records client IP addresses, and incident reports promise that IPs are not kept. Open the frontend at `localhost`, not `127.0.0.1`, because `CORS_ORIGINS` lists `http://localhost:5173`.

The health check is `GET http://localhost:8000/api/v1/health`. Interactive docs are at <http://localhost:8000/docs>, except in production where they are disabled.

| Command | Purpose |
| --- | --- |
| `pytest` | Run API tests |
| `ruff check .` | Lint |
| `alembic upgrade head` | Create extensions and tables. Requires `DATABASE_URL` |
| `alembic revision -m "describe the change"` | Start the next migration |

Without `DATABASE_URL` the API uses a local SQLite file (`DEV_DATABASE_PATH`). A production process refuses to start until the database URL, `AUTH_JWT_SECRET` and `CORS_ORIGINS` are all set.

Create the first administrator, then add other staff under **Accounts and roles** in the admin console:

```bash
cd backend && .venv/bin/python -m app.auth.create_admin --email you@example.org --name "Your Name"
```

Running the same command for an existing email resets its password and restores the administrator role. Temporary passwords issued in the console must be changed at first sign-in.

For Supabase, use a Postgres URL with TLS:

```
postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:5432/postgres?sslmode=require
```

`postgresql://` and `postgres://` are rewritten to the `psycopg` driver. Do not use the `anon` role for this connection. After the migration, apply the row-level security statements in [docs/security.md](docs/security.md).

**OCR:** Tesseract is used when installed. Otherwise install RapidOCR by following the steps in `backend/requirements-ocr.txt`. Without either, evidence is still accepted and every field is marked for manual entry.

### Results dashboard with demonstration data

```bash
cd backend && python -m app.analytics.demo_seed   # fictional, labelled demo results
uvicorn app.main:app --reload --port 8000
cd ../frontend && npm run dev                      # open http://localhost:5173/results
```

Every screen then shows "DEMONSTRATION DATA — NOT AN OFFICIAL ELECTION RESULT."

## Deploy on Vercel and Render

The site is a Vite app (`frontend/vercel.json`). The API is a Render web service (`render.yaml`). Nothing is deployed until you connect those two accounts. Do this after the GitHub push.

1. On Render, create a Blueprint from the repository. It builds `backend/`, installs RapidOCR, and keeps photos and the database on a disk at `/var/verivote`. The plan in the file is `starter` because a free instance has no disk and would wipe uploads on restart.
2. Set `CORS_ORIGINS` on the Render service to the exact Vercel address, for example `https://team-2-3-0.vercel.app`. No trailing slash, and no `*`.
3. On Vercel, import the same repository, set the root directory to `frontend`, and add these build variables:
   - `VITE_API_BASE_URL` = `https://<your-render-host>/api/v1`
   - `VITE_SITE_URL` = the Vercel address
   - `VITE_APP_ENV` = `staging`
4. Redeploy the frontend after those variables are set. Vite bakes them in at build time.
5. Create a staff account on the API with `python -m app.auth.create_admin` from a Render shell, then sign in on the site.

This staging setup uses the labelled demo register so you can upload a sheet immediately. It is not the production configuration. Production refuses to start until `APP_ENV=production`, a Postgres `DATABASE_URL`, `EVIDENCE_STORAGE=supabase`, and a private Supabase bucket are all set.

## API overview

All routes live under `/api/v1`. Errors use a structured JSON body with a machine-readable code.

| Area | Main routes |
| --- | --- |
| Health | `GET /health` |
| Auth | `POST /auth/login`, `GET /auth/me`, `GET /auth/account`, `POST /auth/password` |
| Directory | `GET /elections`, `GET /locations/states`, `/lgas`, `/wards`, `GET /polling-units`, `GET /polling-units/{id}`, `GET /updates`, `GET /updates/{id}` |
| Evidence | `POST /evidence`, `GET /evidence/{id}`, `/image`, `/integrity`, `/extraction` (GET and PATCH), `/validation`, `/comparisons`, `/anomalies`, `/audit`, `POST /evidence/{id}/review` |
| Analytics | `GET /analytics/national`, `/states/{id}`, `/lgas/{id}`, `/wards/{id}`, `/polling-units/{id}`, `/reporting-coverage`, `/verification-coverage`, `/party-results`, `/discrepancies`, `/progress`, `GET /analytics/updates` (SSE) |
| Incidents | `POST /incidents`, `GET /incidents/track/{reference}`, `GET /incidents/stats`, `POST /incidents/{id}/review`, `GET /public/incidents` |
| USSD | `POST /ussd/sessions`, `POST /ussd/sessions/{id}/input`, `POST /ussd/gateway`, `POST /ussd/africastalking` |
| SMS | `POST /sms/incoming`, `POST /sms/gateway`, `POST /sms/africastalking`, `GET /sms/messages/{ref}` |
| Admin | `/admin/users`, `/admin/register`, `/admin/register/import`, `/admin/elections`, `/admin/updates`, `/admin/audit-events`, `/admin/analytics/rebuild` |

The full, interactive OpenAPI reference is at `/docs` when the API runs outside production.

## Project structure

```
VoteTrace/
├── backend/
│   ├── alembic/versions/        6 migrations
│   ├── app/
│   │   ├── api/v1/              Routers: auth, directory, evidence, analytics,
│   │   │                        incidents, channels, register, audit, health
│   │   ├── auth/                scrypt passwords, JWT, roles, create_admin
│   │   ├── analytics/           Aggregation, refresh hooks, SSE events, demo seed
│   │   ├── channels/            InfoService, USSD, SMS, Africa's Talking adapter
│   │   ├── core/                Config, errors, logging, rate limiting, security
│   │   ├── db/                  Models, enums, sessions
│   │   ├── directory/           Polling-unit register and election updates
│   │   ├── evidence/            Validation, hashing, storage, preprocessing, OCR,
│   │   │   └── ai/              arithmetic checks, comparison, workflow, and
│   │   │                        uncertainty, discrepancy and Isolation Forest
│   │   ├── incidents/           Reporting, triage, review
│   │   └── schemas/             Pydantic models
│   └── tests/                   pytest suite
├── frontend/
│   ├── e2e/                     Playwright smoke tests
│   ├── public/                  Icons, state boundaries, coats of arms
│   └── src/
│       ├── app/                 Routes and providers
│       ├── components/          UI kit, brand, forms, i18n switcher
│       ├── features/            admin, auth, channels, directory, evidence,
│       │                        incidents, polling-units, public, results,
│       │                        system, updates, verification
│       ├── i18n/                en, ha, ig, yo, pcm messages
│       ├── layouts/             Public layout with tab bar, admin layout
│       └── lib/                 API client, offline database, utilities
├── docs/                        Architecture, data model, security, engines
│   └── images/                  Generated infographics and screenshots
└── scripts/                     preview.sh, build-diagrams.mjs, boundary tools
```

## Testing and quality

| Suite | Count | Command |
| --- | --- | --- |
| Backend (pytest) | ~197 tests | `cd backend && pytest` |
| Frontend unit and component (Vitest) plus e2e (Playwright) | ~101 tests | `cd frontend && npm test && npm run test:e2e` |
| Lint | Ruff and ESLint | `ruff check .` and `npm run lint` |
| Types | Strict TypeScript | `npm run typecheck` |

The tests cover the evidence state machine, two-reviewer verification and self-review blocking, arithmetic rules, cross-submission conflicts, aggregation that counts each unit once, the audit hash chain, the guarantee that the USSD and SMS channels are read-only, rate limiting, gateway signatures, incident triage and masking, offline queues, HEIC photo conversion, and the language switcher.

## Honest scope and roadmap

VoteTrace is a working prototype. **All locations and results in the preview are fictional demo data**, and no INEC data ships with the project. An administrator imports the official polling-unit file under **Elections and register** (see [docs/data-sources.md](docs/data-sources.md)).

**Working now:** everything described above, end to end, on a single server.

**Not built yet, and not faked in the interface:**

```mermaid
flowchart LR
    subgraph Now["Built"]
        A[Single API process] --> B[(PostgreSQL / SQLite)]
        A --> C[In-process SSE broker]
        A --> D[In-memory USSD sessions]
    end
    subgraph Next["Planned, not built"]
        E[Docker images] --> F[Nginx / TLS edge]
        F --> G[Multiple API workers]
        G --> H[(Redis: SSE fan-out<br/>and USSD sessions)]
        G --> I[CI pipeline]
        J[Allocated USSD code<br/>and SMS number]
        K[Election-to-polling-unit<br/>mapping]
    end
    Now -.-> Next
```

- An election-to-polling-unit mapping. Every registered unit is currently expected in every election.
- Multi-worker live updates. The event broker is in-process.
- An allocated USSD code and SMS number, plus a shared USSD session store for more than one worker.
- Containerised deployment, a reverse proxy and continuous integration.
- Publishing official results. VoteTrace figures are independent civic verification, not declarations.

## Further reading

- [Architecture](docs/architecture.md)
- [Data model](docs/data-model.md) and [database](docs/database.md)
- [Security and row-level security](docs/security.md)
- [Evidence capture and result verification](docs/evidence-engine.md)
- [Result aggregation and the national dashboard](docs/results-aggregation.md)
- [Incident reporting, USSD and SMS](docs/incidents-and-channels.md)
- [Data sources and demo data](docs/data-sources.md)
- [Design system](docs/design-system.md)

## Disclaimer

VoteTrace is an **independent civic verification tool**. It is not affiliated with, endorsed by or operated on behalf of the Independent National Electoral Commission (INEC). VoteTrace statuses such as "verified" describe its own evidence review, not an official declaration. Official results are declared by INEC.

## Team

| Name | Role |
| --- | --- |
| **Usman A. OGUNTOLA** | Team lead, senior software engineer, AI and ML engineer |
| **OLOWOOKERE Abdulqoyum Adegoke** | Data scientist and solution architect |

---

<div align="center">

**VoteTrace** · Every Vote, Every Voice.

</div>
