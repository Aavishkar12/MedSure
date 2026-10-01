package com.powerbank.medsure

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.*
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.lifecycle.viewmodel.compose.viewModel
import com.powerbank.medsure.state.*
import com.powerbank.medsure.ui.auth.*
import com.powerbank.medsure.ui.components.*
import com.powerbank.medsure.ui.family.*
import com.powerbank.medsure.ui.patient.*
import com.powerbank.medsure.ui.settings.*
import com.powerbank.medsure.ui.theme.Ms

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        // Android 13+ shows no notifications until the user allows them.
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            registerForActivityResult(ActivityResultContracts.RequestPermission()) {}
                .launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        setContent {
            MaterialTheme {
                val vm: MedSureViewModel = viewModel()
                MedSureApp(vm)
            }
        }
    }
}

/** Outer frame: paper column, max 480dp wide and centred (the prototype's responsive shell). */
@Composable
fun MedSureApp(vm: MedSureViewModel) {
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { vm.refresh() }
    LifecycleEventEffect(Lifecycle.Event.ON_PAUSE) { vm.save() }
    // Family view also checks every few seconds while open, in case a push is delayed or missed.
    LaunchedEffect(vm.stage, vm.role) {
        while (vm.stage == Stage.App && !vm.isPatient) {
            kotlinx.coroutines.delay(8000)
            vm.refresh()
        }
    }
    Box(Modifier.fillMaxSize().background(Ms.Outside), contentAlignment = Alignment.TopCenter) {
        Box(
            Modifier.fillMaxHeight().widthIn(max = 480.dp).fillMaxWidth().background(Ms.Paper)
                .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Top + WindowInsetsSides.Horizontal + WindowInsetsSides.Bottom))
        ) {
            AnimatedContent(
                targetState = vm.stage,
                transitionSpec = { fadeIn(tween(250)) togetherWith fadeOut(tween(150)) },
                label = "stage",
            ) { stage ->
                when (stage) {
                    Stage.Lang -> LanguageScreen(vm)
                    Stage.Welcome -> WelcomeScreen(vm)
                    Stage.Details -> DetailsScreen(vm)
                    Stage.Otp -> OtpScreen(vm)
                    Stage.Onboarding -> OnboardingScreen(vm)
                    Stage.Processing -> ProcessingScreen(vm)
                    Stage.App -> AppScaffold(vm)
                }
            }
            SheetHost(vm)
        }
    }
    BackHandler(enabled = vm.sheet != null || vm.overlay != null || vm.stage == Stage.Details || vm.stage == Stage.Otp || vm.stage == Stage.Welcome || vm.stage == Stage.Onboarding || vm.stage == Stage.Processing) {
        when {
            vm.sheet != null -> vm.sheet = null
            vm.overlay != null -> vm.closeOverlay()
            vm.stage == Stage.Processing -> { /* Disabled on processing screen */ }
            vm.stage == Stage.Onboarding -> vm.prevOnboardingStep()
            vm.stage == Stage.Otp -> vm.stage = Stage.Details
            vm.stage == Stage.Details -> vm.stage = Stage.Welcome
            vm.stage == Stage.Welcome -> vm.stage = Stage.Lang
        }
    }
}

@Composable
private fun AppScaffold(vm: MedSureViewModel) {
    val t = vm.tx
    val ov = vm.overlay
    val ctx = LocalContext.current

    // Ask for the phone-call permission once, as soon as the patient is signed in (never in the middle of an alert).
    val askCall = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {}
    LaunchedEffect(vm.role) {
        val granted = ContextCompat.checkSelfPermission(ctx, Manifest.permission.CALL_PHONE) == PackageManager.PERMISSION_GRANTED
        if (vm.isPatient && !granted && !vm.askedCallPerm) {
            vm.askedCallPerm = true
            askCall.launch(Manifest.permission.CALL_PHONE)
        }
    }

    // The countdown lives in the ViewModel; this places the call whichever tab the patient is on.
    LaunchedEffect(vm.dialRequest) {
        vm.dialRequest?.let { number ->
            placeCall(ctx, number)
            vm.dialRequest = null
        }
    }
    Column(Modifier.fillMaxSize()) {
        // Top bar
        Row(
            Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 6.dp),
            horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically,
        ) {
            if (ov == null) D("MedSure", 20) else IconBtn(LineIcons.ChevronLeft, t["back"]) { vm.closeOverlay() }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                T(vm.me, 13, 700, Ms.Muted)
                IconBtn(LineIcons.Settings, t["settings"]) { vm.overlay = Overlay.Settings }
            }
        }

        // Content
        val key = ScreenKey(ov, vm.role, vm.ptab, vm.ftab)
        if (ov == Overlay.LangPick) {
            LangPickScreen(vm, Modifier.weight(1f).padding(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 16.dp))
        } else {
            AnimatedContent(
                targetState = key,
                transitionSpec = { fadeIn(tween(250)) togetherWith fadeOut(tween(120)) },
                modifier = Modifier.weight(1f),
                label = "screen",
            ) { k ->
                Column(
                    Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                        .padding(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 24.dp)
                ) {
                    when {
                        k.ov == Overlay.Settings -> SettingsScreen(vm)
                        k.ov == Overlay.Add -> AddMemberScreen(vm)
                        k.role == Role.Patient -> when (k.ptab) {
                            PTab.Today -> TodayScreen(vm)
                            PTab.Care -> CareScreen(vm)
                            PTab.Checkin -> CheckinScreen(vm)
                            PTab.Help -> HelpScreen(vm)
                        }
                        else -> when (k.ftab) {
                            FTab.Home -> FamilyHomeScreen(vm)
                            FTab.Meds -> FamilyMedsScreen(vm)
                            FTab.Bills -> FamilyBillsScreen(vm)
                            FTab.Claim -> FamilyClaimScreen(vm)
                            FTab.Care -> FamilyRecoveryScreen(vm)
                        }
                    }
                }
            }
        }

        // Bottom tabs
        if (ov == null) BottomTabs(vm)
    }
}

@Composable
private fun BottomTabs(vm: MedSureViewModel) {
    val t = vm.tx
    Row(
        Modifier.fillMaxWidth().background(Ms.Paper)
            .drawBehind { drawLine(Ms.Line, Offset(0f, 0f), Offset(size.width, 0f), 1.dp.toPx()) }
            .padding(start = 10.dp, end = 10.dp, top = 8.dp, bottom = 12.dp),
        horizontalArrangement = Arrangement.spacedBy(if (vm.isPatient) 4.dp else 3.dp),
    ) {
        if (vm.isPatient) {
            Tab(t["tToday"], LineIcons.Pill, vm.ptab == PTab.Today) { vm.ptab = PTab.Today }
            Tab(t["tCare"], LineIcons.FileText, vm.ptab == PTab.Care) { vm.ptab = PTab.Care }
            Tab(t["tCheckin"], LineIcons.Activity, vm.ptab == PTab.Checkin) { vm.ptab = PTab.Checkin }
            Tab(t["tHelp"], LineIcons.MapPin, vm.ptab == PTab.Help) { vm.ptab = PTab.Help }
        } else {
            Tab(t["tHome"], LineIcons.Home, vm.ftab == FTab.Home) { vm.ftab = FTab.Home }
            Tab(t["tMeds"], LineIcons.Pill, vm.ftab == FTab.Meds) { vm.ftab = FTab.Meds }
            Tab(t["tBills"], LineIcons.Receipt, vm.ftab == FTab.Bills) { vm.ftab = FTab.Bills }
            Tab(t["tClaim"], LineIcons.Shield, vm.ftab == FTab.Claim) { vm.ftab = FTab.Claim }
            Tab(t["tRec"], LineIcons.Activity, vm.ftab == FTab.Care) { vm.ftab = FTab.Care }
        }
    }
}

@Composable
private fun RowScope.Tab(label: String, icon: ImageVector, on: Boolean, onClick: () -> Unit) {
    val fg = if (on) Ms.Ink else Ms.Muted2
    Column(
        Modifier.weight(1f).heightIn(min = 58.dp).clip(RoundedCornerShape(16.dp))
            .background(if (on) Ms.Marigold else androidx.compose.ui.graphics.Color.Transparent)
            .pressable(onClick = onClick).padding(horizontal = 2.dp, vertical = 6.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(3.dp, Alignment.CenterVertically),
    ) {
        Ico(icon, fg)
        T(label, 11, 600, fg, align = TextAlign.Center, lh = 1.15f)
    }
}

/** Bottom sheet with scrim, matching the prototype's .scrim / .sheet. */
@Composable
private fun SheetHost(vm: MedSureViewModel) {
    val show = vm.stage == Stage.App && !vm.isPatient && vm.sheet != null
    var last by remember { mutableStateOf(vm.sheet) }
    if (vm.sheet != null) last = vm.sheet
    AnimatedVisibility(show, enter = fadeIn(tween(200)), exit = fadeOut(tween(150))) {
        Box(
            Modifier.fillMaxSize().background(Ms.Ink.copy(alpha = 0.5f))
                .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null) { vm.sheet = null },
        )
    }
    BoxWithConstraints(Modifier.fillMaxSize(), contentAlignment = Alignment.BottomCenter) {
        val maxH = maxHeight * 0.9f
        AnimatedVisibility(
            show,
            enter = slideInVertically(tween(300)) { it / 4 } + fadeIn(tween(300)),
            exit = slideOutVertically(tween(200)) { it / 4 } + fadeOut(tween(200)),
        ) {
            Column(
                Modifier.fillMaxWidth().heightIn(max = maxH)
                    .clip(RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp)).background(Ms.Paper)
                    .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null) {}
                    .verticalScroll(rememberScrollState())
                    .padding(start = 20.dp, end = 20.dp, top = 12.dp, bottom = 28.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                when (last) {
                    Sheet.Query -> QuerySheetContent(vm)
                    Sheet.Approve -> ApproveSheetContent(vm)
                    null -> {}
                }
            }
        }
    }
}

private data class ScreenKey(val ov: Overlay?, val role: Role, val ptab: PTab, val ftab: FTab)
