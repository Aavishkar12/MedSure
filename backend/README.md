# MedSure backend

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

## Layout

| Path | What |
|---|---|
| `app/routers/` | Endpoints: cases, documents, claims + drafts, check-ins, devices |
| `app/models.py` | Database tables. Shared file: say so before changing it |
| `app/llm/` | Groq client, prompts and extraction schemas |
| `app/rules.py` | Red-flag rule engine (deterministic, no LLM) |
| `app/firebase.py`, `app/notify.py` | Token verification and push notifications |

Tables are created on startup but never altered. After changing `models.py`:

```bash
.venv/Scripts/python -m app.reset_db --yes   # deletes all data
```

## Push notification payload

`data` carries `case_id`, `kind` (`document`, `discharge_card`, `bill`, `claim`, `draft`, `checkin`) and `ref_id`.
