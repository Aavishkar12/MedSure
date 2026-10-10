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
3. Point the app at the hosted API in `MedSure/local.properties` (the file is yours, it is not committed):
   `medsure.apiUrl=https://<your-service>.onrender.com`
   For local development only, use `http://<laptop-ip>:8000` from a phone or `http://10.0.2.2:8000`
   from the Android emulator. Several addresses can be listed, separated by commas.
4. For the Nearby Care map, add `maps.apiKey=<your Google Maps API key>` to the same file. Enable the
   Maps SDK for Android and Places API for that key, and restrict it to this Android application.
5. Run the `app` configuration on a phone.

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

OCR happens on the Android device with ML Kit. The original document is not uploaded to FastAPI; Android submits
recognized page text, and the backend deterministically parses it into records stored in PostgreSQL.

## Working together

- Start new work from an up-to-date `main`, on your own branch, and merge through a pull request.
- The app lives in `MedSure/`. Do not move it to the repo root.
- `MedSureViewModel.kt` and `backend/app/models.py` are shared by everyone: pull before you change them.
- Never commit `.env`, the Firebase service-account key or `google-services.json`.
