package com.powerbank.medsure.ui.debug

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.powerbank.medsure.state.MedSureViewModel
import com.powerbank.medsure.ui.components.*
import com.powerbank.medsure.ui.theme.Ms
import org.json.JSONArray
import org.json.JSONObject

/**
 * Optional debug-only screen / dialog to inspect real pipeline extractions:
 * - Document type
 * - Key extracted fields
 * - Extraction method (text_layer vs device_ocr, read on the phone, vs demo_fallback)
 * - Classification and extraction confidence
 * - Validation warnings
 * - Formatted structured JSON inspection
 */
@Composable
fun ExtractedDataDialog(vm: MedSureViewModel) {
    Dialog(
        onDismissRequest = { vm.showExtractionDebug = false },
        properties = DialogProperties(usePlatformDefaultWidth = false),
    ) {
        Box(
            Modifier.fillMaxSize().background(Ms.Outside).padding(16.dp),
            contentAlignment = Alignment.Center,
        ) {
            Column(
                Modifier.fillMaxHeight(0.92f)
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(24.dp))
                    .background(Ms.Paper)
                    .padding(20.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                // Header
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column {
                        D("Extracted Data", 22)
                        T("Real document pipeline output", 13, 400, Ms.Muted)
                    }
                    MsButton("Close", BtnKind.Light, height = 38.dp) {
                        vm.showExtractionDebug = false
                    }
                }

                HorizontalDivider(color = Ms.BlisterEdge)

                val data = vm.extractedData
                if (data == null) {
                    Box(
                        Modifier.fillMaxWidth().weight(1f),
                        contentAlignment = Alignment.Center,
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Ico(LineIcons.FileText, Ms.Muted, 40.dp)
                            D("No Extractions Yet", 18)
                            T("Complete onboarding with documents or upload a file to inspect structured JSON output.", 14, 400, Ms.Text3)
                        }
                    }
                } else {
                    val docsArray = data.optJSONArray("documents") ?: JSONArray()
                    val totalDocs = data.optInt("total_documents", docsArray.length())
                    val schemaVer = data.optString("schema_version", "1.0.0")

                    LazyColumn(
                        Modifier.fillMaxWidth().weight(1f),
                        verticalArrangement = Arrangement.spacedBy(16.dp),
                    ) {
                        item {
                            MsCard(gap = 8.dp) {
                                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                    T("Schema Version: $schemaVer", 12, 700, Ms.Muted)
                                    T("Total Documents: $totalDocs", 12, 700, Ms.Muted)
                                }
                            }
                        }

                        items(docsArray.length()) { i ->
                            val docObj = docsArray.optJSONObject(i) ?: JSONObject()
                            DocumentExtractionCard(docObj)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun DocumentExtractionCard(doc: JSONObject) {
    var showRawJson by remember { mutableStateOf(false) }

    val docType = doc.optString("doc_type", "unknown")
    val sourceFile = doc.optString("source_file", "document")
    val method = doc.optString("extraction_method", "text_layer")
    val classConf = doc.optDouble("classification_confidence", 0.0)
    val extConf = doc.optDouble("extraction_confidence", 0.0)
    val pages = doc.optInt("pages", 1)
    val warningsArray = doc.optJSONArray("warnings") ?: JSONArray()
    val fields = doc.optJSONObject("fields") ?: JSONObject()

    MsCard(gap = 12.dp) {
        // Card title & badges
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                D(sourceFile, 16)
                T("Type: $docType · $pages page(s)", 13, 600, Ms.Muted)
            }
            // Method badge
            Box(
                Modifier.clip(RoundedCornerShape(999.dp))
                    .background(if (method == "device_ocr") Ms.AmberBg else Ms.GreenBg)
                    .padding(horizontal = 8.dp, vertical = 4.dp)
            ) {
                T(method.uppercase(), 11, 800, if (method == "device_ocr") Ms.AmberFg else Ms.GreenFg)
            }
        }

        // Confidence row
        Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            T(String.format("Classify: %.0f%%", classConf * 100), 12, 500, Ms.Muted)
            T(String.format("Extract: %.0f%%", extConf * 100), 12, 500, Ms.Muted)
        }

        // Warnings list (if present)
        if (warningsArray.length() > 0) {
            Column(
                Modifier.fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .background(Ms.AmberBg)
                    .padding(10.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                T("Warnings (${warningsArray.length()}):", 12, 700, Ms.AmberFg)
                for (w in 0 until warningsArray.length()) {
                    T("• " + warningsArray.optString(w), 12, 400, Ms.AmberFg)
                }
            }
        }

        // Key extracted summary
        KeyFieldsSummary(docType, fields)

        // Raw JSON inspection toggle
        Box(
            Modifier.fillMaxWidth()
                .clip(RoundedCornerShape(10.dp))
                .background(Ms.Blister)
                .clickable { showRawJson = !showRawJson }
                .padding(horizontal = 12.dp, vertical = 8.dp)
        ) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                T(if (showRawJson) "Hide Raw JSON" else "Inspect Raw JSON", 13, 600, Ms.Ink)
                Ico(if (showRawJson) LineIcons.ChevronDown else LineIcons.ChevronRight, Ms.Ink, 16.dp)
            }
        }

        AnimatedVisibility(visible = showRawJson) {
            Box(
                Modifier.fillMaxWidth()
                    .clip(RoundedCornerShape(10.dp))
                    .background(Ms.Outside)
                    .padding(10.dp)
            ) {
                T(doc.toString(2), 11, 400, Ms.Ink)
            }
        }
    }
}

@Composable
private fun KeyFieldsSummary(docType: String, fields: JSONObject) {
    Column(
        Modifier.fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(Ms.Blister)
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        T("KEY EXTRACTED FIELDS", 11, 800, Ms.Muted)

        when (docType) {
            "discharge_summary" -> {
                val pt = fields.optJSONObject("patient") ?: JSONObject()
                FieldRow("Patient Name", pt.optString("name", "—"))
                FieldRow("UHID", pt.optString("uhid", "—"))
                FieldRow("Admission", fields.optString("admission_date", "—"))
                FieldRow("Discharge", fields.optString("discharge_date", "—"))
                FieldRow("Diagnosis", fields.optString("diagnosis", "—"))
                val meds = fields.optJSONArray("medicines") ?: JSONArray()
                FieldRow("Medicines Count", "${meds.length()} prescribed")
            }
            "investigation_report" -> {
                FieldRow("Report Date", fields.optString("report_date", "—"))
                val tests = fields.optJSONArray("tests") ?: JSONArray()
                FieldRow("Tests Extracted", "${tests.length()} tests")
                FieldRow("Impression", fields.optString("impression", "—"))
            }
            "hospital_bill", "pharmacy_bill", "lab_bill" -> {
                FieldRow("Vendor", fields.optString("vendor", "—"))
                FieldRow("Bill No", fields.optString("bill_no", "—"))
                FieldRow("Bill Date", fields.optString("bill_date", "—"))
                val items = fields.optJSONArray("line_items") ?: JSONArray()
                FieldRow("Line Items", "${items.length()} items")
                FieldRow("Gross Total", "₹" + fields.optDouble("gross_total", 0.0))
                FieldRow("Balance Due", "₹" + fields.optDouble("balance_due", 0.0))
            }
            "insurance_policy" -> {
                FieldRow("Insurer", fields.optString("insurer", "—"))
                FieldRow("Policy No", fields.optString("policy_no", "—"))
                FieldRow("Sum Insured", "₹" + fields.optDouble("sum_insured", 0.0))
                FieldRow("Copay", fields.optDouble("copay_percent", 0.0).toString() + "%")
                FieldRow("Claim Submission", fields.optInt("claim_submission_days", 0).toString() + " days")
            }
            else -> {
                FieldRow("Document Summary", fields.optString("summary", "Unclassified / Raw document"))
            }
        }
    }
}

@Composable
private fun FieldRow(label: String, value: String) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        T(label, 13, 500, Ms.Muted)
        T(value.take(35), 13, 700, Ms.Ink)
    }
}
