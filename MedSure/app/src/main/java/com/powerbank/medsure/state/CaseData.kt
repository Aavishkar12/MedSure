package com.powerbank.medsure.state

import org.json.JSONArray
import org.json.JSONObject

// What the backend read from this case's documents. Parsed from the API's JSON; every field is optional
// on the wire, so a document the AI could only partly read still shows what it did read.

data class MedicineItemModel(
    val name: String,
    val dose: String = "",
    val schedule: String = "",
    val purpose: String = "",
    val days: Int? = null,
    val sourcePage: Int? = null,
)

data class LabValueModel(
    val name: String,
    val value: String = "",
    val unit: String = "",
    val range: String = "",
    val status: String = "unknown", // low | normal | high | unknown
    val plain: String = "",
    val sourcePage: Int? = null,
)

/** A precaution, warning sign or follow-up line, with the page it came from. */
data class SourcedText(val text: String, val sub: String = "", val sourcePage: Int? = null)

data class DischargeCardModel(
    val documentId: Int,
    val summary: String,
    val hospital: String,
    val doctor: String,
    val admissionDate: String,
    val dischargeDate: String,
    val diagnosisName: String,
    val diagnosisPlain: String,
    val diagnosisPage: Int?,
    val otherDiagnoses: List<SourcedText>,
    val medicines: List<MedicineItemModel>,
    val labValues: List<LabValueModel>,
    val precautions: List<SourcedText>,
    val warningSigns: List<SourcedText>,
    val followUps: List<SourcedText>,
    val disclaimer: String,
)

data class BillItemModel(
    val id: Int,
    val description: String,
    val amount: Double,
    val explanation: String = "",
    val worthAsking: Boolean = false,
    val askReason: String = "",
)

data class BillDataModel(val total: Double, val items: List<BillItemModel>)

data class DocumentInfoModel(
    val id: Int,
    val docType: String,
    val filename: String,
    val status: String, // processing | ready | failed
    val error: String? = null,
)

data class CoverageItemModel(
    val billItemId: Int,
    val description: String,
    val amount: Double,
    val status: String, // covered | partly_covered | not_covered | unclear
    val claimable: Double,
    val reason: String,
    val policyQuote: String,
)

data class CoverageModel(
    val headline: String,
    val explanation: String,
    val items: List<CoverageItemModel>,
    val billed: Double,
    val estimatedClaimable: Double,
    val outOfPocket: Double,
    val copay: Double,
    val copayPercent: Double,
    val unclear: Double,
    val notes: List<String>,
    val insurer: String,
    val policyNumber: String,
    val byAi: Boolean,
    val disclaimer: String,
)

private fun JSONObject.text(key: String): String = if (isNull(key)) "" else optString(key).trim()
private fun JSONObject.page(key: String = "source_page"): Int? = if (has(key) && !isNull(key)) optInt(key) else null
private fun <T> JSONArray?.objects(f: (JSONObject) -> T?): List<T> =
    if (this == null) emptyList() else (0 until length()).mapNotNull { optJSONObject(it)?.let(f) }

/** Lines like precautions may arrive as {"text", "source_page"} objects or as plain strings. */
private fun JSONArray?.sourced(): List<SourcedText> {
    if (this == null) return emptyList()
    return (0 until length()).mapNotNull { i ->
        when (val v = opt(i)) {
            is JSONObject -> v.text("text").takeIf { it.isNotEmpty() }?.let { SourcedText(it, sourcePage = v.page()) }
            is String -> v.trim().takeIf { it.isNotEmpty() }?.let { SourcedText(it) }
            else -> null
        }
    }
}

/** GET /cases/{id}/discharge-card */
fun parseDischargeCard(json: JSONObject): DischargeCardModel {
    val data = json.optJSONObject("data") ?: JSONObject()
    val diagnosis = data.optJSONObject("diagnosis") ?: JSONObject()
    return DischargeCardModel(
        documentId = json.optInt("document_id"),
        summary = data.text("summary"),
        hospital = data.text("hospital"),
        doctor = data.text("doctor"),
        admissionDate = data.text("admission_date"),
        dischargeDate = data.text("discharge_date"),
        diagnosisName = diagnosis.text("name"),
        diagnosisPlain = diagnosis.text("plain"),
        diagnosisPage = diagnosis.page(),
        otherDiagnoses = data.optJSONArray("other_diagnoses").objects { d ->
            d.text("name").takeIf { it.isNotEmpty() }?.let { SourcedText(it, d.text("plain"), d.page()) }
        },
        medicines = data.optJSONArray("medicines").objects { m ->
            m.text("name").takeIf { it.isNotEmpty() }?.let {
                MedicineItemModel(it, m.text("dose"), m.text("schedule"), m.text("purpose"),
                    if (m.has("days") && !m.isNull("days")) m.optInt("days") else null, m.page())
            }
        },
        labValues = data.optJSONArray("lab_values").objects { l ->
            l.text("name").takeIf { it.isNotEmpty() }?.let {
                LabValueModel(it, l.text("value"), l.text("unit"), l.text("range"), l.text("status").ifEmpty { "unknown" }, l.text("plain"), l.page())
            }
        },
        precautions = data.optJSONArray("precautions").sourced(),
        warningSigns = data.optJSONArray("warning_signs").sourced(),
        followUps = data.optJSONArray("follow_ups").objects { f ->
            f.text("what").takeIf { it.isNotEmpty() }?.let { SourcedText(it, f.text("when"), f.page()) }
        },
        disclaimer = data.text("disclaimer").ifEmpty { "This explains your documents. It is not medical advice." },
    )
}

/** GET /cases/{id}/bill */
fun parseBill(json: JSONObject): BillDataModel = BillDataModel(
    total = json.optDouble("total", 0.0),
    items = json.optJSONArray("items").objects { i ->
        BillItemModel(i.optInt("id"), i.text("description").ifEmpty { "Item" }, i.optDouble("amount", 0.0),
            i.text("explanation"), i.optBoolean("worth_asking"), i.text("ask_reason"))
    },
)

/** GET /cases/{id}/documents */
fun parseDocuments(arr: JSONArray): List<DocumentInfoModel> = arr.objects { d ->
    DocumentInfoModel(d.optInt("id"), d.text("doc_type"), d.text("filename"), d.text("status"), d.text("error").ifEmpty { null })
}

/** GET /cases/{id}/coverage */
fun parseCoverage(json: JSONObject): CoverageModel {
    val data = json.optJSONObject("data") ?: JSONObject()
    val totals = data.optJSONObject("totals") ?: JSONObject()
    val notes = data.optJSONArray("notes")
    return CoverageModel(
        headline = data.text("headline"),
        explanation = data.text("explanation"),
        items = data.optJSONArray("items").objects { i ->
            CoverageItemModel(i.optInt("bill_item_id"), i.text("description"), i.optDouble("amount", 0.0),
                i.text("status").ifEmpty { "unclear" }, i.optDouble("claimable_amount", 0.0), i.text("reason"), i.text("policy_quote"))
        },
        billed = totals.optDouble("billed", 0.0),
        estimatedClaimable = totals.optDouble("estimated_claimable", 0.0),
        outOfPocket = totals.optDouble("estimated_out_of_pocket", 0.0),
        copay = totals.optDouble("copay", 0.0),
        copayPercent = totals.optDouble("copay_percent", 0.0),
        unclear = totals.optDouble("unclear", 0.0),
        notes = if (notes == null) emptyList() else (0 until notes.length()).map { notes.optString(it) }.filter { it.isNotBlank() },
        insurer = data.text("insurer"),
        policyNumber = data.text("policy_number"),
        byAi = data.text("method") == "ai",
        disclaimer = data.text("disclaimer"),
    )
}

/** ₹1,84,350: Indian digit grouping, no paise. */
fun rupees(amount: Double): String {
    val whole = Math.round(amount)
    val s = kotlin.math.abs(whole).toString()
    val grouped = if (s.length <= 3) s else {
        val head = s.dropLast(3)
        head.reversed().chunked(2).joinToString(",").reversed() + "," + s.takeLast(3)
    }
    return (if (whole < 0) "-₹" else "₹") + grouped
}
