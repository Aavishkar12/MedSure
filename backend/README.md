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
.venv/Scripts/python -m app.migrate
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

## Layout

| Path | What |
|---|---|
| `app/routers/` | Endpoints: cases, documents, claims + drafts, check-ins, devices |
| `app/models.py` | Database tables. Shared file: say so before changing it |
| `app/llm/` | Groq client, prompts and extraction schemas |
| `app/rules.py` | Red-flag rule engine (deterministic, no LLM) |
| `app/firebase.py`, `app/notify.py` | Token verification and push notifications |

## Database migrations

The schema is managed by Alembic; application startup never silently changes it. Before starting a
new checkout or deploying a new version, run:

```bash
.venv/Scripts/python -m app.migrate
```

This also safely adopts an older MedSure database that was created with `create_all`: it verifies the
expected tables and columns before recording the baseline, then applies newer migrations. It refuses
to stamp a partial schema.

After changing `models.py`, generate and review a migration:

```bash
.venv/Scripts/python -m alembic revision --autogenerate -m "describe the change"
.venv/Scripts/python -m alembic upgrade head
```

For a destructive local reset only:

```bash
.venv/Scripts/python -m app.reset_db --yes   # deletes all data
```

Run database tests with `.venv/Scripts/python -m pytest -q`. Set `DATABASE_URL` to a disposable
PostgreSQL test database when adding PostgreSQL-specific behavior; never run reset commands against
the shared Neon database.

## Document processing and app population

OCR runs on the Android device with ML Kit. The backend does not accept PDFs or images and contains no
cloud OCR implementation. `POST /cases/{case_id}/documents` accepts recognized page text in this shape:

```json
{
  "documents": [
    {
      "filename": "discharge-summary.jpg",
      "doc_type": "discharge_summary",
      "file_hash": null,
      "pages": [
        {"page_number": 1, "text": "recognized text", "confidence": 0.96}
      ],
      "warnings": []
    }
  ]
}
```

It returns a processing job. Android polls `GET /jobs/{job_id}`, then reads the database-backed
extraction, discharge-card and bill endpoints. Raw recognized text is retained for deterministic
reprocessing but is excluded from document-list responses. Structured JSON lives in
`document.extraction`; the original medical document stays on the phone.

Leave `DEMO_FALLBACK=false` when verifying real extraction. LLM enrichment can be added after the
deterministic extraction and persistence path is stable.

## Hosted API and database

The production path is Android -> Render FastAPI -> Neon PostgreSQL. Create the Render service from
the repository's root `render.yaml`, then provide `DATABASE_URL` and `FIREBASE_CREDENTIALS` in the
Render dashboard. The Blueprint deploys in Singapore, runs Alembic before every start and verifies the
database through `/health`. Never enable `AUTH_DEV_BYPASS` on the hosted service.

Use Neon's pooled connection string with `sslmode=require`. After deployment, set Android's
`medsure.apiUrl` to the Render HTTPS URL. The phone and database then work without a developer laptop.

## Push notification payload

`data` carries `case_id`, `kind` (`document`, `discharge_card`, `bill`, `claim`, `draft`, `checkin`) and `ref_id`.
