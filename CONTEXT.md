# MedSure — Project Context

## One-liner
MedSure is a patient-and-family-centric Android app for the post-discharge period. It explains medical reports and bills in plain language, helps manage insurance claims, and tracks recovery day by day — AI does the drafting and summarizing, humans approve and decide.

## Background
Built for ACM SIGCHI SRM "Doomsday Hackathon" (MedTech track). Team: PowerBank. Team lead: Ravichandran Jaganathan.

## The problem
After a patient is discharged, the hospital's involvement effectively ends but the hardest part begins for the family:
- Discharge summaries and lab reports are full of clinical jargon nobody explains.
- Itemized bills are long, confusing, and hard to question.
- Insurance claims get denied/delayed at discharge (IRDAI mandates 1-hour admission / 3-hour discharge cashless decisions, rarely enforced in practice); missing documents turn cashless into reimbursement.
- Recovery at home is unsupervised — patients can't tell if a symptom is serious, and nobody is watching for red flags until a readmission happens.

Supporting data points (for reference, not to recite verbatim):
- ₹26,000 Cr of health insurance claims disallowed/repudiated in FY24 (IRDAI Annual Report 2023-24)
- 19% of patients suffer an adverse event after discharge, two-thirds drug-related (Forster et al., Ann Intern Med 2003)
- Only ~14-42% of patients can accurately state their discharge diagnosis/medication side effects (Makaryus & Friedman, Mayo Clin Proc 2005)
- 43.4% of India's health spending is out-of-pocket; ~55M pushed into poverty yearly by medical costs
- Project RED trial: re-engineered discharge process cut 30-day hospital use by ~30%

## Target user
Recovering patients (especially elderly/chronic-care) and their family caregivers who pay bills and chase insurance claims. NOT targeting hospitals or insurers as users in this version — this is a patient/family-side app only.

## The solution — three pillars

### 1. Understand (Reports, Condition, Precautions)
- Upload/scan discharge summary, lab reports, prescriptions.
- AI explains medical jargon in plain language: what the condition is, what report values mean, what medicines are for, precautions/what to avoid.
- Grounded Q&A — answers only from the patient's own uploaded documents, never a general diagnosis engine.
- Output: a clean "Discharge Card" per visit/report, shareable with family.

### 2. Bills & Insurance
- Upload itemized bill → AI explains each line in plain language, flags items "worth asking about."
- Insurance claim tracker: cashless/reimbursement status, document checklist with missing-page detection.
- AI drafts claims/appeal letters; a human (family) must review and approve before anything is sent/submitted — this approval gate is non-negotiable in the design.
- Running total view: paid / pending / insurance-covered.

### 3. Recovery Tracker
- Medicine and follow-up reminders pulled automatically from the Discharge Card.
- Daily check-in via chat or voice: symptoms, pain, basic vitals if available.
- Deterministic rule-based red-flag detection (NOT an LLM diagnosing) — surfaces "this needs attention, consider calling your doctor."
- Trend view for the family: on track / stalling / concerning.

## Cross-pillar integration (what makes it one app, not three)
- **Smart linking:** a report value (e.g. high creatinine) links to the related bill item and the related recovery check-in question. One shared data model underlies all three pillars.
- **Unified timeline:** single scroll of discharge → bill → claim status → daily check-ins.
- **"Explain to family" export:** one-tap simplified summary sendable via WhatsApp to relatives not on the app.
- (Stretch, not MVP) Cost-of-recovery view, medicine photo recognition, follow-up auto-draft question lists, document vault export as PDF, confidence/source indicator on AI explanations ("based on your report, page 3").

## Core design principles (do not violate these)
1. **AI drafts, human approves.** No claim, appeal, or outbound message is ever sent without explicit user approval.
2. **No AI diagnosis.** Red-flag/symptom logic is rule-based and deterministic. The AI explains and summarizes documents; it does not infer new medical conclusions.
3. **Grounded explanations only.** AI answers about reports/bills are grounded in the patient's own uploaded documents, not general knowledge guesses.
4. **Patient/family only in this version.** No hospital-desk or insurer-facing role in the current MVP scope (may be mentioned as future roadmap only).

## Tech stack
| Layer | Tech |
|---|---|
| Android app | Kotlin + Jetpack Compose |
| Backend | FastAPI (Python) |
| Database | PostgreSQL |
| AI/Agent | LLM API with tool-calling for summarization/drafting; separate deterministic rule engine for red-flags |
| OCR | Google ML Kit or Document AI |
| Notifications | Firebase Cloud Messaging |
| Auth | Firebase Auth |
| Voice (stretch) | Android SpeechRecognizer / TTS, Bhashini for Indic languages |
| Data | Synthetic/mock discharge packs, bills, and policies — no real patient data |

## MVP build order (hackathon, ~24h)
1. Auth + case data model (one case per patient, family members attached)
2. Pillar 1: document upload → OCR → AI summarization into Discharge Card
3. Pillar 2: bill explainer, claim checklist, claim draft + approval flow
4. Pillar 3: check-in flow, rule engine, recovery trend view
5. Cross-pillar: unified timeline, smart linking between report/bill/check-in data
6. Polish: WhatsApp export, demo data, UI pass

**Cut first if time runs short:** voice input, multi-language, cost-of-recovery view, medicine photo recognition.
**Never cut:** the approval gate before sending anything, and the Discharge Card (core demo moment).

## Team roles
| Role | Owns |
|---|---|
| Android/Frontend | Compose screens for all 3 pillars + unified timeline |
| Backend/Agent | FastAPI, case/data model, LLM tool-calling for summarization & drafting |
| OCR/Rules | Document/bill parsing pipeline, red-flag rule engine, mock data |
| Design/Integration/Pitch | UI polish, demo script, slides, connects frontend↔backend |

## Non-goals (explicitly out of scope for now)
- Real hospital/insurer system integration (mocked with synthetic data)
- Any AI-generated medical diagnosis or treatment recommendation
- Payment processing / actual fund transfers
- Hospital-desk or insurer-facing UI
