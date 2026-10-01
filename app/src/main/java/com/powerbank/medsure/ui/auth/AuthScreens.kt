package com.powerbank.medsure.ui.auth

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.powerbank.medsure.i18n.AllLanguages
import com.powerbank.medsure.i18n.AppLanguage
import com.powerbank.medsure.state.MedSureViewModel
import com.powerbank.medsure.state.Role
import com.powerbank.medsure.state.Stage
import com.powerbank.medsure.ui.components.*
import com.powerbank.medsure.ui.theme.Ms

/** One language tile. Native script on top, English name below. */
@Composable
fun LangTile(l: AppLanguage, selected: Boolean, onClick: () -> Unit) {
    val shape = RoundedCornerShape(18.dp)
    Column(
        Modifier.fillMaxWidth().heightIn(min = 76.dp).clip(shape)
            .background(if (selected) Ms.Ink else Ms.White)
            .border(1.5.dp, if (selected) Ms.Ink else Ms.Line3, shape)
            .pressable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(2.dp, Alignment.CenterVertically),
    ) {
        val fg = if (selected) Ms.Paper else Ms.Ink
        T(l.native, 20, 700, fg)
        T(l.english, 12, 600, fg.copy(alpha = 0.75f))
    }
}

/** The 23-language grid, used before login and from Settings. */
@Composable
fun LanguageGrid(vm: MedSureViewModel, modifier: Modifier = Modifier, footer: @Composable () -> Unit = {}) {
    LazyVerticalGrid(
        columns = GridCells.Adaptive(140.dp),
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        items(AllLanguages, key = { it.code }) { l -> LangTile(l, vm.lang == l.code) { vm.lang = l.code } }
        item(span = { androidx.compose.foundation.lazy.grid.GridItemSpan(maxLineSpan) }) { footer() }
    }
}

@Composable
fun LanguageScreen(vm: MedSureViewModel) {
    val t = vm.tx
    Column(Modifier.fillMaxSize()) {
        Column(Modifier.padding(start = 18.dp, end = 18.dp, top = 22.dp, bottom = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            D("MedSure", 22)
            D(t["langTitle"], 32, lh = 1.08f, modifier = Modifier.padding(top = 6.dp))
            T("மொழியைத் தேர்ந்தெடுக்கவும் · भाषा चुनें", 15, 400, Ms.Muted)
        }
        LanguageGrid(
            vm,
            Modifier.weight(1f).padding(horizontal = 18.dp),
            footer = { T(t["langNote"], 13, 400, Ms.Muted, Modifier.padding(top = 4.dp, bottom = 16.dp), lh = 1.45f) },
        )
        Box(Modifier.fillMaxWidth().background(Ms.Paper).drawBehind {
            drawLine(Ms.Line, androidx.compose.ui.geometry.Offset(0f, 0f), androidx.compose.ui.geometry.Offset(size.width, 0f), 1.dp.toPx())
        }.padding(start = 18.dp, end = 18.dp, top = 12.dp, bottom = 18.dp)) {
            MsButton(t["cont"], BtnKind.Primary, Modifier.fillMaxWidth(), enabled = vm.lang != null) { vm.stage = Stage.Welcome }
        }
    }
}

/** Decorative blister strip on the welcome screen. */
@Composable
private fun BlisterStrip() {
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(28.dp)).background(Ms.Blister).padding(22.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        repeat(5) { i ->
            val taken = i % 2 == 1
            Box(Modifier.weight(1f).aspectRatio(1f).drawBehind {
                drawCircle(Ms.BubbleShadow, radius = size.minDimension / 2, center = center.copy(y = center.y + 3.dp.toPx()))
            }.clip(CircleShape).background(if (taken) Ms.Taken else Ms.White), contentAlignment = Alignment.Center) {
                if (taken) Ico(LineIcons.Check, Ms.Teal, 22.dp)
                else Box(Modifier.fillMaxWidth(0.6f).fillMaxHeight(0.28f).rotate(-32f).clip(RoundedCornerShape(999.dp)).background(Ms.Marigold))
            }
        }
    }
}

@Composable
private fun RoleCard(title: String, sub: String, badgeBg: Color, badgeFg: Color, icon: androidx.compose.ui.graphics.vector.ImageVector, onClick: () -> Unit) {
    val shape = RoundedCornerShape(22.dp)
    Row(
        Modifier.fillMaxWidth().clip(shape).background(Ms.White).border(1.5.dp, Ms.Line3, shape)
            .pressable(pressedScale = 0.98f, onClick = onClick).padding(18.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Tick(52.dp, badgeBg) { Ico(icon, badgeFg) }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            D(title, 20)
            T(sub, 14, 400, Ms.Muted)
        }
        Ico(LineIcons.ChevronRight, Ms.Ink)
    }
}

@Composable
fun WelcomeScreen(vm: MedSureViewModel) {
    val t = vm.tx
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(start = 18.dp, end = 18.dp, top = 22.dp, bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            D("MedSure", 22)
            Chip(vm.langNative, false, leading = LineIcons.Globe) { vm.stage = Stage.Lang }
        }
        BlisterStrip()
        D(t["welTitle"], 34, lh = 1.08f)
        T(t["welSub"], 16, 400, Ms.Text3, lh = 1.5f)
        RoleCard(t["iamPatient"], t["iamPatientSub"], Ms.Marigold, Ms.Ink, LineIcons.User) {
            vm.loginRole = Role.Patient; vm.stage = Stage.Details
        }
        RoleCard(t["iamFamily"], t["iamFamilySub"], Ms.Teal, Color.White, LineIcons.Users) {
            vm.loginRole = Role.Family; vm.stage = Stage.Details
        }
    }
}

@Composable
fun DetailsScreen(vm: MedSureViewModel) {
    val t = vm.tx
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        IconBtn(LineIcons.ChevronLeft, t["back"]) { vm.stage = Stage.Welcome }
        D(if (vm.loginRole == Role.Patient) t["signPatient"] else t["signFamily"], 32, lh = 1.08f)
        T(t["detailsHint"], 15, 400, Ms.Text3, lh = 1.5f)
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            T(t["mobile"], 14, 700, Ms.Text3)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                val shape = RoundedCornerShape(14.dp)
                Box(
                    Modifier.height(54.dp).clip(shape).background(Ms.Blister).border(1.5.dp, Ms.Line2, shape).padding(horizontal = 14.dp),
                    contentAlignment = Alignment.Center,
                ) { T("+91", 17, 700) }
                Field(null, vm.phone, vm::onPhone, "98765 43210", Modifier.weight(1f), KeyboardType.Phone)
            }
        }
        Field(t["email"], vm.email, vm::onEmail, "name@example.com", keyboard = KeyboardType.Email)
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(Ms.Blister).padding(14.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Ico(LineIcons.Lock, Ms.Teal, 18.dp, Modifier.padding(top = 2.dp))
            T(t["twoFactor"], 14, 400, Ms.Text3, lh = 1.45f)
        }
        MsButton(t["sendCodes"], BtnKind.Primary, Modifier.fillMaxWidth(), enabled = vm.canSend) { vm.sendCodes() }
    }
}

@Composable
fun OtpScreen(vm: MedSureViewModel) {
    val t = vm.tx
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        IconBtn(LineIcons.ChevronLeft, t["back"]) { vm.stage = Stage.Details }
        D(t["otpTitle"], 32, lh = 1.08f)
        OtpField("${t["smsCode"]} +91 ${vm.phone}", vm.otpP, vm::onOtpP, vm.okOtp(vm.otpP), t["codeOk"], t["codeWait"])
        OtpField("${t["emailCode"]} ${vm.email}", vm.otpE, vm::onOtpE, vm.okOtp(vm.otpE), t["codeOk"], t["codeWait"])
        T(t["resend"], 14, 400, Ms.Muted)
        T(t["demoHint"], 13, 400, Ms.Muted, Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Ms.Blister).padding(horizontal = 12.dp, vertical = 10.dp))
        MsButton(t["verify"], BtnKind.Primary, Modifier.fillMaxWidth(), enabled = vm.canVerify) { vm.verify() }
    }
}

@Composable
private fun OtpField(label: String, value: String, onChange: (String) -> Unit, ok: Boolean, okText: String, waitText: String) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Field(label, value, onChange, "••••••", keyboard = KeyboardType.Number, otp = true)
        T(if (ok) okText else waitText, 13, 700, if (ok) Ms.GreenFg else Ms.Muted2)
    }
}
