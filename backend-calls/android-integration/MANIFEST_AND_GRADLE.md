# Wiring the alerts into the MedSure Android project

## 1. Copy the files
Copy the `alerts/` folder to `app/src/main/java/com/powerbank/medsure/alerts/`.

## 2. Firebase
1. https://console.firebase.google.com -> create a project -> **Add Android app** with package `com.powerbank.medsure`.
2. Download `google-services.json` into `app/`.
3. Project settings -> **Service accounts** -> **Generate new private key**. Save it as
   `firebase-service-account.json` next to the backend's `docker-compose.yml` (this is the *server* key; never put it in the app).

## 3. Gradle
Root `build.gradle.kts`, inside `plugins { }`:
```kotlin
id("com.google.gms.google-services") version "4.4.2" apply false
```
`app/build.gradle.kts`:
```kotlin
plugins { id("com.google.gms.google-services") }          // add to the existing plugins block
dependencies {
    implementation(platform("com.google.firebase:firebase-bom:33.7.0"))
    implementation("com.google.firebase:firebase-messaging")
}
```

## 4. AndroidManifest.xml
Above `<application>`:
```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
<uses-permission android:name="android.permission.USE_FULL_SCREEN_INTENT" />
```
On `<application>` add (development only, because the dev server is plain http):
```xml
android:usesCleartextTraffic="true"
```
Inside `<application>`:
```xml
<service android:name=".alerts.AlertService" android:exported="false">
    <intent-filter><action android:name="com.google.firebase.MESSAGING_EVENT" /></intent-filter>
</service>
<receiver android:name=".alerts.AckReceiver" android:exported="false" />
```

## 5. Ask for notification permission (Android 13+), in MainActivity.onCreate
```kotlin
if (android.os.Build.VERSION.SDK_INT >= 33) {
    registerForActivityResult(androidx.activity.result.contract.ActivityResultContracts.RequestPermission()) {}
        .launch(android.Manifest.permission.POST_NOTIFICATIONS)
}
com.powerbank.medsure.alerts.AlertService.createChannels(this)
com.google.firebase.messaging.FirebaseMessaging.getInstance().token.addOnSuccessListener { t ->
    com.powerbank.medsure.alerts.Session.saveFcmToken(this, t)
}
```

## 6. Hook the prototype's screens to the API (call from a coroutine / background thread)
| App moment | Call |
|---|---|
| "Send codes" button | `AlertApi.requestOtp(ctx, phone, email)` |
| "Verify and continue" | `AlertApi.verify(ctx, phone, email, otpP, otpE, "patient" or "family", name, langCode)` |
| Check-in answers finished | `AlertApi.submitCheckin(ctx, breathing, swelling, medicine, note)` |
| Family opens a red alert | `AlertApi.getAlert(ctx, alertId)` -> show status + who was contacted |
| "I'm on it" inside the app | `AlertApi.acknowledge(ctx, alertId)` |
| Log out | `AlertApi.unregisterDevice(ctx)` |

Check-in answer words (what the buttons map to):
| Question | Button text | Send |
|---|---|---|
| Breathing | Normal / A little harder / Hard even when resting | `normal` / `harder` / `hard_resting` |
| Swelling | No swelling / Same as before / More than yesterday | `none` / `same` / `more` |
| Medicines | No trouble / Dizzy / Rash or itching / Upset stomach | `none` / `dizzy` / `rash` / `stomach` |

The server decides green / amber / red from these words. The note is stored and shown but never changes the status.

## 7. Open the alert when the notification is tapped
In `MainActivity`, read `intent.getStringExtra("alert_id")` (also in `onNewIntent`) and navigate the family layer to the alert.
