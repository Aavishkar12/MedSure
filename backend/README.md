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

With the default `.env` it runs on a local SQLite file and no Firebase, so you can start without any
accounts. Without `GROQ_API_KEY` documents are read by the rule-based parsers only: typed documents in
the usual layouts work, anything else is marked failed with a message saying the AI is not configured.
The backend never returns sample data in place of a document it could not read.

**OCR for scanned PDFs and photos** needs the Tesseract program as well as the Python packages:
Windows: install from https://github.com/UB-Mannheim/tesseract/wiki and set `TESSERACT_CMD` in `.env`
if it is not on PATH; macOS: `brew install tesseract`; Debian/Ubuntu: `apt install tesseract-ocr`.
Without it, scans are still read when `GROQ_API_KEY` is set (the vision model reads the page images).

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
- **Insurance Policies:** Sum insured, room-rent limit, co-pay, sub-limits, exclusions, non-payable items, waiting periods (`GET /cases/{case_id}/policy`).
- **Insurance coverage (`GET`/`POST /cases/{case_id}/coverage`):** every bill line compared with the policy: covered, partly covered, not covered or unclear, with a plain reason and a quote from the policy. The AI judges each line; co-pay, deductible, the sum-insured cap and all totals are computed in code, and policy quotes are checked against the policy text. Runs by itself once both a bill and a policy have been read.
- **Grounded Q&A (`POST /cases/{case_id}/ask`):** Answering user questions grounded strictly in their uploaded case documents with source document, page, and exact quotes.

How a document is read: file -> text (PDF text layer, OCR text sent by the phone, or Tesseract) ->
document type (the upload category, corrected by `app/pipeline/classifier.py` when the text clearly says
otherwise) -> structured data. Medicines and tests the AI names that do not appear in the document text
are dropped. Upload with `POST /cases/{id}/documents` (field `file`, or several `files`), then poll
`GET /documents/{id}` or `GET /jobs/{job_id}`; `POST /documents/{id}/retry` reads a failed one again.

## Running Tests

Run the automated backend test suite:
```bash
.venv/Scripts/python -m pytest
```
The tests never call Groq: the AI replies are mocked.

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
