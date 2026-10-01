package com.powerbank.medsure.ui.family

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.unit.dp
import com.powerbank.medsure.state.FTab
import com.powerbank.medsure.state.MedSureViewModel
import com.powerbank.medsure.state.Sheet
import com.powerbank.medsure.ui.components.*
import com.powerbank.medsure.ui.theme.Ms

// ====================== HOME ======================

@Composable
fun FamilyCircleList(vm: MedSureViewModel) {
    val t = vm.tx
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        CircleRow("L", "Lakshmi", t["patientRole"], Ms.Ink, Ms.Paper)
        vm.members.forEachIndexed { i, m ->
            val bg = if (i % 2 == 1) Ms.Teal else Ms.Marigold
            val fg = if (i % 2 == 1) Color.White else Ms.Ink
            CircleRow(m.name.take(1).uppercase(), m.name + if (m.you) " ${t["you"]}" else "", vm.roleLabel(m.role), bg, fg)
        }
    }
}

@Composable
private fun CircleRow(initial: String, label: String, role: String, bg: Color, fg: Color) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.weight(1f)) {
            Tick(40.dp, bg) { T(initial, 15, 700, fg) }
            T(label, 15, 600)
        }
        T(role, 13, 700, Ms.Muted)
    }
}

@Composable
fun FamilyHomeScreen(vm: MedSureViewModel) {
    val t = vm.tx
    val L = vm.level
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Column(Modifier.padding(top = 6.dp)) {
            T(t["caring"], 14, 600, Ms.Muted)
            D(vm.famHead, 32, modifier = Modifier.padding(top = 4.dp))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.height(IntrinsicSize.Min)) {
            MsCard(Modifier.weight(1f).fillMaxHeight(), gap = 4.dp, onClick = { vm.ftab = FTab.Meds }) {
                T(t["medsCap"], 12, 800, Ms.Muted)
                D("${vm.takenCount}/4", 34)
                Box(Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(999.dp)).background(Ms.Blister)) {
                    Box(Modifier.fillMaxWidth(vm.takenCount / 4f).height(8.dp).clip(RoundedCornerShape(999.dp)).background(Ms.Teal))
                }
            }
            MsCard(
                Modifier.weight(1f).fillMaxHeight(), bg = if (vm.ciDone) L.bg else Ms.White,
                border = if (vm.ciDone) null else Ms.Line, gap = 4.dp,
            ) {
                val fg = if (vm.ciDone) L.fg else Ms.Ink
                T(t["ciCap"], 12, 800, fg)
                D(if (vm.ciDone) L.name else t["notYet"], 24, color = fg)
                T(if (vm.ciDone) t["fromAmma"] else t["remSent"], 13, 600, fg)
            }
        }
        D(t["waiting"], 22, modifier = Modifier.padding(top = 4.dp))
        val approvals = vm.approvals
        if (approvals.isEmpty()) MsCard { T(t["nothing"], 15, 400, Ms.Muted) }
        approvals.forEach { a ->
            MsCard(onClick = a.open) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                    Tick(44.dp, Ms.Marigold, shape = RoundedCornerShape(14.dp)) { Ico(LineIcons.File, Ms.Ink) }
                    Column(Modifier.weight(1f)) {
                        T(a.title, 16, 700)
                        T(a.sub, 14, 400, Ms.Muted)
                    }
                    Ico(LineIcons.ChevronRight, Ms.Ink, 18.dp)
                }
            }
        }
        D(t["familyCircle"], 22, modifier = Modifier.padding(top = 4.dp))
        MsCard(gap = 12.dp) {
            FamilyCircleList(vm)
            MsButton(t["invite"], BtnKind.Light, Modifier.fillMaxWidth(), height = 46.dp) { vm.openAdd() }
        }
    }
}

// ====================== MEDICINES ======================

@Composable
fun FamilyMedsScreen(vm: MedSureViewModel) {
    val t = vm.tx
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Column(Modifier.padding(top = 6.dp)) {
            D(t["fmTitle"], 32)
            T(t["fmSub"], 14, 400, Ms.Muted, Modifier.padding(top = 6.dp), lh = 1.45f)
        }
        when (vm.medChange) {
            "pending" -> Column(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(22.dp)).background(Ms.FlagBg)
                    .dashedBorder(Ms.FlagBorder, 1.5.dp, 22.dp).padding(18.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Caps(t["pendTitle"], Ms.AmberDark, 12)
                D(t["changeTxt"], 22, lh = 1.2f)
                T(t["changeSrc"], 14, 400, Ms.Brown, lh = 1.5f)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    MsButton(t["askDoc"], BtnKind.Light, Modifier.weight(1f)) { vm.changeMed("held") }
                    MsButton(t["approveChg"], BtnKind.Primary, Modifier.weight(1f)) { vm.changeMed("approved") }
                }
            }
            "approved" -> T(t["chgApproved"], 15, 600, Ms.GreenFg, Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(Ms.GreenBg).padding(16.dp))
            else -> MsCard(gap = 10.dp) {
                T(t["chgHeld"], 15, 600)
                MsButton(t["approveChg"], BtnKind.Primary, height = 44.dp) { vm.changeMed("approved") }
            }
        }
        D(t["todayDoses"], 22)
        MsCard(gap = 14.dp) {
            vm.doses.forEach { d ->
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
                    Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Tick(36.dp, if (d.taken) Ms.GreenBg else Ms.Blister) { Ico(LineIcons.Pill, if (d.taken) Ms.GreenFg else Ms.Muted2, 18.dp) }
                        Column {
                            T(d.name, 15, 700)
                            T("${d.time} · ${d.what}", 13, 400, Ms.Muted)
                        }
                    }
                    T(if (d.taken) t["taken"] else t["notTaken"], 13, 800, if (d.taken) Ms.GreenFg else Ms.AmberText)
                }
            }
        }
    }
}

// ====================== BILLS ======================

/** Torn-paper zigzag along the bottom of the receipt. */
@Composable
private fun Zigzag() {
    Canvas(Modifier.fillMaxWidth().height(14.dp)) {
        val tooth = 18.dp.toPx()
        val h = size.height
        val path = Path().apply {
            moveTo(0f, 0f)
            var x = 0f
            while (x < size.width) {
                lineTo(x + tooth / 2, h * 0.64f)
                lineTo(x + tooth, 0f)
                x += tooth
            }
            lineTo(size.width, 0f)
            close()
        }
        drawPath(path, Color.White)
    }
}

@Composable
fun FamilyBillsScreen(vm: MedSureViewModel) {
    val t = vm.tx
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Column(Modifier.padding(top = 6.dp)) {
            D(t["billTitle"], 32)
            T(t["billSub"], 14, 400, Ms.Muted, Modifier.padding(top = 6.dp))
        }
        Column(Modifier.shadow(10.dp, RoundedCornerShape(20.dp), ambientColor = Ms.Ink.copy(alpha = 0.08f), spotColor = Ms.Ink.copy(alpha = 0.08f))) {
            Column(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp)).background(Color.White)
                    .padding(start = 18.dp, end = 18.dp, top = 20.dp, bottom = 10.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                T("[HOSPITAL NAME] · IP [NUMBER]", 12, 800, Ms.Muted, spacing = 0.12f)
                vm.billRows.forEach { (label, amt) ->
                    Column {
                        Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                            T(label, 15); T(amt, 15, 600)
                        }
                        Box(Modifier.fillMaxWidth().height(1.dp).dashedBorder(Ms.Line, 1.dp, 0.dp, 3.dp, 3.dp))
                    }
                }
                Caps(t["worth"], Ms.AmberText, modifier = Modifier.padding(top = 6.dp))
                vm.flags.forEach { f ->
                    val sentF = vm.sent[f.id] == true
                    Column(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Ms.FlagBg)
                            .dashedBorder(Ms.FlagBorder, 1.5.dp, 14.dp)
                            .pressable(pressedScale = 0.98f) { vm.qid = f.id; vm.sheet = Sheet.Query }
                            .padding(12.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            T(f.label, 15, 700, modifier = Modifier.weight(1f)); T(f.amt, 15, 700)
                        }
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            T(f.note, 13, 400, Ms.AmberDark, Modifier.weight(1f))
                            T(if (sentF) t["asked"] else t["ask"], 13, 700, if (sentF) Ms.GreenFg else Ms.AmberText)
                        }
                    }
                }
                Box(Modifier.fillMaxWidth().padding(top = 6.dp).height(2.dp).background(Ms.Ink))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    D(t["total"], 20); D("₹1,84,350", 24)
                }
            }
            Zigzag()
        }
        D(t["whoPaid"], 22)
        MsCard(gap = 12.dp) {
            Row(Modifier.fillMaxWidth().height(14.dp).clip(RoundedCornerShape(999.dp)), horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                Box(Modifier.weight(120000f).fillMaxHeight().background(Ms.Marigold))
                Box(Modifier.weight(40000f).fillMaxHeight().background(Ms.Teal))
                Box(Modifier.weight(24350f).fillMaxHeight().background(Ms.Taken))
            }
            PayRow(Ms.Marigold, "${vm.me} · UPI, 29 Sep", "₹1,20,000")
            PayRow(Ms.Teal, "Meera · card, 29 Sep", "₹40,000")
            PayRow(Ms.Taken, t["stillPay"], "₹24,350")
        }
    }
}

@Composable
private fun PayRow(color: Color, label: String, amt: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(Modifier.size(12.dp).clip(RoundedCornerShape(4.dp)).background(color)); T(label, 15)
        }
        T(amt, 15, 700)
    }
}

// ====================== CLAIM ======================

@Composable
fun FamilyClaimScreen(vm: MedSureViewModel) {
    val t = vm.tx
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Column(Modifier.padding(top = 6.dp)) {
            D(t["claimTitle"], 32)
            T(t["claimSub"], 14, 400, Ms.Muted, Modifier.padding(top = 6.dp))
        }
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(22.dp)).background(Ms.Ink).padding(18.dp),
            horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                T(t["submitBy"], 13, 700, Ms.OnDark)
                D(t["daysLeft"], 28, color = Ms.Paper)
            }
            Ico(LineIcons.Clock, Ms.Marigold, 30.dp)
        }
        MsCard {
            val track = vm.track
            track.forEachIndexed { i, (label, sub) ->
                val done = i < vm.curStep; val now = i == vm.curStep; val bad = i == 1
                val dot = when { bad -> Ms.Red; done -> Ms.Teal; now -> Ms.Marigold; else -> Color.White }
                val ring = when { bad -> Ms.Red; done -> Ms.Teal; now -> Ms.Ink; else -> Ms.Handle }
                val line = if (i == track.lastIndex) Color.Transparent else if (i < vm.curStep) Ms.Teal else Ms.Line
                Row(Modifier.height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                    Column(Modifier.fillMaxHeight(), horizontalAlignment = Alignment.CenterHorizontally) {
                        Box(Modifier.size(18.dp).clip(CircleShape).background(dot).border(3.dp, ring, CircleShape))
                        Box(Modifier.width(2.dp).weight(1f).heightIn(min = 22.dp).background(line))
                    }
                    Column(Modifier.padding(bottom = 14.dp)) {
                        T(label, 15, 700, if (i > vm.curStep) Ms.Muted2 else Ms.Ink)
                        T(sub, 13, 400, Ms.Muted)
                    }
                }
            }
        }
        D(t["docs"], 22)
        MsCard(gap = 12.dp) {
            vm.checklist.forEach { k ->
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Tick(28.dp, if (k.done) Ms.GreenBg else Ms.AmberBg) {
                        Ico(if (k.done) LineIcons.Check else LineIcons.Exclaim, if (k.done) Ms.GreenFg else Ms.AmberDark, 18.dp)
                    }
                    Column(Modifier.weight(1f)) {
                        T(k.name, 15, 700)
                        T(k.sub, 13, 400, if (k.done) Ms.Muted else Ms.AmberText)
                    }
                    if (!k.done && k.fix != null) MsButton(k.fixLabel, BtnKind.Mari, height = 44.dp, fontSize = 14, hPad = 12.dp) { k.fix?.invoke() }
                }
            }
        }
        if (vm.approved) T(t["sentIns"], 15, 600, Ms.GreenFg, Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(Ms.GreenBg).padding(16.dp))
        else MsButton(t["review"], BtnKind.Primary, Modifier.fillMaxWidth()) { vm.sheet = Sheet.Approve }
    }
}

// ====================== RECOVERY ======================

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun FamilyRecoveryScreen(vm: MedSureViewModel) {
    val t = vm.tx
    val L = vm.level
    val past = listOf(Ms.GreenDot, Ms.GreenDot, Ms.AmberDot, Ms.GreenDot, Ms.GreenDot, Ms.GreenDot)
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Column(Modifier.padding(top = 6.dp)) {
            D(t["recTitle"], 32)
            T(t["recSub"], 14, 400, Ms.Muted, Modifier.padding(top = 6.dp))
        }
        MsCard(gap = 14.dp) {
            T(t["weekLbl"], 15, 700)
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                t.days.forEachIndexed { i, d ->
                    Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        val shape = RoundedCornerShape(12.dp)
                        val box = Modifier.fillMaxWidth().aspectRatio(1f).clip(shape)
                        when {
                            i < 6 -> Box(box.background(past[i]))
                            vm.ciDone -> Box(box.background(L.dot))
                            else -> Box(box.dashedBorder(Ms.Pale, 1.5.dp, 12.dp, 4.dp, 3.dp))
                        }
                        T(d, 11, 700, Ms.Muted)
                    }
                }
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Legend(Ms.GreenDot, t["legClear"]); Legend(Ms.AmberDot, t["legAmber"]); Legend(Ms.Red, t["legRed"]); Legend(null, t["legNone"])
            }
        }
        if (vm.noteSaved.isNotEmpty()) {
            MsCard(border = Ms.Ink, borderWidth = 1.5.dp, gap = 8.dp) {
                T(t["famNote"], 15, 700)
                T(vm.noteSaved, 15, 400, Ms.Text3, lh = 1.5f)
            }
        }
        MsCard(gap = 8.dp) {
            T(t["sunTitle"], 15, 700)
            T(t["sunBody"], 15, 400, Ms.Text3, lh = 1.5f)
        }
        MsCard(gap = 10.dp) {
            T(t["scanTitle"], 15, 700)
            T(t["scanBody"], 14, 400, Ms.Muted, lh = 1.45f)
            MsButton(t["openCam"], BtnKind.Primary, icon = LineIcons.Camera) {}
        }
    }
}

@Composable
private fun Legend(color: Color?, label: String) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        val m = Modifier.size(10.dp).clip(RoundedCornerShape(3.dp))
        if (color != null) Box(m.background(color)) else Box(m.dashedBorder(Ms.Pale, 1.5.dp, 3.dp, 2.dp, 2.dp))
        T(label, 13, 400, Ms.Text3)
    }
}
