package com.powerbank.medsure.state

import android.app.Application
import android.content.Context
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.Color
import android.util.Log
import androidx.compose.runtime.snapshotFlow
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import org.json.JSONArray
import org.json.JSONObject
import com.powerbank.medsure.i18n.AllLanguages
import com.powerbank.medsure.i18n.Tx
import com.powerbank.medsure.net.Backend
import com.powerbank.medsure.push.PushBus
import com.powerbank.medsure.ui.theme.Ms
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.time.LocalDate

enum class Stage { Lang, Welcome, Details, Otp, Onboarding, Processing, App }
enum class Role { Patient, Family }
enum class Overlay { Settings, LangPick, Add }
enum class PTab { Today, Care, Checkin, Help }
enum class FTab { Home, Meds, Bills, Claim, Care }
enum class Sheet { Query, Approve }

data class UploadedDoc(
    val uri: Uri,
    val name: String,
    val sizeBytes: Long,
    val mimeType: String,
    /** Text read from a camera scan on the phone, with [Page N] markers. Sent to the backend with the file. */
    val ocrText: String? = null,
) {
    val formattedSize: String get() {
        val kb = sizeBytes / 1024.0
        return if (kb >= 1024) {
            String.format(java.util.Locale.US, "%.1f MB", kb / 1024.0)
        } else {
            String.format(java.util.Locale.US, "%d KB", (kb + 0.5).toInt().coerceAtLeast(1))
        }
    }
    val isPdf: Boolean get() = mimeType.contains("pdf", ignoreCase = true) || name.endsWith(".pdf", ignoreCase = true)
}

data class OnboardingFamilyMember(
    val name: String,
    val phone: String,
    val canApprove: Boolean,
)

data class Member(val name: String, val rel: String, val role: String, val you: Boolean, val phone: String = "")

/** Where the automatic red-alert call is. */
enum class CallPhase { Idle, Counting, Dialed, Cancelled, NoOne }

const val CALL_COUNTDOWN_SECONDS = 10

/** true: a red result also starts the 10 s countdown call. false: only the hidden 'Get help now' tap calls. */
const val AUTO_CALL_ON_RED = true
const val NEXT_CALL_COUNTDOWN_SECONDS = 3

/** Relations the app has a label for; anything else shows as "Other". */
private val KNOWN_RELATIONS = setOf("son", "daughter", "spouse", "other")

/** Papers an insurance claim needs: upload category, label key, and whether the claim cannot go without it. */
private const val LAST_UTTERANCE = "last"

/** Id of the Help-tab entry for the hospital named on the discharge papers. */
const val DISCHARGE_HOSPITAL_ID = "discharge-hospital"

private val CLAIM_PAPERS = listOf(
    Triple("discharge_summary", "cpDischarge", true),
    Triple("bill", "cpBill", true),
    Triple("policy", "cpPolicy", true),
    Triple("id_proof", "cpId", true),
    Triple("lab_report", "cpLab", false),
    Triple("prescription", "cpRx", false),
)

/** Bump when the saved-state format changes; older saved state is then dropped. */
private const val STATE_VERSION = 2

data class Dose(
    val id: String, val name: String, val time: String, val what: String, val why: String, val taken: Boolean,
)

data class Level(
    val name: String, val caps: String, val title: String, val body: String,
    val bg: Color, val fg: Color, val dot: Color,
)

data class Place(
    val id: String, val type: String, val name: String, val meta: String, val dist: String, val open: String, val badge: String, val lat: Double = 0.0, val lng: Double = 0.0,
)

data class Flag(
    val id: String, val label: String, val amt: String, val note: String, val why: String, val draft: String,
)

data class CheckItem(
    val name: String, val sub: String, val done: Boolean, val fixLabel: String = "", val fix: (() -> Unit)? = null,
)

data class Approval(val title: String, val sub: String, val open: () -> Unit)

/** All app state. Mirrors the web prototype one-to-one so the screens behave the same. */
class MedSureViewModel(app: Application) : AndroidViewModel(app) {
    // Auth
    var stage by mutableStateOf(Stage.Lang)
    var lang by mutableStateOf<String?>(null)
    var loginRole by mutableStateOf(Role.Patient)
    var role by mutableStateOf(Role.Patient)
    var phone by mutableStateOf("")
    var email by mutableStateOf("")
    var otpP by mutableStateOf("")
    var otpE by mutableStateOf("")

    // Navigation
    var overlay by mutableStateOf<Overlay?>(null)
    private var prevOverlay: Overlay? = null
    var ptab by mutableStateOf(PTab.Today)
    var ftab by mutableStateOf(FTab.Home)
    var sheet by mutableStateOf<Sheet?>(null)

    // Family circle + invite form
    val members = mutableStateListOf<Member>()
    var fName by mutableStateOf("")
    var fRel by mutableStateOf("son")
    var fRole by mutableStateOf("approve")
    var fPhone by mutableStateOf("")
    var fEmail by mutableStateOf("")

    // Patient
    val taken = mutableStateMapOf<String, Boolean>()
    var step by mutableIntStateOf(0)
    val ans = mutableStateListOf<Int>()
    var listening by mutableStateOf(false)
    var care by mutableStateOf("watch")
    var reading by mutableStateOf(false)
        private set
    var readError by mutableStateOf<String?>(null)
    var note by mutableStateOf("")
    var noteSaved by mutableStateOf("")
    var filter by mutableStateOf("all")
    var chosen by mutableStateOf<String?>(null)
    var share by mutableStateOf(true)

    // Family
    var qid by mutableStateOf("f1")
    val sent = mutableStateMapOf<String, Boolean>()
    var k4 by mutableStateOf(false)
    var k5 by mutableStateOf(false)
    var medChange by mutableStateOf("pending")
    var plan by mutableStateOf("stay")
    var plus by mutableStateOf(false)

    val tx: Tx get() = Tx(lang)
    val isPatient get() = role == Role.Patient
    val langNative get() = AllLanguages.firstOrNull { it.code == lang }?.native ?: "English"

    // ---------- Auth ----------
    private fun digits(v: String) = v.filter { it.isDigit() }
    fun okOtp(v: String) = digits(v).length == 6
    val canSend get() = digits(phone).length >= 10 && email.indexOf('@') >= 1 && email.contains('.')
    val canVerify get() = okOtp(otpP) && okOtp(otpE)

    fun onPhone(v: String) { phone = v.filter { it.isDigit() || it == ' ' }.take(11) }
    fun onEmail(v: String) { email = v.trim() }
    fun onOtpP(v: String) { otpP = digits(v).take(6) }
    fun onOtpE(v: String) { otpE = digits(v).take(6) }
    fun sendCodes() { otpP = ""; otpE = ""; stage = Stage.Otp }

    // Onboarding (held in-memory, survives going back and forth between steps)
    var onboardingStep by mutableIntStateOf(1)
    var onbFullName by mutableStateOf("")
    var onbAge by mutableStateOf("")
    var onbGender by mutableStateOf<String?>(null)
    var onbBloodGroup by mutableStateOf<String?>(null)
    var onbInteractedName by mutableStateOf(false)
    var onbInteractedAge by mutableStateOf(false)
    val onbReports = mutableStateListOf<UploadedDoc>()
    val onbBills = mutableStateListOf<UploadedDoc>()
    var onbInsCompany by mutableStateOf("")
    var onbInsPolicy by mutableStateOf("")
    var onbInsDoc by mutableStateOf<UploadedDoc?>(null)
    val onbFamilyMembers = mutableStateListOf<OnboardingFamilyMember>()

    // Reading the onboarding documents (ProcessingScreen shows these)
    var processingError by mutableStateOf<String?>(null)
    var processingActiveStep by mutableIntStateOf(0)
    var processingCompletedSteps by mutableIntStateOf(0)
    var processingTargetProgress by mutableFloatStateOf(0.08f)
    var processingCompletedPills by mutableIntStateOf(0)
    private var processingJob: Job? = null
    /** Onboarding file (uri) -> backend document id, so a retry never uploads the same file twice. */
    private val uploadedDocs = mutableStateMapOf<String, Int>()
    var extractedData by mutableStateOf<JSONObject?>(null)
    var showExtractionDebug by mutableStateOf(false)

    val onbStep1Valid: Boolean
        get() = onbFullName.trim().isNotEmpty() &&
                (onbAge.toIntOrNull()?.let { it in 1..120 } == true) &&
                onbGender != null &&
                onbBloodGroup != null

    fun nextOnboardingStep() {
        if (onboardingStep < 4) {
            onboardingStep += 1
        } else {
            stage = Stage.Processing
        }
    }

    fun prevOnboardingStep() {
        if (onboardingStep > 1) {
            onboardingStep -= 1
        } else {
            stage = Stage.Otp
        }
    }

    fun completeProcessing() {
        stage = Stage.App
        overlay = null
        ptab = PTab.Today
        ftab = FTab.Home
        saveOnboarding()
    }

    /**
     * Uploads the onboarding documents and waits while the backend reads them (OCR + AI), so the
     * home screen opens with the patient's own discharge card, bill and policy. Safe to call again
     * after a failure: files already uploaded are not sent twice, and failed ones are read again.
     */
    fun startProcessing(context: Context) {
        if (processingJob?.isActive == true) return
        processingError = null
        val app = context.applicationContext
        processingJob = viewModelScope.launch {
            try {
                processingActiveStep = 0; processingTargetProgress = 0.2f; processingCompletedPills = 1
                saveOnboardingMembers()
                val id = syncLock.withLock { ensureSession(createCase = true) }
                    ?: throw java.io.IOException("Could not create your case on the server")
                processingCompletedSteps = 1; processingCompletedPills = 2

                // Reports go up without a type: the server tells a discharge summary from a lab report by its text.
                processingActiveStep = 1; processingTargetProgress = 0.4f
                val pending = onbReports.map { it to null } + onbBills.map { it to "bill" } + listOfNotNull(onbInsDoc).map { it to "policy" }
                for ((doc, type) in pending) {
                    val key = doc.uri.toString()
                    val known = uploadedDocs[key]
                    if (known == null) {
                        uploadedDocs[key] = Backend.uploadDocument(app, id, doc, type)
                    } else if (Backend.document(known).status == "failed") {
                        Backend.retryDocument(known)
                    }
                }
                processingCompletedSteps = 2; processingCompletedPills = 3

                // The AI takes a few seconds per document; scans and long PDFs take longer.
                processingActiveStep = 2
                val ids = pending.mapNotNull { uploadedDocs[it.first.uri.toString()] }
                val deadline = System.currentTimeMillis() + 180_000
                var docs = ids.map { Backend.document(it) }
                while (docs.any { it.status == "processing" } && System.currentTimeMillis() < deadline) {
                    val done = docs.count { it.status != "processing" }
                    processingTargetProgress = 0.5f + 0.4f * done / docs.size.coerceAtLeast(1)
                    delay(1500)
                    docs = ids.map { Backend.document(it) }
                }
                processingCompletedSteps = 3; processingCompletedPills = 4

                processingActiveStep = 3; processingTargetProgress = 0.95f
                loadCaseAnalysis(id)
                runCatching { extractedData = Backend.getCaseExtractions(id) }
                val failed = docs.filter { it.status == "failed" }
                val slow = docs.filter { it.status == "processing" }
                if (failed.isNotEmpty() || slow.isNotEmpty()) {
                    processingError = (failed.map { "${it.filename}: ${it.error ?: "could not be read"}" } +
                        slow.map { "${it.filename}: still being read" }).joinToString("\n")
                    return@launch
                }
                processingCompletedSteps = 4; processingCompletedPills = 5; processingTargetProgress = 1f
                delay(400)
                completeProcessing()
            } catch (e: Exception) {
                Log.e("MedSure", "Document processing failed", e)
                processingError = e.message ?: "Could not reach the MedSure server"
            }
        }
    }

    fun verify() {
        if (!canVerify) return
        if (loginRole == Role.Family) {
            members.clear() // the family circle arrives from the backend once this phone is matched to a case
            role = Role.Family
            overlay = null; ptab = PTab.Today; ftab = FTab.Home
            stage = Stage.App
        } else {
            members.indices.forEach { i -> members[i] = members[i].copy(you = false) }
            role = Role.Patient
            onboardingStep = 1
            stage = Stage.Onboarding
        }

        // Family lands in the app now. A patient's case is created when onboarding finishes.
        sessionStale = true
        send("Sign-in")
    }

    /** Onboarding finished: show the helpers in the family circle and send everything to the backend. */
    private fun saveOnboarding() {
        saveOnboardingMembers()
        send("Onboarding")
    }

    /** The helpers added during onboarding join the family circle; the next sync sends them. */
    private fun saveOnboardingMembers() {
        onbFamilyMembers.forEach { h ->
            val number = normalizePhone(h.phone)
            if (members.none { it.phone == number }) {
                members.add(Member(h.name, "other", if (h.canApprove) "approve" else "view", false, number))
            }
        }
        sessionStale = true
    }

    /** Logging out leaves a clean slate for whoever signs in next on this phone. */
    fun logout() {
        cancelCall(); callPhase = CallPhase.Idle
        stage = Stage.Welcome; overlay = null; otpP = ""; otpE = ""; sheet = null
        ptab = PTab.Today; ftab = FTab.Home; onboardingStep = 1
        phone = ""; email = ""
        members.clear()
        onbFullName = ""; onbAge = ""; onbGender = null; onbBloodGroup = null
        onbInteractedName = false; onbInteractedAge = false
        onbReports.clear(); onbBills.clear(); onbInsCompany = ""; onbInsPolicy = ""; onbInsDoc = null
        onbFamilyMembers.clear()
        step = 0; ans.clear(); listening = false; note = ""; noteSaved = ""
        taken.clear()
        medChange = "pending"; sent.clear(); k4 = false; k5 = false
        caseId = null; lastCheckinId = null; sentNote = ""; patientName = ""
        processingJob?.cancel(); processingError = null; uploadedDocs.clear(); extractedData = null
        dischargeCardData = null; billData = null; coverage = null; caseDocuments.clear(); rawPlaces.clear()
        cardJson = null; billJson = null; coverageJson = null; documentsJson = null
        policy = null; policyJson = null; claimDraft = null; claimDraftJson = null; draftError = null
        checkinDays.clear(); shareRequest = null; addDocsError = null
        fName = ""; fPhone = ""; fEmail = ""
        sessionStale = true; pendingCheckin = false; stateDirty = false
        sync("Sign-out") { Backend.signOut() }
    }

    // ---------- Backend & LLM State ----------
    /** The case this user is on, once the backend has confirmed it. */
    var caseId by mutableStateOf<Int?>(null)

    /** Today's check-in on the backend, so a note added afterwards can be attached to it. */
    private var lastCheckinId by mutableStateOf<Int?>(null)

    // What still has to reach the backend. These are saved with the rest of the state, so anything that
    // failed to send (no network, server down) is retried until it gets through, even after a restart.
    private var sessionStale by mutableStateOf(true)      // profile, case and family circle not confirmed yet
    private var pendingCheckin by mutableStateOf(false)   // today's check-in not sent yet
    private var stateDirty by mutableStateOf(false)       // tablets taken / medicine change not sent yet
    private var sentNote by mutableStateOf("")
    private val syncLock = Mutex()

    // What the backend read from this case's documents. Kept on the phone too (see snapshot), so the
    // screens show the patient's own data straight away after a restart.
    var dischargeCardData by mutableStateOf<DischargeCardModel?>(null)
    var billData by mutableStateOf<BillDataModel?>(null)
    var coverage by mutableStateOf<CoverageModel?>(null)
    val caseDocuments = mutableStateListOf<DocumentInfoModel>()
    var coverageRunning by mutableStateOf(false)
    private var cardJson: String? = null
    private var billJson: String? = null
    private var coverageJson: String? = null
    private var documentsJson: String? = null
    var policy by mutableStateOf<PolicyModel?>(null)
    private var policyJson: String? = null
    private var claimDraftJson: String? = null

    init {
        viewModelScope.launch { PushBus.events.collect { refresh() } }
    }

    /** Signs in and makes sure the backend has this person's profile, case and family circle. Returns the case id. */
    private suspend fun ensureSession(createCase: Boolean = stage == Stage.App): Int? {
        Backend.signIn()
        if (sessionStale) {
            // Family have no name field at sign-in: the backend keeps the name the patient gave them.
            val name = if (isPatient) onbFullName.trim().ifEmpty { me } else ""
            Backend.saveProfile(name, phone, email) // also links this phone number to the cases it was invited to
            var id = Backend.myCaseId(isPatient)
            if (id == null && isPatient && createCase) id = Backend.createCase(name, "self")
            caseId = id
            if (id != null) {
                members.filter { !it.you && it.phone.isNotBlank() }.forEach {
                    Backend.addMember(id, it.name, it.rel, it.role == "approve", it.phone, "")
                }
            }
            Backend.registerDevice()
            sessionStale = false
        }
        // Family can be invited to a newer case after they signed in, so they always look again.
        if (!isPatient || caseId == null) caseId = Backend.myCaseId(isPatient)
        return caseId
    }

    /** Sends whatever has not reached the backend yet. */
    private suspend fun flush(id: Int) {
        if (isPatient && pendingCheckin && ciDone) {
            val note = noteSaved
            lastCheckinId = Backend.checkin(id, ans.toList(), note) // family sees it; they are notified if it needs attention
            sentNote = note
            pendingCheckin = false
        }
        val checkinId = lastCheckinId
        if (isPatient && checkinId != null && noteSaved != sentNote) {
            val note = noteSaved
            Backend.updateCheckinNote(checkinId, note)
            sentNote = note
        }
        if (stateDirty) {
            stateDirty = false
            try {
                if (isPatient) Backend.sendTaken(id, taken.toMap(), today()) else Backend.sendMedChange(id, medChange)
            } catch (e: Exception) {
                stateDirty = true
                throw e
            }
        }
    }

    /** Brings in what the others on the case did. */
    private suspend fun pull(id: Int) {
        // Family circle: the same list on every phone.
        val everyone = Backend.members(id)
        everyone.firstOrNull { it.relation == "self" }?.name?.takeIf { it.isNotBlank() }?.let { patientName = it }
        val circle = everyone.filter { it.relation != "self" }.map {
            Member(
                it.name.ifBlank { "Family" }, if (it.relation in KNOWN_RELATIONS) it.relation else "other",
                if (it.canApprove) "approve" else "view", it.you, normalizePhone(it.phone),
            )
        }
        if (!sessionStale && circle != members.toList()) { members.clear(); members.addAll(circle) }

        loadCaseAnalysis(id)

        val shared = Backend.sharedState(id)
        // A medicine change is decided by family; tablets taken are ticked by the patient.
        shared.optString("med_change").takeIf { it.isNotEmpty() && !stateDirty }?.let { medChange = it }
        if (isPatient) return
        val sharedTaken = shared.optJSONObject("taken")
        if (sharedTaken != null && shared.optString("taken_day") == today()) {
            sharedTaken.keys().forEach { taken[it] = sharedTaken.getBoolean(it) }
        }
        // The patient's latest check-in from today: answers, result and note.
        val latest = Backend.latestCheckin(id)
        if (latest != null && latest.isToday) {
            if (ans.toList() != latest.levels) { ans.clear(); ans.addAll(latest.levels) }
            step = 3
            noteSaved = latest.note
        } else {
            ans.clear(); step = 0; noteSaved = ""
        }
    }

    /** Full sync. Runs when the app comes to the front, when a push arrives, and every few seconds while open. */
    fun refresh() {
        if (stage != Stage.App || syncLock.isLocked) return
        sync("Refresh") {
            val id = ensureSession() ?: return@sync
            flush(id)
            pull(id)
        }
    }

    /** Sends local changes now. If it fails they stay marked and the next refresh retries. */
    private fun send(what: String) = sync(what) { ensureSession()?.let { flush(it) } }

    /** Fetches what the backend has read from the case's documents. A missing piece leaves the old one in place. */
    suspend fun loadCaseAnalysis(id: Int) {
        runCatching { Backend.listDocuments(id) }.onSuccess { arr ->
            documentsJson = arr.toString(); setDocuments(parseDocuments(arr))
        }.onFailure { Log.w("MedSure", "Documents fetch failed", it) }
        runCatching { Backend.getDischargeCard(id) }.onSuccess { json ->
            cardJson = json?.toString(); dischargeCardData = json?.let(::parseDischargeCard)
        }.onFailure { Log.w("MedSure", "Discharge card fetch failed", it) }
        runCatching { Backend.getBill(id) }.onSuccess { json ->
            billJson = json.toString(); billData = parseBill(json).takeIf { it.items.isNotEmpty() }
        }.onFailure { Log.w("MedSure", "Bill fetch failed", it) }
        runCatching { Backend.getCoverage(id) }.onSuccess { json ->
            coverageJson = json?.toString(); coverage = json?.let(::parseCoverage)
        }.onFailure { Log.w("MedSure", "Coverage fetch failed", it) }
        runCatching { Backend.getPolicy(id) }.onSuccess { json ->
            policyJson = json?.toString(); policy = json?.let(::parsePolicy)
        }.onFailure { Log.w("MedSure", "Policy fetch failed", it) }
        if (!draftBusy) runCatching { Backend.getClaimDraft(id) }.onSuccess { json ->
            claimDraftJson = json?.toString(); claimDraft = json?.let(::parseDraft)
        }.onFailure { Log.w("MedSure", "Claim letter fetch failed", it) }
        runCatching { Backend.checkins(id) }.onSuccess { all ->
            // One result per day: the latest check-in made that day.
            val days = all.mapNotNull { c -> c.day?.let { CheckinDay(it, c.levels.maxOrNull() ?: 0, c.note) } }
                .groupBy { it.day }.map { it.value.last() }.sortedBy { it.day }
            if (days != checkinDays.toList()) { checkinDays.clear(); checkinDays.addAll(days) }
        }.onFailure { Log.w("MedSure", "Check-ins fetch failed", it) }
    }

    private fun setDocuments(list: List<DocumentInfoModel>) {
        if (list != caseDocuments.toList()) { caseDocuments.clear(); caseDocuments.addAll(list) }
    }

    var addingDocs by mutableStateOf(false)
    var addDocsError by mutableStateOf<String?>(null)

    /**
     * Uploads papers added after onboarding and waits for the backend to read them.
     * docType null lets the server tell a discharge summary, lab report, bill or policy apart by its text.
     */
    fun addDocuments(context: Context, docs: List<UploadedDoc>, docType: String? = null) {
        if (docs.isEmpty() || addingDocs) return
        val app = context.applicationContext
        addingDocs = true
        addDocsError = null
        viewModelScope.launch {
            try {
                val id = syncLock.withLock { ensureSession(createCase = isPatient) }
                    ?: throw java.io.IOException(tx["noCaseYet"])
                val ids = docs.map { Backend.uploadDocument(app, id, it, docType) }
                loadCaseAnalysis(id) // shows them as "being read" straight away
                val deadline = System.currentTimeMillis() + 180_000
                var states = ids.map { Backend.document(it) }
                while (states.any { it.status == "processing" } && System.currentTimeMillis() < deadline) {
                    delay(2000)
                    states = ids.map { Backend.document(it) }
                }
                loadCaseAnalysis(id)
                states.filter { it.status == "failed" }.takeIf { it.isNotEmpty() }?.let { failed ->
                    addDocsError = failed.joinToString("\n") { "${it.filename}: ${it.error ?: "could not be read"}" }
                }
            } catch (e: Exception) {
                Log.w("MedSure", "Adding documents failed", e)
                addDocsError = e.message ?: "Could not reach the MedSure server"
            } finally {
                addingDocs = false
            }
        }
    }

    /** Compares the bill with the insurance policy again (family Claim tab). */
    fun checkCoverage() {
        if (coverageRunning) return
        coverageRunning = true
        sync("Coverage") {
            try {
                val id = ensureSession() ?: return@sync
                val json = Backend.runCoverage(id)
                coverageJson = json.toString(); coverage = parseCoverage(json)
            } finally {
                coverageRunning = false
            }
        }
    }

    /** Runs backend work off the screens, one piece at a time. The screens keep working if it fails. */
    private fun sync(what: String, block: suspend () -> Unit) {
        viewModelScope.launch {
            try { syncLock.withLock { block() } } catch (e: Exception) { Log.w("MedSure", "$what failed", e) }
        }
    }

    // ---------- Overlays ----------
    fun closeOverlay() {
        overlay = if (overlay == Overlay.LangPick || (overlay == Overlay.Add && prevOverlay == Overlay.Settings)) Overlay.Settings else null
    }

    fun openAdd() {
        prevOverlay = overlay
        fName = ""; fPhone = ""; fEmail = ""
        fRel = if (isPatient) "son" else "daughter"; fRole = "approve"
        overlay = Overlay.Add
    }

    /** Exactly 10 digits, typed without +91. A pasted +91 / 91 / leading 0 is stripped. */
    fun cleanPhone10(raw: String): String {
        var d = raw.filter { it.isDigit() }
        if (d.length >= 12 && d.startsWith("91")) d = d.drop(2)
        else if (d.length == 11 && d.startsWith("0")) d = d.drop(1)
        return d.take(10)
    }
    fun onFPhone(v: String) { fPhone = cleanPhone10(v) }

    /** A valid Indian mobile number: 10 digits starting with 6, 7, 8 or 9. */
    val phoneOk get() = fPhone.length == 10 && fPhone[0] in '6'..'9'
    val phoneBadStart get() = fPhone.isNotEmpty() && fPhone[0] !in '6'..'9'

    // The email is free text on purpose: it is never checked here.
    val canAdd get() = fName.isNotBlank() && phoneOk && !(isPatient && members.isNotEmpty())

    fun submitAdd() {
        if (!canAdd) return
        val added = Member(fName.trim(), fRel, if (isPatient) "approve" else fRole, false, phone = normalizePhone(fPhone))
        members.add(added)
        overlay = if (prevOverlay == Overlay.Settings) Overlay.Settings else null

        sessionStale = true // the family circle changed; it is sent again in full
        send("Invite")
    }

    /** The signed-in person's first name: what they typed, or what the case knows them as. */
    val me: String
        get() {
            val name = if (isPatient) onbFullName.ifBlank { patientName } else members.firstOrNull { it.you }?.name.orEmpty()
            return name.trim().substringBefore(' ').ifEmpty { tx["meFallback"] }
        }

    /** The patient's name as the case knows it. */
    var patientName by mutableStateOf("")
        private set
    val patientFullName: String get() = (if (isPatient) onbFullName.ifBlank { patientName } else patientName).trim()
    val patientFirstName: String get() = patientFullName.substringBefore(' ').ifEmpty { tx["patientFallback"] }

    /** Dictionary text with the patient's name filled in. */
    fun named(key: String) = tx[key].replace("{name}", patientFirstName)

    // ---------- Read aloud ----------
    private var tts: android.speech.tts.TextToSpeech? = null
    private var ttsReady = false

    /** What the open My care section says, as one text to speak. */
    private fun careSpeech(): String {
        val t = tx
        val card = dischargeCardData ?: return t["noCard"]
        fun sentence(s: String) = s.trim().let { if (it.isEmpty() || it.last() in ".!?") it else "$it." }
        val parts = when (care) {
            "watch" -> listOf(t["cWatch"]) + card.warningSigns.map { it.text }.ifEmpty { listOf(t["noWatch"]) } +
                t["call108line"] + (if (card.precautions.isEmpty()) emptyList() else listOf(t["precautions"]) + card.precautions.map { it.text })
            "meds" -> listOf(t["cMeds"]) + card.medicines.map { m ->
                listOf(listOf(m.name, m.dose).filter { it.isNotBlank() }.joinToString(" "), m.schedule,
                    m.days?.let { "for $it days" }.orEmpty(), m.purpose).filter { it.isNotBlank() }.joinToString(", ")
            }.ifEmpty { listOf(t["noMeds"]) }
            "visit" -> listOf(t["cVisit"]) + card.followUps.map { listOf(it.text, it.sub).filter { s -> s.isNotBlank() }.joinToString(", ") }
                .ifEmpty { listOf(t["noVisit"]) }
            else -> listOf(t["cHappened"], card.diagnosisName, card.diagnosisPlain, card.summary)
        }
        return (parts.filter { it.isNotBlank() }.map(::sentence) + sentence(card.disclaimer)).joinToString(" ")
    }

    /** The "Read this aloud" button: speaks the open My care section, or stops if it is speaking. */
    fun toggleReadAloud() {
        if (reading) { stopReading(); return }
        readError = null
        val text = careSpeech()
        val engine = tts
        if (engine != null && ttsReady) { speak(engine, text); return }
        reading = true // shows "Reading aloud" while the engine starts
        tts = android.speech.tts.TextToSpeech(getApplication()) { status ->
            val started = tts
            if (status != android.speech.tts.TextToSpeech.SUCCESS || started == null) {
                reading = false
                readError = tx["ttsMissing"]
                return@TextToSpeech
            }
            ttsReady = true
            started.setOnUtteranceProgressListener(object : android.speech.tts.UtteranceProgressListener() {
                override fun onStart(utteranceId: String?) {}
                override fun onDone(utteranceId: String?) { if (utteranceId == LAST_UTTERANCE) reading = false }
                @Deprecated("Deprecated in Java")
                override fun onError(utteranceId: String?) { reading = false }
            })
            if (reading) speak(started, text) // not cancelled while the engine was starting
        }
    }

    private fun speak(engine: android.speech.tts.TextToSpeech, text: String) {
        // The AI writes its explanations in English; an Indian English voice reads names and medicines best.
        val voices = listOf(java.util.Locale("en", "IN"), java.util.Locale.UK, java.util.Locale.US)
        val ok = voices.any { engine.setLanguage(it) >= android.speech.tts.TextToSpeech.LANG_AVAILABLE }
        if (!ok) { reading = false; readError = tx["ttsNoVoice"]; return }
        engine.setSpeechRate(0.9f) // a little slower than normal: easier to follow
        // The engine takes a limited length at once, so it is fed sentence by sentence.
        val sentences = text.split(Regex("(?<=[.!?])\\s+")).filter { it.isNotBlank() }
        reading = true
        sentences.forEachIndexed { i, sentence ->
            val mode = if (i == 0) android.speech.tts.TextToSpeech.QUEUE_FLUSH else android.speech.tts.TextToSpeech.QUEUE_ADD
            engine.speak(sentence, mode, null, if (i == sentences.lastIndex) LAST_UTTERANCE else "s$i")
        }
    }

    /** Stops speaking: the button was tapped again, the section changed, or the app went to the background. */
    fun stopReading() {
        tts?.stop()
        reading = false
    }

    override fun onCleared() {
        tts?.shutdown()
        tts = null
        super.onCleared()
    }

    // ---------- Today ----------
    val todayLabel: String get() = LocalDate.now().format(java.time.format.DateTimeFormatter.ofPattern("EEE, d MMM", java.util.Locale.ENGLISH))

    /** "Day 3 at home", counted from the discharge date on the papers. Empty when that date is not known. */
    val dayHomeLabel: String
        get() {
            val discharged = dischargeCardData?.dischargeDate?.let(::parseDocDate) ?: return ""
            val day = java.time.temporal.ChronoUnit.DAYS.between(discharged, LocalDate.now()) + 1
            return if (day in 1..365) tx["dayAtHome"].replace("{n}", day.toString()) else ""
        }

    fun relLabel(rel: String) = tx["r" + rel.replaceFirstChar { it.uppercase() }]
    fun roleLabel(r: String) = if (r == "approve") tx["canApprove"] else tx["canView"]

    // ---------- Medicines ----------
    /** True once this case has documents on the backend. */
    val hasCaseData get() = caseDocuments.isNotEmpty() || dischargeCardData != null || billData != null

    /** Medicines from the Discharge Card (with prescriptions merged in by the backend). */
    val doses: List<Dose>
        get() = dischargeCardData?.medicines.orEmpty().mapIndexed { i, m ->
            val id = "med_$i"
            val what = listOf(m.dose, m.days?.let { "$it days" }.orEmpty()).filter { it.isNotBlank() }.joinToString(" · ")
            Dose(id, m.name, m.schedule.ifBlank { tx["asDirected"] }, what, m.purpose, taken[id] == true)
        }
    val takenCount get() = doses.count { it.taken }
    fun toggleDose(id: String) {
        taken[id] = taken[id] != true
        if (isPatient) { stateDirty = true; send("Tablets") } // family sees today's tablets
    }

    /** Family approves or holds a dose change; the patient's medicine list follows. */
    fun changeMed(status: String) {
        medChange = status
        stateDirty = true
        send("Medicine change")
    }

    // ---------- Check-in ----------
    /**
     * Three questions. The first two ask about the warning signs written on the patient's own discharge
     * papers (general questions when there are none); the third is about trouble with medicines.
     * Scoring is fixed: 0 fine, 1 keep watch, 2 needs help now. No AI decides the result.
     */
    val questions: List<Pair<String, List<Pair<String, Int>>>>
        get() {
            val t = tx
            val yesNo = listOf(t["ansNo"] to 0, t["ansLittle"] to 1, t["ansYes"] to 2)
            val signs = dischargeCardData?.warningSigns.orEmpty().map { it.text.trim().trimEnd('.') }.filter { it.length in 3..140 }.take(2)
            val list = signs.map { t["qSign"].replace("{sign}", it) to yesNo }.toMutableList()
            if (list.isEmpty()) list += t["qFeel"] to listOf(t["qFeelA"] to 0, t["qFeelB"] to 1, t["qFeelC"] to 2)
            if (list.size < 2) list += t["qNew"] to yesNo
            list += t["q3"] to listOf(t["q3a"] to 0, t["q3b"] to 1, t["q3c"] to 1, t["q3d"] to 1)
            return list
        }
    val asking get() = step < 3
    val ciDone get() = step >= 3
    val levelIndex get() = ans.maxOrNull() ?: 0
    val level: Level
        get() {
            val t = tx
            return when (levelIndex) {
                0 -> Level(t["lvl0"], t["lvl0caps"], t["lvl0t"], t["lvl0b"], Ms.GreenBg, Ms.GreenFg, Ms.GreenDot)
                1 -> Level(t["lvl1"], t["lvl1caps"], t["lvl1t"], t["lvl1b"], Ms.AmberBg, Ms.AmberFg, Ms.AmberDot)
                else -> Level(t["lvl2"], t["lvl2caps"], t["lvl2t"], t["lvl2bLive"], Ms.Red, Color.White, Ms.Red)
            }
        }
    val medWarn get() = !asking && (ans.getOrNull(2) ?: 0) > 0
    fun answer(lvl: Int) {
        ans.add(lvl); step += 1; listening = false
        if (ciDone && isPatient) {
            pendingCheckin = true; lastCheckinId = null; sentNote = ""
            send("Check-in")
        }
        if (AUTO_CALL_ON_RED && step >= 3 && levelIndex == 2 && isPatient) armCall()      // red -> start the 10 s countdown
    }
    fun resetCi() {
        cancelCall(); callPhase = CallPhase.Idle
        step = 0; ans.clear(); listening = false; note = ""; noteSaved = ""
        lastCheckinId = null; sentNote = ""; pendingCheckin = false
    }
    fun saveNote() {
        if (note.isBlank()) return
        noteSaved = note.trim(); note = ""
        send("Note") // goes with the check-in, or as an update if that was already sent
    }

    // ---------- Automatic red-alert call (from the patient's own phone) ----------
    var callPhase by mutableStateOf(CallPhase.Idle)
    var countdown by mutableIntStateOf(CALL_COUNTDOWN_SECONDS)
    var callIdx by mutableIntStateOf(0)
    var dialRequest by mutableStateOf<String?>(null)     // MainActivity places the call when this is set
    var askedCallPerm by mutableStateOf(false)
    private var countJob: Job? = null

    /**
     * Family with a saved number. Those who can approve are called first, then view-only members:
     * in an emergency anyone the patient added should be reachable.
     */
    val callers get() = members.filter { !it.you && it.phone.isNotBlank() }.sortedByDescending { it.role == "approve" }
    val callTarget: Member? get() = callers.getOrNull(callIdx)
    val hasNextCaller get() = callIdx + 1 < callers.size

    fun armCall() { callIdx = 0; startCountdown(CALL_COUNTDOWN_SECONDS) }

    private fun startCountdown(seconds: Int) {
        countJob?.cancel()
        if (callTarget == null) { callPhase = CallPhase.NoOne; return }
        callPhase = CallPhase.Counting
        countdown = seconds
        countJob = viewModelScope.launch {
            while (countdown > 0) { delay(1000); countdown -= 1 }
            dial()
        }
    }

    private fun dial() {
        val target = callTarget ?: return
        callPhase = CallPhase.Dialed
        dialRequest = target.phone
    }

    fun callNow() { countJob?.cancel(); dial() }

    private var lastHelpAt = 0L

    /**
     * The hidden "Get help now" tap on the red result: calls the first family number at once, no countdown.
     * Taps within 3 seconds of the last one are ignored so a double tap can't dial twice.
     */
    fun helpNow(nowMs: Long = System.currentTimeMillis()) {
        if (nowMs - lastHelpAt < 3000) return
        lastHelpAt = nowMs
        countJob?.cancel()
        callIdx = 0
        if (callTarget == null) { callPhase = CallPhase.NoOne; return }
        dial()
    }
    fun cancelCall() { countJob?.cancel(); if (callPhase == CallPhase.Counting) callPhase = CallPhase.Cancelled }
    fun callAgain() { dial() }
    fun callNext() { if (hasNextCaller) { callIdx += 1; startCountdown(NEXT_CALL_COUNTDOWN_SECONDS) } }

    /** +91 for 10-digit Indian numbers; keeps an explicit country code otherwise. */
    fun normalizePhone(raw: String): String {
        val d = digits(raw)
        return when {
            d.length == 10 -> "+91$d"
            d.length == 12 && d.startsWith("91") -> "+$d"
            d.length > 10 -> "+$d"
            else -> d
        }
    }

    // ---------- Help ----------
    var rawPlaces = mutableStateListOf<Place>()
    /** Places found near the phone, with the hospital that discharged the patient listed first. */
    val places: List<Place>
        get() {
            val list = rawPlaces.toMutableList()
            val own = hospitalName
            if (own.isNotBlank() && list.none { it.name.equals(own, ignoreCase = true) }) {
                list.add(0, Place(DISCHARGE_HOSPITAL_ID, "hosp", own, tx["yourHospital"], "", "", tx["knows"]))
            }
            return list.filter { filter == "all" || it.type == filter }
        }

    // ---------- Bills ----------
    /** Bill lines the AI marked as worth asking the billing desk about, each with a ready-to-send question. */
    val flags: List<Flag>
        get() {
            val t = tx
            return billData?.items.orEmpty().filter { it.worthAsking }.map { item ->
                val amt = rupees(item.amount)
                val reason = item.askReason.ifBlank { t["askDefault"] }
                Flag("b${item.id}", item.description, amt, reason, item.explanation.ifBlank { reason },
                    "Hello, this is $me, family of $patientFullName. On the final bill, \"${item.description}\" is charged $amt. $reason Thank you.")
            }
        }

    val billRows: List<Pair<String, String>> get() = billData?.items.orEmpty().map { it.description to rupees(it.amount) }
    val billTotalFormatted: String get() = rupees(billData?.total ?: 0.0)

    /** "01-10-2026 to 06-10-2026": the stay the bill is for, from the discharge summary. */
    val stayLabel: String
        get() = listOf(dischargeCardData?.admissionDate.orEmpty(), dischargeCardData?.dischargeDate.orEmpty())
            .filter { it.isNotBlank() }.joinToString(" – ")

    /** Marks a billing question as approved and hands its text to the phone's share sheet. */
    fun sendQuery(flag: Flag) {
        sent[flag.id] = true
        shareRequest = flag.draft
    }

    /** Text waiting to be shared (WhatsApp, email...). MainActivity opens the share sheet and clears it. */
    var shareRequest by mutableStateOf<String?>(null)

    /** The hospital named on the discharge summary, for the bill header. */
    val hospitalName: String get() = dischargeCardData?.hospital.orEmpty()

    val unsent get() = flags.count { sent[it.id] != true }

    // ---------- Claim ----------
    /** Claim papers: which ones have been uploaded and read. */
    val checklist: List<CheckItem>
        get() {
            val t = tx
            return CLAIM_PAPERS.map { (type, label, _) ->
                val docs = caseDocuments.filter { it.docType == type }
                val sub = when {
                    docs.any { it.status == "ready" } -> t["paperReady"].replace("{n}", docs.count { it.status == "ready" }.toString())
                    docs.any { it.status == "processing" } -> t["paperReading"]
                    docs.isNotEmpty() -> t["paperFailed"]
                    else -> t["paperMissing"]
                }
                CheckItem(t[label], sub, docs.any { it.status == "ready" })
            }
        }
    private val requiredPapers get() = CLAIM_PAPERS.count { it.third }
    val missing get() = CLAIM_PAPERS.indices.count { CLAIM_PAPERS[it].third && !checklist[it].done }

    /** The AI-drafted claim letter. Nothing is marked sent until a family member approves it. */
    var claimDraft by mutableStateOf<ClaimDraftModel?>(null)
    var draftBusy by mutableStateOf(false)
    var draftError by mutableStateOf<String?>(null)
    val approved get() = claimDraft?.status == "approved" || claimDraft?.status == "sent"

    /** Where the claim is, from what has really happened: label, detail, done. */
    val claimSteps: List<Triple<String, String, Boolean>>
        get() {
            val t = tx
            val status = claimDraft?.status
            return listOf(
                Triple(t["csPapers"], t["csPapersSub"].replace("{n}", (requiredPapers - missing).toString()).replace("{of}", requiredPapers.toString()), missing == 0),
                Triple(t["csCoverage"], coverage?.let { t["csCoverageDone"].replace("{amt}", rupees(it.estimatedClaimable)) } ?: t["csCoverageWait"], coverage != null),
                Triple(t["csLetter"], when (status) { null -> t["csLetterNone"]; "draft" -> t["csLetterDraft"]; else -> t["csLetterOk"] }, approved),
                Triple(t["csSent"], if (status == "sent") t["csSentDone"] else t["csSentWait"], status == "sent"),
            )
        }
    val track: List<Pair<String, String>> get() = claimSteps.map { it.first to it.second }
    val curStep get() = claimSteps.indexOfFirst { !it.third }.let { if (it < 0) claimSteps.size else it }

    /** When the claim must reach the insurer, from the policy's deadline and the discharge date. */
    val claimDeadline: Pair<String, String>?
        get() {
            val text = policy?.claimDeadline?.takeIf { it.isNotBlank() } ?: return null
            val days = Regex("(\\d+)\\s*days").find(text)?.groupValues?.get(1)?.toIntOrNull()
            val discharged = dischargeCardData?.dischargeDate?.let(::parseDocDate)
            if (days == null || discharged == null) return tx["deadlineLbl"] to text
            val due = discharged.plusDays(days.toLong())
            val left = java.time.temporal.ChronoUnit.DAYS.between(LocalDate.now(), due)
            val date = due.format(java.time.format.DateTimeFormatter.ofPattern("d MMM yyyy", java.util.Locale.ENGLISH))
            return tx["submitByLive"].replace("{date}", date) to
                (if (left >= 0) tx["daysLeftLive"].replace("{n}", left.toString()) else tx["deadlinePassed"])
        }

    /** Asks the AI to draft the claim letter from this case's papers. */
    fun prepareClaimLetter() {
        if (draftBusy) return
        draftBusy = true; draftError = null
        viewModelScope.launch {
            try {
                val id = syncLock.withLock { ensureSession() } ?: throw java.io.IOException(tx["noCaseYet"])
                val json = Backend.prepareClaimDraft(id)
                claimDraftJson = json.toString(); claimDraft = parseDraft(json)
            } catch (e: Exception) {
                Log.w("MedSure", "Claim letter failed", e)
                draftError = e.message ?: "Could not reach the MedSure server"
            } finally {
                draftBusy = false
            }
        }
    }

    /** The family approves the letter; only then is it marked sent and handed to the share sheet. */
    fun approveClaim() {
        val draft = claimDraft ?: return
        if (missing > 0 || draftBusy) return
        draftBusy = true; draftError = null
        viewModelScope.launch {
            try {
                val json = Backend.approveAndSendDraft(draft.id, alreadyApproved = draft.status == "approved")
                claimDraftJson = json.toString(); claimDraft = parseDraft(json)
                sheet = null; ftab = FTab.Claim
                shareRequest = draft.body
            } catch (e: Exception) {
                Log.w("MedSure", "Claim approval failed", e)
                draftError = e.message ?: "Could not reach the MedSure server"
            } finally {
                draftBusy = false
            }
        }
    }

    // ---------- Recovery ----------
    /** Check-in results by day, newest last. */
    val checkinDays = mutableStateListOf<CheckinDay>()

    /** The last seven days ending today: weekday letter and that day's result (null: no check-in). */
    val week: List<Pair<String, Int?>>
        get() {
            val today = LocalDate.now()
            val mine = if (isPatient && ciDone) levelIndex else null // today's answer shows before it has synced
            return (6 downTo 0).map { back ->
                val day = today.minusDays(back.toLong())
                val level = checkinDays.lastOrNull { it.day == day }?.level ?: mine.takeIf { back == 0 }
                day.dayOfWeek.getDisplayName(java.time.format.TextStyle.SHORT, java.util.Locale.ENGLISH) to level
            }
        }

    /** Amber and red check-ins from the last seven days, newest first. */
    val flaggedDays: List<CheckinDay> get() = checkinDays.filter { it.level > 0 && it.day >= LocalDate.now().minusDays(6) }.reversed()

    // ---------- Family home ----------
    val approvals: List<Approval>
        get() {
            val t = tx
            val list = mutableListOf<Approval>()
            if (hasCaseData && !approved) list += Approval(t["apClaimLive"], if (missing > 0) "$missing ${t["apMissing"]}" else t["apAllIn"]) { ftab = FTab.Claim }
            if (unsent > 0) list += Approval("$unsent ${t["apBills"]}", t["apBillsSub"]) { ftab = FTab.Bills }
            return list
        }
    val famHead: String
        get() = when {
            !ciDone -> named("fh0n")
            levelIndex == 0 -> named("fh1n")
            levelIndex == 1 -> named("fh2n")
            else -> named("fh3n")
        }

    // ---------- Persistence ----------
    // Everything the screens need is written to the phone, so closing or restarting the app loses nothing.
    private val prefs = app.getSharedPreferences("medsure_state", Context.MODE_PRIVATE)

    private fun today() = LocalDate.now().toString()
    private fun JSONObject.str(key: String): String? = if (isNull(key)) null else getString(key)
    private fun JSONObject.int(key: String): Int? = if (isNull(key)) null else getInt(key)

    private fun docJson(d: UploadedDoc) =
        JSONObject().put("uri", d.uri.toString()).put("name", d.name).put("size", d.sizeBytes).put("mime", d.mimeType).put("ocr", d.ocrText)
    private fun docOf(o: JSONObject) =
        UploadedDoc(Uri.parse(o.getString("uri")), o.getString("name"), o.getLong("size"), o.getString("mime"), o.str("ocr"))
    private fun <T> JSONArray.mapObjects(f: (JSONObject) -> T): List<T> = List(length()) { f(getJSONObject(it)) }

    private fun snapshot(): JSONObject = JSONObject()
        .put("v", STATE_VERSION).put("day", today())
        .put("sessionStale", sessionStale).put("pendingCheckin", pendingCheckin).put("stateDirty", stateDirty).put("sentNote", sentNote)
        // Every stage is saved as it is. Processing resumes reading the papers; uploads are not repeated.
        // The one-time codes on the Otp screen are never saved, so that screen comes back empty.
        .put("stage", stage.name).put("loginRole", loginRole.name)
        .put("overlay", overlay?.name).put("prevOverlay", prevOverlay?.name).put("sheet", sheet?.name).put("qid", qid)
        .put("fName", fName).put("fRel", fRel).put("fRole", fRole).put("fPhone", fPhone).put("fEmail", fEmail)
        .put("lang", lang).put("role", role.name).put("phone", phone).put("email", email)
        .put("ptab", ptab.name).put("ftab", ftab.name)
        .put("members", JSONArray(members.map {
            JSONObject().put("name", it.name).put("rel", it.rel).put("role", it.role).put("you", it.you).put("phone", it.phone)
        }))
        .put("taken", JSONObject(taken.toMap())).put("step", step).put("ans", JSONArray(ans.toList()))
        .put("note", note).put("noteSaved", noteSaved).put("lastCheckinId", lastCheckinId)
        .put("care", care).put("filter", filter).put("chosen", chosen).put("share", share)
        .put("sent", JSONObject(sent.toMap())).put("k4", k4).put("k5", k5)
        .put("medChange", medChange).put("plan", plan).put("plus", plus)
        .put("onboardingStep", onboardingStep).put("onbFullName", onbFullName).put("onbAge", onbAge)
        .put("onbGender", onbGender).put("onbBloodGroup", onbBloodGroup)
        .put("onbReports", JSONArray(onbReports.map(::docJson))).put("onbBills", JSONArray(onbBills.map(::docJson)))
        .put("onbInsCompany", onbInsCompany).put("onbInsPolicy", onbInsPolicy).put("onbInsDoc", onbInsDoc?.let(::docJson))
        .put("onbFamilyMembers", JSONArray(onbFamilyMembers.map {
            JSONObject().put("name", it.name).put("phone", it.phone).put("canApprove", it.canApprove)
        }))
        .put("caseId", caseId).put("askedCallPerm", askedCallPerm)
        .put("uploadedDocs", JSONObject(uploadedDocs.toMap())).put("patientName", patientName)
        // What the backend read from the documents, exactly as it sent it.
        .put("cardJson", cardJson).put("billJson", billJson).put("coverageJson", coverageJson).put("documentsJson", documentsJson)
        .put("policyJson", policyJson).put("claimDraftJson", claimDraftJson)
        .put("checkinDays", JSONArray(checkinDays.map { JSONObject().put("day", it.day.toString()).put("level", it.level).put("note", it.note) }))

    /** Writes the current state to the phone. Also runs by itself shortly after anything changes. */
    fun save() {
        prefs.edit().putString("state", snapshot().toString()).apply()
    }

    private fun restore() {
        val o = JSONObject(prefs.getString("state", null) ?: return)
        if (o.optInt("v") != STATE_VERSION) return // saved by an older build: start clean
        lang = o.str("lang")
        role = if (o.optString("role") == Role.Family.name) Role.Family else Role.Patient
        loginRole = if (o.optString("loginRole", role.name) == Role.Family.name) Role.Family else Role.Patient
        phone = o.optString("phone"); email = o.optString("email")
        ptab = PTab.entries.firstOrNull { it.name == o.optString("ptab") } ?: PTab.Today
        ftab = FTab.entries.firstOrNull { it.name == o.optString("ftab") } ?: FTab.Home
        o.optJSONArray("members")?.let { arr ->
            members.clear()
            members.addAll(arr.mapObjects { Member(it.getString("name"), it.getString("rel"), it.getString("role"), it.getBoolean("you"), it.optString("phone")) })
        }
        care = o.optString("care", care); filter = o.optString("filter", filter); chosen = o.str("chosen"); share = o.optBoolean("share", share)
        o.optJSONObject("sent")?.let { m -> sent.clear(); m.keys().forEach { sent[it] = m.getBoolean(it) } }
        k4 = o.optBoolean("k4"); k5 = o.optBoolean("k5")
        medChange = o.optString("medChange", medChange); plan = o.optString("plan", plan); plus = o.optBoolean("plus")
        onboardingStep = o.optInt("onboardingStep", 1).coerceIn(1, 4)
        onbFullName = o.optString("onbFullName"); onbAge = o.optString("onbAge")
        onbGender = o.str("onbGender"); onbBloodGroup = o.str("onbBloodGroup")
        o.optJSONArray("onbReports")?.let { onbReports.clear(); onbReports.addAll(it.mapObjects(::docOf)) }
        o.optJSONArray("onbBills")?.let { onbBills.clear(); onbBills.addAll(it.mapObjects(::docOf)) }
        onbInsCompany = o.optString("onbInsCompany"); onbInsPolicy = o.optString("onbInsPolicy")
        onbInsDoc = o.optJSONObject("onbInsDoc")?.let(::docOf)
        o.optJSONArray("onbFamilyMembers")?.let { arr ->
            onbFamilyMembers.clear()
            onbFamilyMembers.addAll(arr.mapObjects { OnboardingFamilyMember(it.getString("name"), it.getString("phone"), it.getBoolean("canApprove")) })
        }
        caseId = o.int("caseId"); askedCallPerm = o.optBoolean("askedCallPerm")
        o.optJSONObject("uploadedDocs")?.let { m -> uploadedDocs.clear(); m.keys().forEach { uploadedDocs[it] = m.getInt(it) } }
        patientName = o.optString("patientName")
        // A piece that fails to parse is dropped on its own; the next refresh fetches it again.
        cardJson = o.str("cardJson")?.also { runCatching { dischargeCardData = parseDischargeCard(JSONObject(it)) } }
        billJson = o.str("billJson")?.also { runCatching { billData = parseBill(JSONObject(it)).takeIf { b -> b.items.isNotEmpty() } } }
        coverageJson = o.str("coverageJson")?.also { runCatching { coverage = parseCoverage(JSONObject(it)) } }
        documentsJson = o.str("documentsJson")?.also { runCatching { setDocuments(parseDocuments(JSONArray(it))) } }
        policyJson = o.str("policyJson")?.also { runCatching { policy = parsePolicy(JSONObject(it)) } }
        claimDraftJson = o.str("claimDraftJson")?.also { runCatching { claimDraft = parseDraft(JSONObject(it)) } }
        o.optJSONArray("checkinDays")?.let { arr ->
            runCatching {
                checkinDays.clear()
                checkinDays.addAll(arr.mapObjects { CheckinDay(LocalDate.parse(it.getString("day")), it.getInt("level"), it.optString("note")) })
            }
        }
        fName = o.optString("fName"); fRel = o.optString("fRel", fRel); fRole = o.optString("fRole", fRole)
        fPhone = o.optString("fPhone"); fEmail = o.optString("fEmail"); qid = o.optString("qid", qid)
        sessionStale = o.optBoolean("sessionStale", true); stateDirty = o.optBoolean("stateDirty")

        // Tablets taken and the check-in belong to one day; a new day starts fresh.
        if (o.optString("day") == today()) {
            o.optJSONObject("taken")?.let { m -> m.keys().forEach { taken[it] = m.getBoolean(it) } }
            o.optJSONArray("ans")?.let { arr -> ans.clear(); ans.addAll(List(arr.length()) { arr.getInt(it) }) }
            step = o.optInt("step").coerceIn(0, 3).coerceAtMost(ans.size)
            note = o.optString("note"); noteSaved = o.optString("noteSaved"); lastCheckinId = o.int("lastCheckinId")
            pendingCheckin = o.optBoolean("pendingCheckin"); sentNote = o.optString("sentNote")
        }
        // "Onboarding" used to stand for the Processing stage too; both names still restore correctly.
        stage = Stage.entries.firstOrNull { it.name == o.optString("stage") } ?: if (lang != null) Stage.Welcome else Stage.Lang
        if (stage == Stage.App) {
            // The open screen on top of the tabs: Settings, Add family member, language picker, or a bottom sheet.
            overlay = Overlay.entries.firstOrNull { it.name == o.str("overlay") }
            prevOverlay = Overlay.entries.firstOrNull { it.name == o.str("prevOverlay") }
            sheet = Sheet.entries.firstOrNull { it.name == o.str("sheet") }.takeIf { !isPatient }
        }
    }

    // Keep this last: every property above must exist before state is restored into it.
    init {
        try {
            restore()
        } catch (e: Exception) {
            Log.w("MedSure", "Saved state unreadable, starting fresh", e)
            prefs.edit().remove("state").apply()
        }
        viewModelScope.launch {
            snapshotFlow { snapshot().toString() }.collectLatest { json ->
                delay(400) // wait for a burst of changes to settle
                prefs.edit().putString("state", json).apply()
            }
        }
    }
}
