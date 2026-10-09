# MedSure backend

> **Two backends live in this repo for now.** This one (`backend/`) is what the Android app talks to:
> Firebase sign-in, cases, documents, claims, AI features and push notifications.
> `backend-calls/` is the red-alert escalation service (Twilio phone calls, SMS, its own OTP login).
> It runs and is tested on its own, but the app does not call it yet. See `backend-calls/README.md`.

FastAPI + Postgres (Neon) + Firebase Auth/FCM + Groq.

## Run locally

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # macOS/Linux: .venv/bin/python
cp .env.example .env                                       # then fill in; ask Ravi for the shared values
.venv/Scripts/python -m uvicorn app.main:app --reload --host 0.0.0.0
```

API docs: http://localhost:8000

With the default `.env` it runs on a local SQLite file, no Firebase and canned AI results, so you can
start without any accounts.

## Auth

- Real: `Authorization: Bearer <Firebase ID token>`
- Dev (`AUTH_DEV_BYPASS=true`): `X-User-Id: <any name>`

After sign-in the app calls `PATCH /me` with the sign-up details (`name`, `phone`, `email`), then
`POST /devices` with its FCM token. On sign-out it calls `DELETE /devices/{token}`.

## Family circle

- `POST /cases` with `relation: "self"` when the patient signs up, or `son`, `daughter`... for family.
- `POST /cases/{id}/members` adds someone by phone or email. If they have no account yet they show up
  as `pending` and join automatically when they sign in with that phone or email.
- `can_approve: false` makes a member view-only: they cannot approve drafts.

## AI Document Understanding & Q&A

MedSure integrates server-side Groq LLMs (`GROQ_API_KEY`) to extract structured clinical and billing data from medical documents and ground user Q&A:
- **Discharge Summaries:** Clinical diagnosis, medications (dosage, schedule, purpose, warnings), lab values with reference ranges, precautions/red flags, and follow-up schedules.
- **Hospital Bills:** Line items, descriptions, quantities, unit prices, arithmetic reconciliation against stated subtotal/discounts/tax/total, and billing review flags.
- **Prescriptions:** Prescribed medications, dosage instructions, duration, safety confirmation flags.
- **Lab Reports:** Test panels, units, reference intervals, high/low abnormality status flags.
- **Insurance Policies:** Policy details, coverage limits, copay, exclusions, preauth clauses.
- **Grounded Q&A (`POST /cases/{case_id}/ask`):** Answering user questions grounded strictly in their uploaded case documents with source document, page, and exact quotes.

## Running Tests

Run the automated backend test suite:
```bash
python -m pytest tests/test_llm_documents.py -v
```

## Connecting Android Emulator or Physical Device

- **Android Emulator:** Set `API_URL = "http://10.0.2.2:8000"` in `local.properties` or build config.
- **Physical Device:** Ensure the phone and PC are on the same Wi-Fi network and set `API_URL = "http://<PC_LOCAL_IP>:8000"`.

## Layout

| Path | What |
|---|---|
| `app/routers/` | Endpoints: cases, documents (`/cases/{id}/documents`, `/documents/{id}`, `/cases/{id}/ask`, `/discharge-card`, `/bill`), claims, check-ins, devices |
| `app/models.py` | Database tables (Case, CaseMember, Document, DischargeCard, BillItem, User, etc.) |
| `app/llm/` | Groq client, prompts, extraction schemas (discharge, bill, prescription, lab, policy), and document Q&A engine |
| `app/rules.py` | Red-flag rule engine (deterministic, no LLM) |
| `app/firebase.py`, `app/notify.py` | Token verification and push notifications |
| `tests/` | Comprehensive test suite for LLM extraction, bill reconciliation, validations, and API routes |

Tables are created on startup but never altered. After changing `models.py`:

```bash
.venv/Scripts/python -m app.reset_db --yes   # deletes all data
```

## Push notification payload

`data` carries `case_id`, `kind` (`document`, `discharge_card`, `bill`, `claim`, `draft`, `checkin`) and `ref_id`.
