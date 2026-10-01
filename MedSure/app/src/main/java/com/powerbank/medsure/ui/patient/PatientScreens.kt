package com.powerbank.medsure.ui.patient

import android.content.Intent
import android.net.Uri
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.powerbank.medsure.state.MedSureViewModel
import com.powerbank.medsure.state.PTab
import com.powerbank.medsure.ui.components.*
import com.powerbank.medsure.ui.theme.Ms

fun dial108(context: android.content.Context) {
    context.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:108")))
}

/** Opens the dialler with an Indian mobile number filled in. */
fun dial(context: android.content.Context, phone: String) {
    val digits = phone.filter { it.isDigit() }.takeLast(10)
    if (digits.isNotEmpty()) context.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:+91$digits")))
}

// ====================== TODAY ======================

@Composable
private fun Bubble(taken: Boolean, label: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    var popKey by remember { mutableIntStateOf(0) }
    val pop = remember { Animatable(1f) }
    LaunchedEffect(popKey) {
        if (popKey > 0) {
            pop.animateTo(0.86f, tween(120)); pop.animateTo(1f, tween(180))
        }
    }
    Box(
        modifier.aspectRatio(1f)
            .drawBehind {
                if (!taken) drawCircle(Ms.BubbleShadow, radius = size.minDimension / 2, center = center.copy(y = center.y + 3.dp.toPx()))
            }
            .scale(pop.value)
            .clip(CircleShape)
            .background(if (taken) Ms.Taken else Ms.White)
            .pressable(pressedScale = 0.9f) { popKey++; onClick() }
            .semanticsLabel(label),
        contentAlignment = Alignment.Center,
    ) {
        if (taken) Ico(LineIcons.Check, Ms.Teal, 30.dp)
        else Box(
            Modifier.fillMaxWidth(0.6f).fillMaxHeight(0.28f).rotate(-32f).clip(RoundedCornerShape(999.dp))
                .background(Ms.Marigold)
        )
    }
}

private fun Modifier.semanticsLabel(label: String) = this.semantics { contentDescription = label }

@Composable
fun TodayScreen(vm: MedSureViewModel) {
    val t = vm.tx
    val doses = vm.doses
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Column(Modifier.padding(top = 6.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                T(t["date"], 14, 600, Ms.Muted); Dot(); T(t["dayHome"], 14, 600, Ms.Muted)
            }
            D(t["hello"] + "\nLakshmi", 40, lh = 1.05f, modifier = Modifier.padding(top = 4.dp))
        }

        MsCard(gap = 14.dp) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    D(t["todaysMeds"], 22)
                    T(t["tapAfter"], 14, 400, Ms.Muted)
                }
                Row(verticalAlignment = Alignment.Bottom) { D("${vm.takenCount}", 30); D("/4", 18, color = Ms.Muted2, modifier = Modifier.padding(bottom = 3.dp)) }
            }
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(24.dp)).background(Ms.Blister)
                    .border(1.dp, Ms.BlisterEdge, RoundedCornerShape(24.dp)).padding(14.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                doses.forEach { d ->
                    Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Bubble(d.taken, "${d.time} ${d.name}", { vm.toggleDose(d.id) }, Modifier.fillMaxWidth())
                        T(d.time, 12, 700, align = TextAlign.Center)
                    }
                }
            }
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                doses.forEach { d ->
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        T("${d.time} · ${d.name}", 14, 600, modifier = Modifier.weight(1f))
                        T(d.what, 14, 400, Ms.Muted, align = TextAlign.End)
                    }
                }
            }
        }

        if (!vm.ciDone) {
            Column(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(22.dp)).background(Ms.Marigold).padding(18.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                D(t["ciCardTitle"], 24, lh = 1.15f)
                T(t["ciCardBody"], 15, 500, lh = 1.45f)
                MsButton(t["startCi"], BtnKind.Primary) { vm.ptab = PTab.Checkin }
            }
        } else {
            val L = vm.level
            MsCard {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                    Tick(28.dp, L.bg) { Ico(LineIcons.Activity, L.fg, 18.dp) }
                    Column(Modifier.weight(1f)) {
                        T("${t["ciDoneLbl"]} · ${L.name}", 15, 700)
                        T(L.title, 14, 400, Ms.Muted)
                    }
                    MsButton(t["view"], BtnKind.Light, height = 44.dp) { vm.ptab = PTab.Checkin }
                }
            }
        }

        if (vm.members.isEmpty()) {
            Column(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(22.dp)).background(Ms.Paper)
                    .dashedBorder(Ms.SwitchOff, 2.dp, 22.dp).padding(18.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Tick(48.dp, Ms.Teal) { Ico(LineIcons.UserPlus, Color.White) }
                    D(t["addFamTitle"], 20, lh = 1.15f)
                }
                T(t["addFamBody"], 15, 400, Ms.Text3, lh = 1.5f)
                MsButton(t["addFamBtn"], BtnKind.Primary) { vm.openAdd() }
            }
        } else {
            val h = vm.members.first()
            MsCard {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Tick(44.dp, Ms.Marigold) { T(h.name.take(1).uppercase(), 15, 800) }
                    Column {
                        T("${h.name} · ${t["helperIs"]}", 15, 700)
                        T(t["helperSub"], 14, 400, Ms.Muted)
                    }
                }
            }
        }

        MsCard {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                Column(
                    Modifier.size(58.dp, 64.dp).clip(RoundedCornerShape(14.dp)).background(Ms.Ink),
                    horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center,
                ) {
                    T(t["mon"], 11, 700, Ms.Paper, spacing = 0.06f)
                    D("5", 26, color = Ms.Paper, lh = 1f)
                }
                Column(Modifier.weight(1f)) {
                    T(t["followTitle"], 16, 700)
                    T(t["followSub"], 14, 400, Ms.Muted)
                }
            }
        }

        MsButton(t["notRight"], BtnKind.Ghost, Modifier.fillMaxWidth(), icon = LineIcons.MapPin) { vm.ptab = PTab.Help }
    }
}

// ====================== MY CARE ======================

@Composable
fun CareScreen(vm: MedSureViewModel) {
    val t = vm.tx
    val tabs = listOf("watch" to t["cWatch"], "meds" to t["cMeds"], "visit" to t["cVisit"], "happened" to t["cHappened"])
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Column(Modifier.padding(top = 6.dp)) {
            D(t["careTitle"], 32)
            T(t["careSub"], 14, 400, Ms.Muted, Modifier.padding(top = 6.dp))
        }
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            tabs.forEach { (id, label) -> Chip(label, vm.care == id) { vm.care = id } }
        }
        MsCard(gap = 12.dp) {
            when (vm.care) {
                "watch" -> {
                    D(t["cWatch"], 24)
                    listOf(t["watch1"], t["watch2"], t["watch3"]).forEach { w ->
                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            Ico(LineIcons.Alert, Ms.Warn); T(w, 17, 400)
                        }
                    }
                    T(t["call108line"], 15, 600, Color.White, Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Ms.Red).padding(horizontal = 14.dp, vertical = 12.dp))
                    T("${t["src"]} 4", 13, 400, Ms.Muted)
                }
                "meds" -> {
                    D(t["cMeds"], 24)
                    vm.doses.forEach { d ->
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            T(d.time, 14, 800, modifier = Modifier.width(66.dp))
                            Column {
                                T(d.name, 16, 700)
                                T(d.why, 15, 400, Ms.Muted)
                            }
                        }
                    }
                    T("${t["src"]} 3", 13, 400, Ms.Muted)
                }
                "visit" -> {
                    D(t["cVisit"], 24)
                    T(t["visitBody"], 18, 400, lh = 1.5f)
                    T(t["visitBring"], 16, 400, Ms.Text3, lh = 1.5f)
                    T("${t["src"]} 4", 13, 400, Ms.Muted)
                }
                else -> {
                    D(t["cHappened"], 24)
                    T(t["happenedBody"], 18, 400, lh = 1.55f)
                    T("${t["src"]} 1", 13, 400, Ms.Muted)
                }
            }
        }
        MsButton(
            if (vm.reading) t["reading"] else t["readAloud"],
            if (vm.reading) BtnKind.Primary else BtnKind.Light,
            Modifier.fillMaxWidth(), icon = LineIcons.Volume,
        ) { vm.reading = !vm.reading }
    }
}

// ====================== CHECK-IN ======================

@Composable
private fun Rings() {
    val inf = rememberInfiniteTransition(label = "rings")
    listOf(0, 500).forEach { delay ->
        val p by inf.animateFloat(
            0f, 1f,
            infiniteRepeatable(tween(1400, delayMillis = delay, easing = LinearOutSlowInEasing), RepeatMode.Restart),
            label = "ring$delay",
        )
        Box(
            Modifier.fillMaxSize().scale(1f + 0.7f * p).alpha(0.8f * (1f - p))
                .border(2.dp, Ms.Marigold, CircleShape)
        )
    }
}

@Composable
private fun Equalizer() {
    val inf = rememberInfiniteTransition(label = "eq")
    Row(Modifier.height(22.dp), horizontalArrangement = Arrangement.spacedBy(3.dp), verticalAlignment = Alignment.CenterVertically) {
        repeat(5) { i ->
            val h by inf.animateFloat(
                5f, 22f,
                infiniteRepeatable(tween(450, delayMillis = i * 150, easing = FastOutSlowInEasing), RepeatMode.Reverse),
                label = "bar$i",
            )
            Box(Modifier.width(4.dp).height(h.dp).clip(RoundedCornerShape(4.dp)).background(Ms.Marigold))
        }
    }
}

@Composable
private fun VoiceButton(vm: MedSureViewModel) {
    val t = vm.tx
    val on = vm.listening
    val shape = RoundedCornerShape(999.dp)
    Row(
        Modifier.fillMaxWidth().heightIn(min = 76.dp).clip(shape)
            .background(if (on) Ms.Ink else Ms.White).border(2.dp, Ms.Ink, shape)
            .pressable(pressedScale = 0.98f) { vm.listening = !vm.listening }
            .padding(start = 8.dp, end = 18.dp, top = 8.dp, bottom = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Box(Modifier.size(60.dp), contentAlignment = Alignment.Center) {
            if (on) Rings()
            Box(Modifier.fillMaxSize().clip(CircleShape).background(if (on) Ms.Paper else Ms.Marigold), contentAlignment = Alignment.Center) {
                Ico(LineIcons.Mic, if (on) Ms.Red else Ms.Ink, 30.dp)
            }
        }
        val fg = if (on) Ms.Paper else Ms.Ink
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            T(if (on) t["micListening"] else t["micBtn"], 17, 800, fg)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Ico(LineIcons.Globe, fg.copy(alpha = 0.85f), 18.dp)
                T(if (on) t["micStop"] else t["micAny"], 13, 600, fg.copy(alpha = 0.85f))
            }
        }
        if (on) Equalizer()
    }
}

@Composable
fun CheckinScreen(vm: MedSureViewModel) {
    val t = vm.tx
    val ctx = LocalContext.current
    Column(verticalArrangement = Arrangement.spacedBy(18.dp)) {
        if (vm.asking) {
            val (q, opts) = vm.questions[vm.step.coerceAtMost(2)]
            Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Row(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    repeat(3) { i ->
                        val c = when {
                            i < vm.step -> Ms.Teal
                            i == vm.step -> Ms.Marigold
                            else -> Ms.Line
                        }
                        Box(Modifier.weight(1f).height(6.dp).clip(RoundedCornerShape(999.dp)).background(c))
                    }
                }
                T("${t["qWord"]} ${vm.step + 1} / 3", 14, 700, Ms.Muted)
                D(q, 30, lh = 1.15f)
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    opts.forEach { (label, lvl) ->
                        val shape = RoundedCornerShape(18.dp)
                        Row(
                            Modifier.fillMaxWidth().heightIn(min = 62.dp).clip(shape).background(Ms.White)
                                .border(1.5.dp, Ms.Line2, shape)
                                .pressable(pressedScale = 0.98f) { vm.answer(lvl) }
                                .padding(horizontal = 18.dp, vertical = 12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.SpaceBetween,
                        ) {
                            T(label, 17, 600, modifier = Modifier.weight(1f))
                            Ico(LineIcons.ChevronRight, Ms.Muted2, 18.dp)
                        }
                    }
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Rule(modifier = Modifier.weight(1f)); T(t["orSpeak"], 14, 600, Ms.Muted); Rule(modifier = Modifier.weight(1f))
                }
                VoiceButton(vm)
                Field(
                    label = null, value = vm.note, onChange = { vm.note = it.take(500) },
                    placeholder = t["typePh"], singleLine = false, minHeight = 112.dp,
                    modifier = Modifier.padding(top = 4.dp),
                    labelContent = {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Ico(LineIcons.Pen, Ms.Text3, 18.dp); T(t["typeLbl"], 14, 700, Ms.Text3)
                        }
                    },
                )
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    T(t["noteHint"], 13, 400, Ms.Muted, Modifier.weight(1f))
                    MsButton(t["sendNote"], BtnKind.Primary, enabled = vm.note.isNotBlank(), height = 46.dp) { vm.saveNote() }
                }
                if (vm.noteSaved.isNotEmpty()) {
                    Row(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Ms.GreenBg).padding(horizontal = 14.dp, vertical = 12.dp),
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Ico(LineIcons.Check, Ms.GreenFg, 18.dp, Modifier.padding(top = 2.dp))
                        T("${t["noteAdded"]}: ${vm.noteSaved}", 14, 400, Ms.GreenFg, lh = 1.45f)
                    }
                }
            }
        } else {
            val L = vm.level
            Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Column(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(26.dp)).background(L.bg).padding(22.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    T(L.caps, 13, 800, L.fg, spacing = 0.08f)
                    D(L.title, 30, color = L.fg)
                    T(L.body, 17, 400, L.fg, lh = 1.5f)
                    if (vm.medWarn) T(t["medWarn"], 16, 700, L.fg)
                }
                if (vm.noteSaved.isNotEmpty()) {
                    MsCard(gap = 6.dp) {
                        Caps(t["yourNote"], size = 12)
                        T(vm.noteSaved, 16, 400, lh = 1.5f)
                    }
                }
                if (vm.levelIndex == 2) MsButton(t["call108"], BtnKind.Danger, Modifier.fillMaxWidth()) { dial108(ctx) }
                if (vm.levelIndex > 0) MsButton(t["findHosp"], BtnKind.Primary, Modifier.fillMaxWidth(), icon = LineIcons.MapPin) { vm.ptab = PTab.Help }
                MsButton(t["again"], BtnKind.Light, Modifier.fillMaxWidth()) { vm.resetCi() }
                T(t["rulesNote"], 13, 400, Ms.Muted, Modifier.fillMaxWidth().padding(horizontal = 12.dp), lh = 1.45f, align = TextAlign.Center)
            }
        }
    }
}

// ====================== GET HELP ======================

@Composable
fun HelpScreen(vm: MedSureViewModel) {
    val t = vm.tx
    val ctx = LocalContext.current
    val filters = listOf("all" to t["fAll"], "hosp" to t["fHosp"], "clinic" to t["fClinic"], "pharm" to t["fPharm"])
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Column(Modifier.padding(top = 6.dp)) {
            D(t["helpTitle"], 32)
            T(t["helpSub"], 15, 400, Ms.Muted, Modifier.padding(top = 6.dp))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            MsButton(t["call108s"], BtnKind.Danger, Modifier.weight(1f)) { dial108(ctx) }
            val fam = vm.members.firstOrNull()
            MsButton(if (fam != null) "${t["call"]} ${fam.name}" else t["callFam"], BtnKind.Light, Modifier.weight(1f), enabled = fam != null) {
                fam?.let { dial(ctx, it.phone) }
            }
        }
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            filters.forEach { (id, label) -> Chip(label, vm.filter == id) { vm.filter = id } }
        }
        vm.places.forEach { p ->
            val on = vm.chosen == p.id
            MsCard(border = if (on) Ms.Ink else Ms.Line, gap = 12.dp) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Column(Modifier.weight(1f)) {
                        T(p.name, 17, 700)
                        T(p.meta, 14, 400, Ms.Muted)
                    }
                    D(p.dist, 20)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    T(p.open, 13, 700, Ms.GreenFg, Modifier.clip(RoundedCornerShape(999.dp)).background(Ms.GreenBg).padding(horizontal = 10.dp, vertical = 4.dp))
                    if (p.badge.isNotEmpty()) T(p.badge, 13, 700, Ms.Paper, Modifier.clip(RoundedCornerShape(999.dp)).background(Ms.Ink).padding(horizontal = 10.dp, vertical = 4.dp))
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    MsButton(t["call"], BtnKind.Light, Modifier.weight(1f), height = 44.dp) {}
                    MsButton(if (on) t["going"] else t["goHere"], if (on) BtnKind.Primary else BtnKind.Mari, Modifier.weight(1f), height = 44.dp) {
                        vm.chosen = if (on) null else p.id
                    }
                }
            }
        }
        if (vm.chosen != null && vm.places.any { it.id == vm.chosen }) {
            Column(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(22.dp)).background(Ms.Ink).padding(18.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    T(t["shareTitle"], 16, 700, Ms.Paper, Modifier.weight(1f))
                    MsSwitch(vm.share, t["shareTitle"]) { vm.share = !vm.share }
                }
                T(if (vm.share) t["shareOnTxt"] else t["shareOffTxt"], 14, 400, Ms.OnDark, lh = 1.5f)
            }
        }
    }
}
