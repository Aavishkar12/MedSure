# MedSure backend

FastAPI + PostgreSQL. When a patient's check-in comes out **red**, the family is reached by **push notification and a phone call**, one person at a time, until someone confirms.

```
Patient taps answers in the app
  -> POST /checkins
  -> fixed rules decide green / amber / red   (never an LLM, never the free-text note)
  -> RED:  alert saved in Postgres, first call placed within the request
  -> worker, every 2 s, for each family member who can approve (in order):
        push + phone call -> wait 60 s for "press 1" / "I'm on it" -> next person
  -> nobody confirmed: call every approver again + SMS the whole circle
  -> still nobody: marked "exhausted" and written to the audit trail
```

Amber sends a push only (no call). Green is just logged.

## Run it in 2 minutes (no Twilio or Firebase needed)

```bash
python -m venv .venv && source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                     # Windows: copy .env.example .env
# For a quick local run, set in .env:  DATABASE_URL=sqlite:///./medsure.db   and   RUN_WORKER_IN_API=true
uvicorn app.main:app --reload --port 8000
```
Open http://localhost:8000/docs. Calls, pushes and SMS are **printed in the server log as `[DRY-RUN …]`** until you add credentials. With `DEV_MODE=true`, login codes are printed there too, and `DEV_OTP=123456` is always accepted.

With Postgres and Docker instead: put your values in `.env`, drop `firebase-service-account.json` next to `docker-compose.yml` (an empty `{}` file works for dry-run), then `docker compose up --build`.

## Try the red alert from a terminal
```bash
H='Content-Type: application/json'
# 1. Patient signs in (dev: code 123456 for both boxes)
curl -s localhost:8000/auth/request-otp -H "$H" -d '{"phone":"9876500001","email":"lakshmi@example.com"}'
curl -s localhost:8000/auth/verify -H "$H" -d '{"phone":"9876500001","email":"lakshmi@example.com","otp_phone":"123456","otp_email":"123456","role":"patient","name":"Lakshmi"}'
#    -> copy "token" into $P
# 2. Patient adds the first family member (use YOUR real number to receive the demo call)
curl -s localhost:8000/members -H "Authorization: Bearer $P" -H "$H" -d '{"name":"Arjun","phone":"9876500002","email":"arjun@example.com","relation":"son"}'
# 3. A RED check-in
curl -s localhost:8000/checkins -H "Authorization: Bearer $P" -H "$H" -d '{"breathing":"hard_resting","swelling":"none","medicine":"none"}'
```

## Switching on real calls, SMS and push

**Phone calls + SMS (Twilio)**
1. Create a Twilio account, buy or get a trial number, and copy the Account SID and Auth Token.
2. Fill `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` in `.env`.
3. Twilio must reach your server over the internet: run `ngrok http 8000` and set `BASE_URL` to the https URL it prints. Restart the server.
4. Trial accounts can only call numbers you have **verified** in the Twilio console, which is fine for a demo.

**Push (Firebase)**: follow `android-integration/MANIFEST_AND_GRADLE.md` and set `FCM_CREDENTIALS_FILE`.

**Email login codes**: set `SMTP_*`. Otherwise they are only logged (dev).

Each channel switches on independently: you can have push live while calls are still dry-run.

## API

| Endpoint | Who | What |
|---|---|---|
| `POST /auth/request-otp` | anyone | Sends one code by SMS and a different one by email |
| `POST /auth/verify` | anyone | Needs **both** codes. Returns a JWT. Family can only sign in if invited |
| `PUT /devices`, `DELETE /devices` | signed in | Register / remove this phone's FCM token (call on app start, `onNewToken`, logout) |
| `GET /members`, `POST /members` | signed in | Patient may add **one** member; family with *approve* may add more |
| `PATCH /me/settings` | signed in | `allow_alert_calls` (family), `language` |
| `POST /checkins` | patient | `{breathing, swelling, medicine, note?}` -> status, and `alert_id` if amber/red |
| `GET /alerts`, `GET /alerts/{id}` | patient, family | Status plus every push/call/SMS attempt |
| `POST /alerts/{id}/ack` | family (approve) | "I'm on it". Stops escalation. Others get an `alert_ack` push |
| `POST /alerts/{id}/cancel` | patient | "Tapped by mistake". Only before the first call goes out |
| `GET /alerts/{id}/audit` | patient, family | Full timeline |
| `POST /twilio/voice|ack|status/...` | Twilio only | Call script, "press 1", call result. Signature-checked |

## Rules worth knowing

- **Who gets phoned:** only family with *approve* rights who have not switched off alert calls. **View-only members are never called**; they get a push and, at the last step, an SMS.
- **Calls are generic.** The spoken message names the patient and asks for a call back, but reads out **no medical details**; the lock-screen notification is equally generic.
- **No-answer shortcut:** if Twilio reports busy / no-answer / failed, the next person is called straight away instead of waiting out 60 seconds.
- **A provider outage never stops the escalation.** A failed push or call is recorded and the next step still happens.
- **Dead push tokens are deleted automatically.**
- **Optional cancel window:** set `CANCEL_WINDOW_SECONDS=20` and the patient gets 20 s to cancel before anyone is contacted. Leave at `0` for instant.
- **Durable timers:** escalation state lives in Postgres, not in memory, so restarting the server or worker mid-alert loses nothing. You can run several workers safely.

## Tests
```bash
pytest -q                                                        # SQLite, 39 tests (1 needs Postgres)
DATABASE_URL=postgresql+psycopg://user:pass@localhost/medsure_test pytest -q   # all 40
```
The tests use a recording fake in place of Twilio and Firebase and control the clock, so they check who is called, in what order, when, and who is never called.

## What has and has not been verified

Verified here: all 40 tests pass on SQLite and on PostgreSQL 16, including 8 workers racing for one alert (exactly one call goes out); the real API and worker ran as two separate processes and walked a red alert from check-in to acknowledgement; Twilio signature checking was tested using Twilio's own validator.

**Not verified** (needs your accounts or hardware): real Twilio calls and SMS, real Firebase delivery, SMTP, `docker compose build`, and the Android files (checked for syntax only, not built). The **Tamil call voice** (`Google.ta-IN-Standard-A` in `app/voice.py`) is a best guess: confirm it in your Twilio console, or the call falls back to whatever Twilio does for an unknown voice.

## Before real patients use this
- Set a long random `JWT_SECRET`, `DEV_MODE=false`, serve over **https**, and remove `usesCleartextTraffic` from the app.
- Move from `create_all` to Alembic migrations; add rate limiting and move JWTs to refresh tokens.
- India: SMS needs **DLT registration** and automated voice calls have caller-ID / consent rules. Check your provider's requirements. Keep the consent flag (`allow_alert_calls`) and show the family member that alert calls are on when they accept an invite.
- A red alert here is a **backup** to the 108 button in the app, not a replacement for emergency services. Get clinical sign-off on `app/rules.py` before real use.
- Android 14+: Google Play only grants full-screen alert intents to calling/alarm apps. The notification and "I'm on it" button still work without it.
