package com.powerbank.medsure.ui.patient

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.*
import androidx.compose.animation.core.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.*
import androidx.compose.runtime.snapshots.SnapshotStateList
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.powerbank.medsure.state.MedSureViewModel
import com.powerbank.medsure.state.OnboardingFamilyMember
import com.powerbank.medsure.state.UploadedDoc
import com.powerbank.medsure.ui.components.*
import com.powerbank.medsure.ui.theme.Ms

/** Query document name, size, and mime type from content resolver. */
fun queryDocInfo(context: Context, uri: Uri): UploadedDoc {
    var name = "Document"
    var size = 0L
    val mime = context.contentResolver.getType(uri) ?: "application/octet-stream"
    try {
        context.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
            val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            val sizeIndex = cursor.getColumnIndex(OpenableColumns.SIZE)
            if (cursor.moveToFirst()) {
                if (nameIndex != -1) name = cursor.getString(nameIndex) ?: "Document"
                if (sizeIndex != -1) size = cursor.getLong(sizeIndex)
            }
        }
    } catch (_: Exception) {}
    if (size == 0L) {
        size = 245 * 1024L
    }
    return UploadedDoc(uri, name, size, mime)
}

/**
 * Shared Onboarding Scaffold with animated progress indicator, header,
 * back button, and fixed bottom action bar.
 */
@Composable
fun OnboardingScreen(vm: MedSureViewModel) {
    val curStep = vm.onboardingStep
    Column(Modifier.fillMaxSize()) {
        // Top row: Back button
        Row(
            Modifier.fillMaxWidth().padding(start = 18.dp, end = 18.dp, top = 16.dp, bottom = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconBtn(LineIcons.ChevronLeft, "Back") { vm.prevOnboardingStep() }
        }

        // Step indicator: "Step X of 4" + 4 segmented progress bars
        Column(
            Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 6.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            T("Step $curStep of 4", 13, 700, Ms.Muted)
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                for (i in 1..4) {
                    val targetColor = when {
                        i < curStep -> Ms.Teal
                        i == curStep -> Ms.Marigold
                        else -> Ms.Blister
                    }
                    val barColor by animateColorAsState(targetColor, tween(300), label = "segment$i")
                    Box(
                        Modifier.weight(1f).height(6.dp).clip(RoundedCornerShape(999.dp))
                            .background(barColor)
                    )
                }
            }
        }

        // Animated step content with horizontal slide transitions
        AnimatedContent(
            targetState = curStep,
            transitionSpec = {
                if (targetState > initialState) {
                    slideInHorizontally(tween(250)) { it } + fadeIn(tween(250)) togetherWith
                            slideOutHorizontally(tween(250)) { -it } + fadeOut(tween(200))
                } else {
                    slideInHorizontally(tween(250)) { -it } + fadeIn(tween(250)) togetherWith
                            slideOutHorizontally(tween(250)) { it } + fadeOut(tween(200))
                }
            },
            modifier = Modifier.weight(1f),
            label = "onboarding_steps",
        ) { step ->
            when (step) {
                1 -> Step1PersonalDetails(vm)
                2 -> Step2MedicalReports(vm)
                3 -> Step3BillsAndInsurance(vm)
                4 -> Step4AddFamilyMember(vm)
            }
        }
    }
}

// ====================== STEP 1: PERSONAL DETAILS ======================

@Composable
private fun Step1PersonalDetails(vm: MedSureViewModel) {
    Column(Modifier.fillMaxSize()) {
        Column(
            Modifier.weight(1f).verticalScroll(rememberScrollState())
                .padding(start = 18.dp, end = 18.dp, top = 12.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp),
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                D("Tell us about you", 32, lh = 1.08f)
                T("This helps your family and doctors know you better.", 15, 400, Ms.Text3, lh = 1.5f)
            }

            // Full name
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Field(
                    label = "Full name",
                    value = vm.onbFullName,
                    onChange = {
                        vm.onbFullName = it
                        vm.onbInteractedName = true
                    },
                    placeholder = "Your full name",
                    keyboard = KeyboardType.Text,
                )
                if (vm.onbInteractedName && vm.onbFullName.trim().isEmpty()) {
                    T("Please enter your full name", 12, 600, Ms.Warn)
                }
            }

            // Age
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Field(
                    label = "Age",
                    value = vm.onbAge,
                    onChange = { input ->
                        val digits = input.filter { it.isDigit() }.take(3)
                        vm.onbAge = digits
                        vm.onbInteractedAge = true
                    },
                    placeholder = "e.g. 68",
                    keyboard = KeyboardType.Number,
                )
                if (vm.onbInteractedAge && (vm.onbAge.toIntOrNull() == null || vm.onbAge.toInt() !in 1..120)) {
                    T("Please enter an age between 1 and 120", 12, 600, Ms.Warn)
                }
            }

            // Gender
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                T("Gender", 14, 700, Ms.Text3)
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    listOf("Female", "Male", "Other").forEach { g ->
                        val selected = vm.onbGender == g
                        GenderPillChip(
                            label = g,
                            selected = selected,
                            modifier = Modifier.weight(1f),
                            onClick = { vm.onbGender = g },
                        )
                    }
                }
            }

            // Blood group grid
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                T("Blood group", 14, 700, Ms.Text3)
                val row1 = listOf("A+", "A-", "B+", "B-")
                val row2 = listOf("O+", "O-", "AB+", "AB-")

                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    row1.forEach { bg ->
                        BloodGroupChip(
                            label = bg,
                            selected = vm.onbBloodGroup == bg,
                            modifier = Modifier.weight(1f),
                            onClick = { vm.onbBloodGroup = bg },
                        )
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    row2.forEach { bg ->
                        BloodGroupChip(
                            label = bg,
                            selected = vm.onbBloodGroup == bg,
                            modifier = Modifier.weight(1f),
                            onClick = { vm.onbBloodGroup = bg },
                        )
                    }
                }
                BloodGroupChip(
                    label = "Not sure",
                    selected = vm.onbBloodGroup == "Not sure",
                    modifier = Modifier.fillMaxWidth(),
                    onClick = { vm.onbBloodGroup = "Not sure" },
                )
            }
        }

        // Fixed bottom button
        Box(
            Modifier.fillMaxWidth().background(Ms.Paper).drawBehind {
                drawLine(Ms.Line, Offset(0f, 0f), Offset(size.width, 0f), 1.dp.toPx())
            }.padding(start = 18.dp, end = 18.dp, top = 12.dp, bottom = 18.dp)
        ) {
            MsButton(
                text = "Continue",
                kind = BtnKind.Primary,
                modifier = Modifier.fillMaxWidth(),
                enabled = vm.onbStep1Valid,
            ) {
                vm.nextOnboardingStep()
            }
        }
    }
}

@Composable
private fun GenderPillChip(label: String, selected: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val shape = RoundedCornerShape(999.dp)
    val bg = if (selected) Ms.Teal else Ms.White
    val fg = if (selected) Color.White else Ms.Text3
    val border = if (selected) Ms.Teal else Ms.Line2
    Box(
        modifier.heightIn(min = 48.dp).clip(shape).background(bg).border(1.5.dp, border, shape)
            .pressable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 10.dp),
        contentAlignment = Alignment.Center,
    ) {
        T(label, 15, 600, fg, align = TextAlign.Center)
    }
}

@Composable
private fun BloodGroupChip(label: String, selected: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val shape = RoundedCornerShape(14.dp)
    val bg = if (selected) Ms.Teal else Ms.White
    val fg = if (selected) Color.White else Ms.Text3
    val border = if (selected) Ms.Teal else Ms.Line2
    Box(
        modifier.heightIn(min = 48.dp).clip(shape).background(bg).border(1.5.dp, border, shape)
            .pressable(onClick = onClick)
            .padding(horizontal = 10.dp, vertical = 10.dp),
        contentAlignment = Alignment.Center,
    ) {
        T(label, 15, 700, fg, align = TextAlign.Center)
    }
}

// ====================== STEP 2: MEDICAL REPORTS ======================

@Composable
private fun Step2MedicalReports(vm: MedSureViewModel) {
    Column(Modifier.fillMaxSize()) {
        Column(
            Modifier.weight(1f).verticalScroll(rememberScrollState())
                .padding(start = 18.dp, end = 18.dp, top = 12.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp),
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                D("Add your medical reports", 32, lh = 1.08f)
                T("Discharge summary, lab reports, prescriptions. You can add more later.", 15, 400, Ms.Text3, lh = 1.5f)
            }

            // Reusable DocumentUploadSection
            DocumentUploadSection(
                docs = vm.onbReports,
                onAddDocs = { newDocs -> vm.onbReports.addAll(newDocs) },
                onRemoveDoc = { doc -> vm.onbReports.remove(doc) },
            )

            // Info note box
            LockInfoNote()
        }

        // Fixed bottom buttons
        Column(
            Modifier.fillMaxWidth().background(Ms.Paper).drawBehind {
                drawLine(Ms.Line, Offset(0f, 0f), Offset(size.width, 0f), 1.dp.toPx())
            }.padding(start = 18.dp, end = 18.dp, top = 12.dp, bottom = 18.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            MsButton(
                text = "Continue",
                kind = BtnKind.Primary,
                modifier = Modifier.fillMaxWidth(),
                enabled = vm.onbReports.isNotEmpty(),
            ) {
                vm.nextOnboardingStep()
            }
            Box(
                Modifier.heightIn(min = 44.dp).pressable { vm.nextOnboardingStep() },
                contentAlignment = Alignment.Center,
            ) {
                T("Skip for now", 15, 600, Ms.Muted)
            }
        }
    }
}

// ====================== STEP 3: BILLS AND INSURANCE ======================

@Composable
private fun Step3BillsAndInsurance(vm: MedSureViewModel) {
    val context = LocalContext.current
    // Local copy for unsaved skip support
    var tempCompany by remember { mutableStateOf(vm.onbInsCompany) }
    var tempPolicy by remember { mutableStateOf(vm.onbInsPolicy) }

    val singlePicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) {
            vm.onbInsDoc = queryDocInfo(context, uri)
        }
    }

    Column(Modifier.fillMaxSize()) {
        Column(
            Modifier.weight(1f).verticalScroll(rememberScrollState())
                .padding(start = 18.dp, end = 18.dp, top = 12.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(22.dp),
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                D("Bills and insurance", 32, lh = 1.08f)
                T("So we can explain your bills and keep your claim on track.", 15, 400, Ms.Text3, lh = 1.5f)
            }

            // Section 1: Hospital bills
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Caps("HOSPITAL BILLS")
                DocumentUploadSection(
                    docs = vm.onbBills,
                    onAddDocs = { newDocs -> vm.onbBills.addAll(newDocs) },
                    onRemoveDoc = { doc -> vm.onbBills.remove(doc) },
                )
            }

            Rule()

            // Section 2: Insurance policy
            Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Caps("INSURANCE POLICY")
                Field(
                    label = "Insurance company",
                    value = tempCompany,
                    onChange = { tempCompany = it },
                    placeholder = "e.g. Star Health / Care / HDFC ERGO",
                )
                Field(
                    label = "Policy number",
                    value = tempPolicy,
                    onChange = { tempPolicy = it },
                    placeholder = "e.g. POL-123456789",
                )

                // Outlined button to upload policy document
                MsButton(
                    text = "Upload policy document",
                    kind = BtnKind.Ghost,
                    modifier = Modifier.fillMaxWidth(),
                    icon = LineIcons.Paperclip,
                    borderColor = Ms.Teal,
                    textColor = Ms.Teal,
                ) {
                    singlePicker.launch(arrayOf("application/pdf", "image/jpeg", "image/png"))
                }

                // Show chosen policy file if present
                vm.onbInsDoc?.let { doc ->
                    DocumentRow(doc = doc, onRemove = { vm.onbInsDoc = null })
                }
            }
        }

        // Fixed bottom buttons
        Column(
            Modifier.fillMaxWidth().background(Ms.Paper).drawBehind {
                drawLine(Ms.Line, Offset(0f, 0f), Offset(size.width, 0f), 1.dp.toPx())
            }.padding(start = 18.dp, end = 18.dp, top = 12.dp, bottom = 18.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            MsButton(
                text = "Continue",
                kind = BtnKind.Primary,
                modifier = Modifier.fillMaxWidth(),
                enabled = true,
            ) {
                // Continue saves the typed company and policy
                vm.onbInsCompany = tempCompany
                vm.onbInsPolicy = tempPolicy
                vm.nextOnboardingStep()
            }
            Box(
                Modifier.heightIn(min = 44.dp).pressable {
                    // Skip for now does NOT save the typed fields
                    vm.nextOnboardingStep()
                },
                contentAlignment = Alignment.Center,
            ) {
                T("Skip for now", 15, 600, Ms.Muted)
            }
        }
    }
}

// ====================== STEP 4: ADD FAMILY MEMBER ======================

@Composable
private fun Step4AddFamilyMember(vm: MedSureViewModel) {
    var showSheet by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize()) {
        Column(
            Modifier.weight(1f).verticalScroll(rememberScrollState())
                .padding(start = 18.dp, end = 18.dp, top = 12.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp),
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                D("Who helps you at home?", 32, lh = 1.08f)
                T("Add someone you trust. They can follow your recovery and help with the paperwork.", 15, 400, Ms.Text3, lh = 1.5f)
            }

            // Existing dashed "Add a family member" card from Patient Home
            Column(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(22.dp)).background(Ms.Paper)
                    .dashedBorder(Ms.SwitchOff, 2.dp, 22.dp).padding(18.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Tick(48.dp, Ms.Teal) { Ico(LineIcons.UserPlus, Color.White) }
                    D("Add a family member", 20, lh = 1.15f)
                }
                T("They can see your medicines, approve changes and help with your hospital papers.", 15, 400, Ms.Text3, lh = 1.5f)
                MsButton("Add family member", BtnKind.Primary) { showSheet = true }
            }

            // List of added family members
            if (vm.onbFamilyMembers.isNotEmpty()) {
                Caps("ADDED HELPERS (${vm.onbFamilyMembers.size})")
                vm.onbFamilyMembers.forEach { member ->
                    MsCard {
                        Row(
                            Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            Tick(44.dp, Ms.Marigold) {
                                T(member.name.take(1).uppercase(), 16, 800, Ms.Ink)
                            }
                            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                T(member.name, 16, 700)
                                T("+91 ${member.phone}", 13, 500, Ms.Muted)
                            }
                            Box(
                                Modifier.clip(RoundedCornerShape(999.dp))
                                    .background(if (member.canApprove) Ms.AmberBg else Ms.GreenBg)
                                    .padding(horizontal = 10.dp, vertical = 4.dp)
                            ) {
                                T(
                                    if (member.canApprove) "Can approve" else "Can view",
                                    12, 700,
                                    if (member.canApprove) Ms.AmberFg else Ms.GreenFg,
                                )
                            }
                            Box(
                                Modifier.size(34.dp).clip(CircleShape)
                                    .pressable { vm.onbFamilyMembers.remove(member) },
                                contentAlignment = Alignment.Center,
                            ) {
                                Ico(LineIcons.Close, Ms.Muted2, 18.dp)
                            }
                        }
                    }
                }
            }
        }

        // Fixed bottom buttons
        Column(
            Modifier.fillMaxWidth().background(Ms.Paper).drawBehind {
                drawLine(Ms.Line, Offset(0f, 0f), Offset(size.width, 0f), 1.dp.toPx())
            }.padding(start = 18.dp, end = 18.dp, top = 12.dp, bottom = 18.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            MsButton(
                text = "Finish",
                kind = BtnKind.Primary,
                modifier = Modifier.fillMaxWidth(),
                enabled = true,
            ) {
                vm.nextOnboardingStep() // Navigates to Stage.Processing
            }
            if (vm.onbFamilyMembers.isEmpty()) {
                Box(
                    Modifier.heightIn(min = 44.dp).pressable {
                        vm.nextOnboardingStep()
                    },
                    contentAlignment = Alignment.Center,
                ) {
                    T("I'll do this later", 15, 600, Ms.Muted)
                }
            }
        }
    }

    // Bottom sheet for adding family member
    if (showSheet) {
        AddFamilyMemberSheet(
            onDismiss = { showSheet = false },
            onAdd = { newMember ->
                vm.onbFamilyMembers.add(newMember)
                showSheet = false
            },
        )
    }
}

// ====================== REUSABLE COMPONENTS ======================

/**
 * Reusable document upload section containing:
 * - "Upload document" option card
 * - "Use camera" dummy card
 * - Compact list of picked files
 */
@Composable
fun DocumentUploadSection(
    docs: SnapshotStateList<UploadedDoc>,
    onAddDocs: (List<UploadedDoc>) -> Unit,
    onRemoveDoc: (UploadedDoc) -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val multiPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        if (uris.isNotEmpty()) {
            val resolved = uris.map { queryDocInfo(context, it) }
            onAddDocs(resolved)
        }
    }

    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        // Upload document card
        UploadOptionCard(
            title = "Upload document",
            sub = "Choose a file from your phone",
            badgeBg = Ms.Marigold,
            badgeFg = Ms.Ink,
            icon = LineIcons.Upload,
            onClick = {
                multiPicker.launch(arrayOf("application/pdf", "image/jpeg", "image/png"))
            },
        )

        // Use camera dummy card (tactile press effect, does nothing)
        UploadOptionCard(
            title = "Use camera",
            sub = "Take a photo of a page",
            badgeBg = Ms.Teal,
            badgeFg = Color.White,
            icon = LineIcons.Camera,
            onClick = { /* DUMMY: does nothing */ },
        )

        // Selected files list
        if (docs.isNotEmpty()) {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                docs.forEach { doc ->
                    AnimatedVisibility(
                        visible = true,
                        enter = fadeIn(tween(200)) + expandVertically(tween(200)),
                        exit = fadeOut(tween(150)) + shrinkVertically(tween(150)),
                    ) {
                        DocumentRow(doc = doc, onRemove = { onRemoveDoc(doc) })
                    }
                }
            }
        }
    }
}

@Composable
private fun UploadOptionCard(
    title: String,
    sub: String,
    badgeBg: Color,
    badgeFg: Color,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    onClick: () -> Unit,
) {
    val shape = RoundedCornerShape(22.dp)
    Row(
        Modifier.fillMaxWidth().clip(shape).background(Ms.White).border(1.5.dp, Ms.Line3, shape)
            .pressable(pressedScale = 0.98f, onClick = onClick).padding(18.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Tick(52.dp, badgeBg) { Ico(icon, badgeFg, 24.dp) }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            D(title, 20)
            T(sub, 14, 400, Ms.Muted)
        }
        Ico(LineIcons.ChevronRight, Ms.Ink)
    }
}

@Composable
private fun DocumentRow(doc: UploadedDoc, onRemove: () -> Unit) {
    val shape = RoundedCornerShape(16.dp)
    Row(
        Modifier.fillMaxWidth().clip(shape).background(Ms.White).border(1.dp, Ms.Line, shape)
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Tick(40.dp, if (doc.isPdf) Ms.Red.copy(alpha = 0.12f) else Ms.Teal.copy(alpha = 0.12f)) {
            Ico(LineIcons.FileText, if (doc.isPdf) Ms.Red else Ms.Teal, 20.dp)
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            T(doc.name, 14, 700, Ms.Ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
            T(doc.formattedSize, 12, 500, Ms.Muted)
        }
        Box(
            Modifier.size(34.dp).clip(CircleShape).pressable(onClick = onRemove),
            contentAlignment = Alignment.Center,
        ) {
            Ico(LineIcons.Close, Ms.Muted2, 18.dp)
        }
    }
}

@Composable
private fun LockInfoNote() {
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(Ms.Blister).padding(14.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Ico(LineIcons.Lock, Ms.Teal, 18.dp, Modifier.padding(top = 2.dp))
        T(
            "Your documents are private. Only you and the family members you approve can see them.",
            14, 400, Ms.Text3, lh = 1.45f,
        )
    }
}

/** Bottom sheet modal for adding a family member during onboarding. */
@Composable
private fun AddFamilyMemberSheet(
    onDismiss: () -> Unit,
    onAdd: (OnboardingFamilyMember) -> Unit,
) {
    var name by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var canApprove by remember { mutableStateOf(false) }

    val digits = phone.filter { it.isDigit() }
    val isValid = name.trim().isNotBlank() && digits.length == 10

    // Scrim
    Box(
        Modifier.fillMaxSize().background(Ms.Ink.copy(alpha = 0.5f))
            .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null) { onDismiss() },
        contentAlignment = Alignment.BottomCenter,
    ) {
        // Sheet content
        Column(
            Modifier.fillMaxWidth()
                .clip(RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp))
                .background(Ms.Paper)
                .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null) {}
                .padding(start = 20.dp, end = 20.dp, top = 20.dp, bottom = 28.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                D("Add family member", 22)
                Box(
                    Modifier.size(36.dp).clip(CircleShape).pressable { onDismiss() },
                    contentAlignment = Alignment.Center,
                ) {
                    Ico(LineIcons.Close, Ms.Muted2, 20.dp)
                }
            }

            Field(
                label = "Name",
                value = name,
                onChange = { name = it },
                placeholder = "Full name",
            )

            // Mobile with +91 prefix
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                T("Mobile number", 14, 700, Ms.Text3)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    val shape = RoundedCornerShape(14.dp)
                    Box(
                        Modifier.height(54.dp).clip(shape).background(Ms.Blister).border(1.5.dp, Ms.Line2, shape).padding(horizontal = 14.dp),
                        contentAlignment = Alignment.Center,
                    ) { T("+91", 17, 700) }
                    Field(
                        label = null,
                        value = phone,
                        onChange = { phone = it.filter { c -> c.isDigit() || c == ' ' }.take(11) },
                        placeholder = "98765 43210",
                        modifier = Modifier.weight(1f),
                        keyboard = KeyboardType.Phone,
                    )
                }
            }

            // Permission selector
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                T("Permission", 14, 700, Ms.Text3)
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    PermissionPillChip(
                        label = "Can view",
                        selected = !canApprove,
                        modifier = Modifier.weight(1f),
                        onClick = { canApprove = false },
                    )
                    PermissionPillChip(
                        label = "Can view and approve",
                        selected = canApprove,
                        modifier = Modifier.weight(1f),
                        onClick = { canApprove = true },
                    )
                }
            }

            Spacer(Modifier.height(4.dp))

            MsButton(
                text = "Add",
                kind = BtnKind.Primary,
                modifier = Modifier.fillMaxWidth(),
                enabled = isValid,
            ) {
                onAdd(OnboardingFamilyMember(name.trim(), digits, canApprove))
            }

            Box(
                Modifier.fillMaxWidth().heightIn(min = 40.dp).pressable { onDismiss() },
                contentAlignment = Alignment.Center,
            ) {
                T("Cancel", 15, 600, Ms.Muted)
            }
        }
    }
}

@Composable
private fun PermissionPillChip(label: String, selected: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val shape = RoundedCornerShape(999.dp)
    val bg = if (selected) Ms.Teal else Ms.White
    val fg = if (selected) Color.White else Ms.Text3
    val border = if (selected) Ms.Teal else Ms.Line2
    Box(
        modifier.heightIn(min = 44.dp).clip(shape).background(bg).border(1.5.dp, border, shape)
            .pressable(onClick = onClick)
            .padding(horizontal = 10.dp, vertical = 8.dp),
        contentAlignment = Alignment.Center,
    ) {
        T(label, 13, 600, fg, align = TextAlign.Center)
    }
}
