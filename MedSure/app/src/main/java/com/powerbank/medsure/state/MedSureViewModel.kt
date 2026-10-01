package com.powerbank.medsure.state

import android.app.Application
import android.content.Context
import android.net.Uri
import androidx.compose.runtime.getValue
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
import com.powerbank.medsure.i18n.AllLanguages
import com.powerbank.medsure.i18n.Tx
import com.powerbank.medsure.net.Backend
import com.powerbank.medsure.push.PushBus
import com.powerbank.medsure.ui.theme.Ms
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
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

data class Dose(
    val id: String, val name: String, val time: String, val what: String, val why: String, val taken: Boolean,
)

data class Level(
    val name: String, val caps: String, val title: String, val body: String,
    val bg: Color, val fg: Color, val dot: Color,
)

data class Place(
    val id: String, val type: String, val name: String, val meta: String, val dist: String, val open: String, val badge: String,
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
    val taken = mutableStateMapOf("d1" to true, "d2" to true, "d3" to false, "d4" to false)
    var step by mutableIntStateOf(0)
    val ans = mutableStateListOf<Int>()
    var listening by mutableStateOf(false)
    var care by mutableStateOf("watch")
    var reading by mutableStateOf(false)
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
    var approved by mutableStateOf(false)
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

    fun verify() {
        if (!canVerify) return
        if (loginRole == Role.Family) {
            if (members.isEmpty()) members.add(Member("Arjun", "son", "approve", true, phone = normalizePhone(phone)))
            else members.indices.forEach { i -> members[i] = members[i].copy(you = i == 0) }
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
        val name = me
        sync("Sign-in") {
            Backend.signIn()
            Backend.saveProfile(name, phone, email) // also joins any case this phone or email was invited to
            caseId = Backend.firstCaseId()
            Backend.registerDevice()
        }
    }

    /** Sends what the patient entered during onboarding: their name, their case and the helpers they added. */
    private fun saveOnboarding() {
        val name = onbFullName.trim().ifEmpty { me }
        val helpers = onbFamilyMembers.toList()
        helpers.forEach { h ->
            if (members.none { it.name == h.name && it.phone == h.phone }) {
                members.add(Member(h.name, "other", if (h.canApprove) "approve" else "view", false, normalizePhone(h.phone)))
            }
        }
        sync("Onboarding") {
            Backend.signIn()
            Backend.saveProfile(name, phone, email)
            val id = caseId ?: Backend.firstCaseId() ?: Backend.createCase(name, "self")
            caseId = id
            helpers.forEach { Backend.addMember(id, it.name, "family", it.canApprove, it.phone, "") }
            Backend.registerDevice()
        }
    }

    fun logout() {
        cancelCall(); callPhase = CallPhase.Idle
        stage = Stage.Welcome; overlay = null; otpP = ""; otpE = ""; sheet = null
        ptab = PTab.Today; ftab = FTab.Home; onboardingStep = 1
        caseId = null; lastCheckinId = null
        sync("Sign-out") { Backend.signOut() }
    }

    // ---------- Backend ----------
    /** The case this user is on, once the backend has confirmed it. */
    var caseId by mutableStateOf<Int?>(null)

    /** Today's check-in on the backend, so a note added afterwards can be attached to it. */
    private var lastCheckinId by mutableStateOf<Int?>(null)

    init {
        viewModelScope.launch { PushBus.events.collect { refresh() } }
    }

    /** Pulls what other family members did. Called when the app comes to the front and when a push arrives. */
    fun refresh() {
        if (stage != Stage.App || !Backend.signedIn) return
        sync("Refresh") {
            // Family joins a case when the patient invites them, which can happen after they signed in.
            val id = caseId ?: Backend.firstCaseId()?.also { caseId = it } ?: return@sync
            // Family sees the patient's latest check-in from today: answers, result and note.
            if (!isPatient) {
                val latest = Backend.latestCheckin(id)
                if (latest != null && latest.isToday) {
                    if (ans.toList() != latest.levels) { ans.clear(); ans.addAll(latest.levels) }
                    step = 3
                    noteSaved = latest.note
                } else {
                    ans.clear(); step = 0; noteSaved = ""
                }
            }
        }
    }

    /** Runs a backend call without blocking the screens, which keep working if it fails. */
    private fun sync(what: String, block: suspend () -> Unit) {
        viewModelScope.launch {
            try { block() } catch (e: Exception) { Log.w("MedSure", "$what failed", e) }
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

        val id = caseId ?: return
        val (invitePhone, inviteEmail) = fPhone to fEmail
        sync("Invite") { Backend.addMember(id, added.name, added.rel, added.role == "approve", invitePhone, inviteEmail) }
    }

    val me: String get() = if (isPatient) onbFullName.trim().substringBefore(' ').ifEmpty { "Lakshmi" } else (members.firstOrNull { it.you }?.name ?: "Arjun")

    fun relLabel(rel: String) = tx["r" + rel.replaceFirstChar { it.uppercase() }]
    fun roleLabel(r: String) = if (r == "approve") tx["canApprove"] else tx["canView"]

    // ---------- Medicines ----------
    val doses: List<Dose>
        get() {
            val t = tx
            val changed = medChange == "approved"
            val base = listOf(
                Triple("d1", if (changed) "Furosemide 20 mg" else "Furosemide 40 mg", "dW" to "whyW"),
                Triple("d2", "Metoprolol 25 mg", "dH" to "whyH"),
                Triple("d3", "Spironolactone 25 mg", "dS" to "whyS"),
                Triple("d4", "Metoprolol 25 mg", "dH" to "whyH2"),
            )
            return base.mapIndexed { i, (id, name, keys) ->
                Dose(id, name, t.times[i], t[keys.first], t[keys.second], taken[id] == true)
            }
        }
    val takenCount get() = taken.values.count { it }
    fun toggleDose(id: String) { taken[id] = taken[id] != true }

    // ---------- Check-in ----------
    val questions: List<Pair<String, List<Pair<String, Int>>>>
        get() {
            val t = tx
            return listOf(
                t["q1"] to listOf(t["q1a"] to 0, t["q1b"] to 1, t["q1c"] to 2),
                t["q2"] to listOf(t["q2a"] to 0, t["q2b"] to 0, t["q2c"] to 1),
                t["q3"] to listOf(t["q3a"] to 0, t["q3b"] to 1, t["q3c"] to 1, t["q3d"] to 1),
            )
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
                else -> Level(t["lvl2"], t["lvl2caps"], t["lvl2t"], t["lvl2b"], Ms.Red, Color.White, Ms.Red)
            }
        }
    val medWarn get() = !asking && (ans.getOrNull(2) ?: 0) > 0
    fun answer(lvl: Int) {
        ans.add(lvl); step += 1; listening = false
        val id = caseId
        if (ciDone && id != null) {
            val levels = ans.toList()
            val sentNote = noteSaved
            sync("Check-in") {
                val checkinId = Backend.checkin(id, levels, sentNote) // family sees it; they are notified if it needs attention
                lastCheckinId = checkinId
                if (noteSaved != sentNote) Backend.updateCheckinNote(checkinId, noteSaved) // note typed while this was sending
            }
        }
        if (AUTO_CALL_ON_RED && step >= 3 && levelIndex == 2 && isPatient) armCall()      // red -> start the 10 s countdown
    }
    fun resetCi() { cancelCall(); callPhase = CallPhase.Idle; step = 0; ans.clear(); listening = false; note = ""; noteSaved = ""; lastCheckinId = null }
    fun saveNote() {
        if (note.isBlank()) return
        noteSaved = note.trim(); note = ""
        val checkinId = lastCheckinId ?: return // not sent yet: the note goes with the check-in itself
        val text = noteSaved
        sync("Note") { Backend.updateCheckinNote(checkinId, text) }
    }

    // ---------- Automatic red-alert call (from the patient's own phone) ----------
    var callPhase by mutableStateOf(CallPhase.Idle)
    var countdown by mutableIntStateOf(CALL_COUNTDOWN_SECONDS)
    var callIdx by mutableIntStateOf(0)
    var dialRequest by mutableStateOf<String?>(null)     // MainActivity places the call when this is set
    var askedCallPerm by mutableStateOf(false)
    private var countJob: Job? = null

    /** Family who can approve and have a saved number, in the order they were added. */
    val callers get() = members.filter { it.role == "approve" && it.phone.isNotBlank() }
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
    val places: List<Place>
        get() {
            val t = tx
            return listOf(
                Place("h1", "hosp", "[Your discharging hospital]", t["m1"], "4.6 km", t["o24"], t["knows"]),
                Place("h2", "hosp", "[Nearest 24×7 hospital]", t["m2"], "1.2 km", t["o24"], ""),
                Place("c1", "clinic", "[Nearest clinic]", t["m3"], "0.6 km", t["o9"], ""),
                Place("p1", "pharm", "[Nearest pharmacy]", t["m4"], "0.3 km", t["o10"], ""),
            ).filter { filter == "all" || it.type == filter }
        }

    // ---------- Bills ----------
    val flags: List<Flag>
        get() {
            val t = tx
            val n = me
            return listOf(
                Flag("f1", "Gloves, masks & kits ×38", "₹3,420", t["n1"], t["why1"],
                    "Hello, this is $n, family of Lakshmi (IP [NUMBER]). The final bill lists gloves, masks and kits 38 times for ₹3,420. Could you share the itemised list for these? Thank you."),
                Flag("f2", "ECG, listed twice on 26 Sep", "₹900", t["n2"], t["why2"],
                    "Hello, this is $n, family of Lakshmi (IP [NUMBER]). ECG appears twice on 26 Sep at ₹450 each. Could you confirm whether two ECGs were done that day? Thank you."),
                Flag("f3", "Admission & admin charges", "₹1,500", t["n3"], t["why3"],
                    "Hello, this is $n, family of Lakshmi (IP [NUMBER]). Could you explain what the ₹1,500 admission and admin charge covers? Thank you."),
            )
        }
    val billRows = listOf(
        "Room · 5 days" to "₹42,500", "ICU · 1 day" to "₹22,000", "Doctor & specialist visits" to "₹18,000",
        "Medicines & IV fluids" to "₹61,230", "Lab tests & scans" to "₹34,800",
    )
    val unsent get() = flags.count { sent[it.id] != true }

    // ---------- Claim ----------
    val checklist: List<CheckItem>
        get() {
            val t = tx
            return listOf(
                CheckItem(t["k1"], t["k1s"], true),
                CheckItem(t["k2"], t["k2s"], true),
                CheckItem(t["k3"], t["k3s"], true),
                CheckItem(t["k4"], if (k4) t["k4a"] else t["k4b"], k4, t["rescan"]) { k4 = true },
                CheckItem(t["k5"], if (k5) t["k5a"] else t["k5b"], k5, t["add"]) { k5 = true },
                CheckItem(t["k6"], t["k6s"], true),
            )
        }
    val missing get() = listOf(k4, k5).count { !it }
    val curStep get() = if (approved) 3 else 2
    val track: List<Pair<String, String>>
        get() {
            val t = tx
            return listOf(
                t["tr1"] to t["tr1s"], t["tr2"] to t["tr2s"],
                t["tr3"] to (if (approved) t["tr3a"] else t["tr3b"]),
                t["tr4"] to (if (approved) t["tr4a"] else t["tr4b"]),
                t["tr5"] to t["tr5s"],
            )
        }
    fun approveClaim() { if (missing == 0) { approved = true; sheet = null; ftab = FTab.Claim } }

    // ---------- Family home ----------
    val approvals: List<Approval>
        get() {
            val t = tx
            val list = mutableListOf<Approval>()
            if (medChange != "approved") list += Approval(t["apMed"], t["apMedSub"]) { ftab = FTab.Meds }
            if (!approved) list += Approval(t["apClaim"], if (missing > 0) "$missing ${t["apMissing"]}" else t["apAllIn"]) { sheet = Sheet.Approve }
            if (unsent > 0) list += Approval("$unsent ${t["apBills"]}", t["apBillsSub"]) { ftab = FTab.Bills }
            return list
        }
    val famHead: String
        get() = when {
            !ciDone -> tx["fh0"]
            levelIndex == 0 -> tx["fh1"]
            levelIndex == 1 -> tx["fh2"]
            else -> tx["fh3"]
        }

    // ---------- Persistence ----------
    // Everything the screens need is written to the phone, so closing or restarting the app loses nothing.
    private val prefs = app.getSharedPreferences("medsure_state", Context.MODE_PRIVATE)

    private fun today() = LocalDate.now().toString()
    private fun JSONObject.str(key: String): String? = if (isNull(key)) null else getString(key)
    private fun JSONObject.int(key: String): Int? = if (isNull(key)) null else getInt(key)

    private fun docJson(d: UploadedDoc) =
        JSONObject().put("uri", d.uri.toString()).put("name", d.name).put("size", d.sizeBytes).put("mime", d.mimeType)
    private fun docOf(o: JSONObject) = UploadedDoc(Uri.parse(o.getString("uri")), o.getString("name"), o.getLong("size"), o.getString("mime"))
    private fun <T> JSONArray.mapObjects(f: (JSONObject) -> T): List<T> = List(length()) { f(getJSONObject(it)) }

    private fun snapshot(): JSONObject = JSONObject()
        .put("day", today())
        .put("stage", when (stage) {
            Stage.App -> "App"
            Stage.Onboarding, Stage.Processing -> "Onboarding"
            Stage.Lang -> "Lang"
            else -> "Welcome"
        })
        .put("lang", lang).put("role", role.name).put("phone", phone).put("email", email)
        .put("ptab", ptab.name).put("ftab", ftab.name)
        .put("members", JSONArray(members.map {
            JSONObject().put("name", it.name).put("rel", it.rel).put("role", it.role).put("you", it.you).put("phone", it.phone)
        }))
        .put("taken", JSONObject(taken.toMap())).put("step", step).put("ans", JSONArray(ans.toList()))
        .put("note", note).put("noteSaved", noteSaved).put("lastCheckinId", lastCheckinId)
        .put("care", care).put("filter", filter).put("chosen", chosen).put("share", share)
        .put("sent", JSONObject(sent.toMap())).put("k4", k4).put("k5", k5).put("approved", approved)
        .put("medChange", medChange).put("plan", plan).put("plus", plus)
        .put("onboardingStep", onboardingStep).put("onbFullName", onbFullName).put("onbAge", onbAge)
        .put("onbGender", onbGender).put("onbBloodGroup", onbBloodGroup)
        .put("onbReports", JSONArray(onbReports.map(::docJson))).put("onbBills", JSONArray(onbBills.map(::docJson)))
        .put("onbInsCompany", onbInsCompany).put("onbInsPolicy", onbInsPolicy).put("onbInsDoc", onbInsDoc?.let(::docJson))
        .put("onbFamilyMembers", JSONArray(onbFamilyMembers.map {
            JSONObject().put("name", it.name).put("phone", it.phone).put("canApprove", it.canApprove)
        }))
        .put("caseId", caseId).put("askedCallPerm", askedCallPerm)

    /** Writes the current state to the phone. Also runs by itself shortly after anything changes. */
    fun save() {
        prefs.edit().putString("state", snapshot().toString()).apply()
    }

    private fun restore() {
        val o = JSONObject(prefs.getString("state", null) ?: return)
        lang = o.str("lang")
        role = if (o.optString("role") == Role.Family.name) Role.Family else Role.Patient
        loginRole = role
        phone = o.optString("phone"); email = o.optString("email")
        ptab = PTab.entries.firstOrNull { it.name == o.optString("ptab") } ?: PTab.Today
        ftab = FTab.entries.firstOrNull { it.name == o.optString("ftab") } ?: FTab.Home
        o.optJSONArray("members")?.let { arr ->
            members.clear()
            members.addAll(arr.mapObjects { Member(it.getString("name"), it.getString("rel"), it.getString("role"), it.getBoolean("you"), it.optString("phone")) })
        }
        care = o.optString("care", care); filter = o.optString("filter", filter); chosen = o.str("chosen"); share = o.optBoolean("share", share)
        o.optJSONObject("sent")?.let { m -> sent.clear(); m.keys().forEach { sent[it] = m.getBoolean(it) } }
        k4 = o.optBoolean("k4"); k5 = o.optBoolean("k5"); approved = o.optBoolean("approved")
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

        // Tablets taken and the check-in belong to one day; a new day starts fresh.
        if (o.optString("day") == today()) {
            o.optJSONObject("taken")?.let { m -> m.keys().forEach { taken[it] = m.getBoolean(it) } }
            o.optJSONArray("ans")?.let { arr -> ans.clear(); ans.addAll(List(arr.length()) { arr.getInt(it) }) }
            step = o.optInt("step").coerceIn(0, 3).coerceAtMost(ans.size)
            note = o.optString("note"); noteSaved = o.optString("noteSaved"); lastCheckinId = o.int("lastCheckinId")
        }
        stage = when (o.optString("stage")) {
            "App" -> Stage.App
            "Onboarding" -> Stage.Onboarding
            "Lang" -> Stage.Lang
            else -> if (lang != null) Stage.Welcome else Stage.Lang
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
