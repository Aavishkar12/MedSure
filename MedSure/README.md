# MedSure — Android (Kotlin + Jetpack Compose)

Native port of the **Tamarind** prototype (team PowerBank, DOOMSDAY Hackathon, MedTech track).
Every colour, size, radius and string is copied from the web prototype.

## Open and run
1. Open this folder in **Android Studio** (Ladybug or newer).
2. Let Gradle sync. If Studio offers to upgrade AGP/Kotlin/Compose versions, accepting is fine.
3. Run the `app` configuration on a phone or emulator (Android 8.0 / API 26+).

## What's inside
```
app/src/main/java/com/powerbank/medsure/
├── MainActivity.kt              App shell: stage routing, top bar, bottom tabs, bottom sheets, back button
├── state/MedSureViewModel.kt    All state + logic (login, roles, check-in rules, claim, approvals)
├── i18n/Dict.kt                 English / Tamil / Hindi copy (generated from the prototype)
├── i18n/Tx.kt                   Language list (22 scheduled languages + English) and lookup
├── ui/theme/Theme.kt            Tamarind palette, Figtree + Bricolage Grotesque fonts
├── ui/components/               Cards, buttons, chips, fields, switch, line icons
├── ui/auth/AuthScreens.kt       Language picker, welcome, phone + email, two OTPs
├── ui/patient/PatientScreens.kt Today (blister pack), My care, Check-in (voice + typed note), Get help
├── ui/family/FamilyScreens.kt   Home, Medicines (approve dose change), Bills, Claim, Recovery
└── ui/settings/SettingsScreens.kt Settings, language change, add/invite member, MedSure+, sheets
```

## Demo flow
1. Pick தமிழ் → **I'm the patient** → any 10-digit phone + any email → any 6 digits in both OTP boxes.
2. Today: tap tablets, **Add family member**, then do the check-in (tap an answer, try the mic, type a note).
3. Settings → **Log out** → **I'm family** → sign in → Medicines → **Approve change**.
4. Log back in as the patient: the morning tablet now reads Furosemide 20 mg.

## Prototype limits (by design)
- OTPs, voice listening, read-aloud, calls (except 108), camera and email sending are UI only.
- English, Tamil and Hindi are fully translated; the other 20 languages fall back to English.
- Bracketed values like `[INSURER]`, `[PRICE]` and `[Nearest clinic]` are placeholders to fill in.
- Hospital/insurer messages stay in English on purpose.

## Production notes
- Move `Dict.kt` into `res/values-xx/strings.xml` and switch locale with
  `AppCompatDelegate.setApplicationLocales` when you add real translations (Bhashini can help).
- Fonts are bundled variable TTFs under the SIL Open Font License.
