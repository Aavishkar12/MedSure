package com.powerbank.medsure.ui.patient

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.powerbank.medsure.state.CoverageModel
import com.powerbank.medsure.state.MedSureViewModel
import com.powerbank.medsure.state.rupees
import com.powerbank.medsure.ui.components.*
import com.powerbank.medsure.ui.theme.Ms

private val PAPER_TYPES = arrayOf("application/pdf", "image/*")

/** Picks PDFs or photos and sends them to be read. docType null: the server works out what each one is. */
@Composable
fun AddPapersButton(vm: MedSureViewModel, docType: String? = null, kind: BtnKind = BtnKind.Light, modifier: Modifier = Modifier) {
    val t = vm.tx
    val context = LocalContext.current
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        if (uris.isNotEmpty()) vm.addDocuments(context, uris.map { queryDocInfo(context, it) }, docType)
    }
    MsButton(
        if (vm.addingDocs) t["addingPapers"] else t["addPapers"], kind, modifier.fillMaxWidth(),
        enabled = !vm.addingDocs, icon = LineIcons.Paperclip, height = 46.dp,
    ) { picker.launch(PAPER_TYPES) }
    vm.addDocsError?.let { T(it, 13, 400, Ms.Red, lh = 1.4f) }
}

/** Shown while the case has no documents yet: everything in the app is built from the patient's own papers. */
@Composable
fun PapersPrompt(vm: MedSureViewModel) {
    if (vm.hasCaseData) return
    val t = vm.tx
    MsCard(bg = Ms.FlagBg, border = Ms.FlagBorder, gap = 10.dp) {
        T(t["noPapersTitle"], 16, 700, Ms.Brown)
        T(t["noPapersBody"], 14, 400, Ms.Brown, lh = 1.45f)
        AddPapersButton(vm, kind = BtnKind.Mari)
    }
}

/** A message in place of a section that has nothing to show yet. */
@Composable
fun EmptyNote(text: String) {
    T(text, 15, 400, Ms.Muted, Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(Ms.Blister).padding(14.dp), lh = 1.45f)
}

/** "Page 3": where a line came from in the patient's papers. */
fun pageRef(vm: MedSureViewModel, page: Int?): String = if (page == null) vm.tx["fromPapers"] else "${vm.tx["page"]} $page"

/** The bill compared line by line with the insurance policy. */
@Composable
fun CoverageSection(vm: MedSureViewModel) {
    val t = vm.tx
    val cov: CoverageModel? = vm.coverage
    val hasBill = vm.billData != null
    val hasPolicy = vm.caseDocuments.any { it.docType == "policy" && it.status == "ready" }
    D(t["covTitle"], 22)
    if (cov == null) {
        MsCard(gap = 12.dp) {
            T(if (hasBill && hasPolicy) t["covIntro"] else t["covNeedBoth"], 15, 400, Ms.Text3, lh = 1.45f)
            if (hasBill && hasPolicy) {
                MsButton(if (vm.coverageRunning) t["covRunning"] else t["covRun"], BtnKind.Primary, Modifier.fillMaxWidth(),
                    enabled = !vm.coverageRunning) { vm.checkCoverage() }
            } else {
                AddPapersButton(vm)
            }
        }
        return
    }
    MsCard(gap = 12.dp) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Stat(t["covBilled"], rupees(cov.billed), Ms.Ink, Modifier.weight(1f))
            Stat(t["covClaimable"], rupees(cov.estimatedClaimable), Ms.GreenFg, Modifier.weight(1f))
            Stat(t["covYouPay"], rupees(cov.outOfPocket), Ms.AmberText, Modifier.weight(1f))
        }
        T(cov.headline, 15, 600, lh = 1.45f)
        if (cov.explanation.isNotBlank()) T(cov.explanation, 15, 400, Ms.Text3, lh = 1.5f)
        if (!cov.byAi) T(t["covBasic"], 13, 600, Ms.AmberText)
    }
    MsCard(gap = 14.dp) {
        cov.items.forEach { item ->
            val (label, bg, fg) = when (item.status) {
                "covered" -> Triple(t["covCovered"], Ms.GreenBg, Ms.GreenFg)
                "partly_covered" -> Triple(t["covPartly"], Ms.AmberBg, Ms.AmberDark)
                "not_covered" -> Triple(t["covNot"], Ms.FlagBg, Ms.Red)
                else -> Triple(t["covUnclear"], Ms.Blister, Ms.Muted)
            }
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.Top) {
                    T(item.description, 15, 700, modifier = Modifier.weight(1f))
                    T(rupees(item.amount), 15, 700)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    T(label, 12, 800, fg, Modifier.clip(RoundedCornerShape(999.dp)).background(bg).padding(horizontal = 10.dp, vertical = 3.dp))
                    if (item.status == "partly_covered") T("${t["covClaimLine"]} ${rupees(item.claimable)}", 13, 600, Ms.Muted)
                }
                if (item.reason.isNotBlank()) T(item.reason, 14, 400, Ms.Text3, lh = 1.4f)
                if (item.policyQuote.isNotBlank()) T("${t["covPolicySays"]}: “${item.policyQuote}”", 13, 400, Ms.Muted, lh = 1.4f)
            }
        }
    }
    cov.notes.forEach { note -> T("• $note", 14, 400, Ms.Text3, lh = 1.45f) }
    if (cov.disclaimer.isNotBlank()) T(cov.disclaimer, 13, 400, Ms.Muted, lh = 1.4f)
    MsButton(if (vm.coverageRunning) t["covRunning"] else t["covRerun"], BtnKind.Light, Modifier.fillMaxWidth(),
        enabled = !vm.coverageRunning, height = 44.dp) { vm.checkCoverage() }
}

@Composable
private fun Stat(label: String, value: String, color: androidx.compose.ui.graphics.Color, modifier: Modifier) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        T(label, 12, 700, Ms.Muted)
        D(value, 18, color = color)
    }
}
