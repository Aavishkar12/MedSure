package com.powerbank.medsure.ui.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.powerbank.medsure.state.MedSureViewModel
import com.powerbank.medsure.state.Overlay
import com.powerbank.medsure.ui.auth.LanguageGrid
import com.powerbank.medsure.ui.components.*
import com.powerbank.medsure.ui.family.FamilyCircleList
import com.powerbank.medsure.ui.theme.Ms

@Composable
private fun VerifiedPill(text: String) =
    T(text, 12, 800, Ms.GreenFg, Modifier.clip(RoundedCornerShape(999.dp)).background(Ms.GreenBg).padding(horizontal = 10.dp, vertical = 5.dp))

@Composable
fun SettingsScreen(vm: MedSureViewModel) {
    val t = vm.tx
    val p = vm.isPatient
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        D(t["settings"], 34)

        Caps(t["profile"])
        MsCard(gap = 14.dp) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                Tick(56.dp, if (p) Ms.Ink else Ms.Marigold) { T(vm.me.take(1), 22, 800, if (p) Ms.Paper else Ms.Ink) }
                Column {
                    D(if (p) "Lakshmi R" else vm.me, 22)
                    T(if (p) t["signedPatient"] else t["signedFamily"], 14, 400, Ms.Muted)
                }
            }
            Rule(Ms.Blister)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) { T(t["mobile"], 13, 400, Ms.Muted); T("+91 " + vm.phone.ifBlank { "98765 43210" }, 15, 600) }
                VerifiedPill(t["verified"])
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) { T(t["email"], 13, 400, Ms.Muted); T(vm.email.ifBlank { "name@example.com" }, 15, 600) }
                VerifiedPill(t["verified"])
            }
        }

        Caps(t["language"])
        MsCard(onClick = { vm.overlay = Overlay.LangPick }) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                Ico(LineIcons.Globe, Ms.Ink)
                Column(Modifier.weight(1f)) {
                    T(vm.langNative, 17, 700)
                    T(t["langChange"], 14, 400, Ms.Muted)
                }
                Ico(LineIcons.ChevronRight, Ms.Ink, 18.dp)
            }
        }

        if (p) {
            Caps(t["familyMember"])
            val h = vm.members.firstOrNull()
            if (h == null) {
                MsCard(gap = 10.dp) {
                    T(t["addFamBody"], 15, 400, Ms.Text3, lh = 1.5f)
                    MsButton(t["addFamBtn"], BtnKind.Primary, Modifier.fillMaxWidth()) { vm.openAdd() }
                }
            } else {
                MsCard(gap = 10.dp) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Tick(44.dp, Ms.Marigold) { T(h.name.take(1).uppercase(), 15, 800) }
                        Column {
                            T("${h.name} · ${vm.relLabel(h.rel)}", 15, 700)
                            T(t["helperSub"], 14, 400, Ms.Muted)
                        }
                    }
                    T(t["askToAdd"], 14, 400, Ms.Muted)
                }
            }
        } else {
            Caps(t["familyCircle"])
            MsCard(gap = 12.dp) {
                FamilyCircleList(vm)
                MsButton(t["invite"], BtnKind.Light, Modifier.fillMaxWidth(), height = 46.dp) { vm.openAdd() }
            }
            Caps("MEDSURE+", modifier = Modifier.padding(top = 6.dp))
            PlusCard(vm)
        }

        MsButton(
            t["logout"], BtnKind.Ghost, Modifier.fillMaxWidth().padding(top = 6.dp), icon = LineIcons.LogOut,
            borderColor = Ms.Red, textColor = Ms.Red,
        ) { vm.logout() }
    }
}

@Composable
private fun PlusCard(vm: MedSureViewModel) {
    val t = vm.tx
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(24.dp)).background(Ms.Ink).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Row { D("MedSure", 28, color = Ms.Paper); D("+", 28, color = Ms.Marigold) }
            T(
                if (vm.plus) t["plusActive"] else t["onFree"], 12, 800, if (vm.plus) Ms.Ink else Ms.OnDark,
                Modifier.clip(RoundedCornerShape(999.dp)).background(if (vm.plus) Ms.Marigold else Ms.PlusBadge).padding(horizontal = 10.dp, vertical = 5.dp),
            )
        }
        T(t["plusSub"], 15, 400, Ms.OnDark)
        listOf(t["plusF1"], t["plusF2"], t["plusF3"], t["plusF4"]).forEach { f ->
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Ico(LineIcons.Check, Ms.Marigold, 18.dp, Modifier.padding(top = 2.dp)); T(f, 15, 400, Ms.Paper)
            }
        }
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf(
                Triple("stay", t["planStay"], t["priceStay"]),
                Triple("month", t["planMonth"], t["priceMonth"]),
                Triple("win", t["planWin"], t["priceWin"]),
            ).forEach { (id, label, price) ->
                val sel = vm.plan == id
                val shape = RoundedCornerShape(16.dp)
                Row(
                    Modifier.fillMaxWidth().heightIn(min = 56.dp).clip(shape).background(if (sel) Ms.PlusSel else Color.Transparent)
                        .border(1.5.dp, if (sel) Ms.Marigold else Ms.PlusLine, shape)
                        .pressable { vm.plan = id }.padding(horizontal = 14.dp, vertical = 10.dp),
                    horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically,
                ) {
                    T(label, 15, 700, Ms.Paper, Modifier.weight(1f))
                    T(price, 14, 700, Ms.Marigold)
                }
            }
        }
        if (!vm.plus) MsButton(t["tryPlus"], BtnKind.Mari, Modifier.fillMaxWidth()) { vm.plus = true }
        T(t["plusFree"], 13, 400, Ms.OnDark, lh = 1.45f)
    }
}

@Composable
fun LangPickScreen(vm: MedSureViewModel, modifier: Modifier = Modifier) {
    val t = vm.tx
    Column(modifier, verticalArrangement = Arrangement.spacedBy(14.dp)) {
        D(t["langTitle"], 30)
        LanguageGrid(vm, Modifier.weight(1f), footer = { T(t["langNote"], 13, 400, Ms.Muted, lh = 1.45f) })
        MsButton(t["done"], BtnKind.Primary, Modifier.fillMaxWidth()) { vm.overlay = Overlay.Settings }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun AddMemberScreen(vm: MedSureViewModel) {
    val t = vm.tx
    val p = vm.isPatient
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        D(if (p) t["addTitleP"] else t["addTitleF"], 30)
        T(if (p) t["addSubP"] else t["addSubF"], 15, 400, Ms.Text3, lh = 1.5f)
        Field(t["name"], vm.fName, { vm.fName = it }, "Arjun")
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            T(t["relation"], 14, 700, Ms.Text3)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("son" to t["rSon"], "daughter" to t["rDaughter"], "spouse" to t["rSpouse"], "other" to t["rOther"]).forEach { (id, label) ->
                    Chip(label, vm.fRel == id) { vm.fRel = id }
                }
            }
        }
        Field(t["mobile"], vm.fPhone, { vm.fPhone = it }, "+91 98765 43210", keyboard = KeyboardType.Phone)
        Field(t["email"], vm.fEmail, { vm.fEmail = it }, "name@example.com", keyboard = KeyboardType.Email)
        if (!p) {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                T(t["roleLbl"], 14, 700, Ms.Text3)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Chip(t["roleApprove"], vm.fRole == "approve") { vm.fRole = "approve" }
                    Chip(t["roleView"], vm.fRole == "view") { vm.fRole = "view" }
                }
            }
        }
        T(t["inviteNote"], 14, 400, Ms.Muted)
        MsButton(t["sendInvite"], BtnKind.Primary, Modifier.fillMaxWidth(), enabled = vm.canAdd) { vm.submitAdd() }
    }
}

// ====================== SHEETS ======================

@Composable
fun SheetHeader(title: String, onClose: () -> Unit) {
    Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
        Box(Modifier.size(44.dp, 5.dp).clip(RoundedCornerShape(999.dp)).background(Ms.Handle))
    }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        D(title, 22, modifier = Modifier.weight(1f))
        IconBtn(LineIcons.Close, "Close", onClose)
    }
}

@Composable
fun QuerySheetContent(vm: MedSureViewModel) {
    val t = vm.tx
    val f = vm.flags.firstOrNull { it.id == vm.qid } ?: vm.flags.first()
    val sent = vm.sent[f.id] == true
    SheetHeader(f.label) { vm.sheet = null }
    T("${t["whyFlag"]}${f.why}", 15, 400, Ms.Brown, Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(Ms.FlagBg).padding(14.dp), lh = 1.5f)
    Caps(t["draftTo"], size = 12)
    MsCard { T(f.draft, 15, 400, lh = 1.55f) }
    if (sent) {
        T(t["sentEmail"], 15, 600, Ms.GreenFg, Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Ms.GreenBg).padding(14.dp))
    } else {
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            MsButton(t["edit"], BtnKind.Light, Modifier.weight(1f)) {}
            MsButton(t["approveSend"], BtnKind.Primary, Modifier.weight(1f)) { vm.sent[f.id] = true }
        }
    }
    T(t["nothingLeaves"], 13, 400, Ms.Muted, Modifier.fillMaxWidth(), align = TextAlign.Center)
}

@Composable
fun ApproveSheetContent(vm: MedSureViewModel) {
    val t = vm.tx
    SheetHeader(t["packet"]) { vm.sheet = null }
    MsCard(gap = 10.dp) {
        SheetRow(t["claimed"], "₹1,84,350")
        SheetRow(t["notPayable"], "− ₹4,920")
        SheetRow(t["docsAttached"], "${6 - vm.missing} ${t["ofSix"]}")
    }
    Caps(t["coverNote"], size = 12)
    MsCard {
        T(
            "Cashless was declined on 24 Sep because documents were incomplete at admission. We are now claiming reimbursement for Lakshmi's stay from 24 to 29 Sep, with all reports, bills and the completed claim form attached.",
            15, 400, lh = 1.55f,
        )
    }
    if (vm.missing > 0) {
        T(t["missingMsg"], 15, 600, Ms.Brown, Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Ms.FlagBg).padding(14.dp))
    }
    MsButton(t["approveIns"], BtnKind.Primary, Modifier.fillMaxWidth(), enabled = vm.missing == 0) { vm.approveClaim() }
    T(t["nothingLeaves"], 13, 400, Ms.Muted, Modifier.fillMaxWidth(), align = TextAlign.Center)
}

@Composable
private fun SheetRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        T(label, 15, modifier = Modifier.weight(1f)); T(value, 15, 700)
    }
}
