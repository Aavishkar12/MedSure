# MedSure

Patient-and-family app for the weeks after hospital discharge. See [CONTEXT.md](CONTEXT.md) for the idea and scope.

## What is where

| Folder | What |
|---|---|
| `MedSure/` | Android app (Kotlin + Jetpack Compose). Open **this folder** in Android Studio |
| `backend/` | The API the app talks to: sign-in, cases, family, check-ins, documents, AI features, push notifications |
| `backend-calls/` | Red-alert escalation service (Twilio calls and SMS). Works on its own; not connected to the app yet |

## After you pull

**Android**
1. Get `google-services.json` from Ravi and put it in `MedSure/app/`. The app does not build without it,
   and it is deliberately not in the repo.
2. Open `MedSure/` in Android Studio and let Gradle sync.
3. To point the app at a backend, add this line to `MedSure/local.properties` (the file is yours, it is not committed):
   `medsure.apiUrl=http://<laptop-ip>:8000`
   Several addresses can be listed, separated by commas; the app uses the first one that answers.
4. Run the `app` configuration on a phone.

The app works without a backend too: screens keep working and backend calls are skipped.

**Backend**
```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
cp .env.example .env
.venv/Scripts/python run_demo.py
```
That runs with a local database file and canned AI answers, no accounts needed. See [backend/README.md](backend/README.md)
for Firebase, Postgres and Groq, and ask Ravi for the shared `.env` values and the Firebase service-account key.

## Working together

- Start new work from an up-to-date `main`, on your own branch, and merge through a pull request.
- The app lives in `MedSure/`. Do not move it to the repo root.
- `MedSureViewModel.kt` and `backend/app/models.py` are shared by everyone: pull before you change them.
- Never commit `.env`, the Firebase service-account key or `google-services.json`.
