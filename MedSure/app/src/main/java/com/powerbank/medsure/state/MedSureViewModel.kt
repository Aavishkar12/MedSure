package com.powerbank.medsure.state

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.Color
import androidx.lifecycle.ViewModel
import com.powerbank.medsure.i18n.AllLanguages
import com.powerbank.medsure.i18n.Tx
import com.powerbank.medsure.ui.theme.Ms

enum class Stage { Lang, Welcome, Details, Otp, App }
enum class Role { Patient, Family }
enum class Overlay { Settings, LangPick, Add }
enum class PTab { Today, Care, Checkin, Help }
enum class FTab { Home, Meds, Bills, Claim, Care }
enum class Sheet { Query, Approve }

data class Member(val name: String, val rel: String, val role: String, val you: Boolean)

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
class MedSureViewModel : ViewModel() {
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

    fun verify() {
        if (!canVerify) return
        if (loginRole == Role.Family) {
            if (members.isEmpty()) members.add(Member("Arjun", "son", "approve", true))
            else members.indices.forEach { i -> members[i] = members[i].copy(you = i == 0) }
        } else {
            members.indices.forEach { i -> members[i] = members[i].copy(you = false) }
        }
        role = loginRole
        overlay = null; ptab = PTab.Today; ftab = FTab.Home
        stage = Stage.App
    }

    fun logout() {
        stage = Stage.Welcome; overlay = null; otpP = ""; otpE = ""; sheet = null
        ptab = PTab.Today; ftab = FTab.Home
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

    val canAdd get() = fName.isNotBlank() && !(isPatient && members.isNotEmpty())

    fun submitAdd() {
        if (!canAdd) return
        members.add(Member(fName.trim(), fRel, if (isPatient) "approve" else fRole, false))
        overlay = if (prevOverlay == Overlay.Settings) Overlay.Settings else null
    }

    val me: String get() = if (isPatient) "Lakshmi" else (members.firstOrNull { it.you }?.name ?: "Arjun")

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
    fun answer(lvl: Int) { ans.add(lvl); step += 1; listening = false }
    fun resetCi() { step = 0; ans.clear(); listening = false; note = ""; noteSaved = "" }
    fun saveNote() { if (note.isNotBlank()) { noteSaved = note.trim(); note = "" } }

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
}
