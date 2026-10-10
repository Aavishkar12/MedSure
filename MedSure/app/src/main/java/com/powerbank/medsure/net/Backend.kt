package com.powerbank.medsure.net

import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.messaging.FirebaseMessaging
import com.powerbank.medsure.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

data class LocalOcrPagePayload(
    val pageNumber: Int,
    val text: String,
    val confidence: Double? = null,
)

data class LocalOcrDocumentPayload(
    val filename: String,
    val docType: String = "unknown",
    val pages: List<LocalOcrPagePayload>,
    val fileHash: String? = null,
    val warnings: List<String> = emptyList(),
)

/** Talks to the MedSure backend. Every call carries the signed-in user's Firebase ID token. */
object Backend {
    private val auth get() = FirebaseAuth.getInstance()

    val signedIn get() = auth.currentUser != null

    /** Gives this phone a Firebase account. The on-screen OTP is a demo; this is the real identity. */
    suspend fun signIn() {
        if (auth.currentUser == null) auth.signInAnonymously().await()
    }

    suspend fun signOut() {
        runCatching { request("DELETE", "/devices/" + URLEncoder.encode(pushToken(), "UTF-8")) }
        auth.signOut()
    }

    /** A blank name is not sent, so the backend keeps the one it already has. */
    suspend fun saveProfile(name: String, phone: String, email: String) {
        val body = JSONObject().put("phone", phone).put("email", email)
        if (name.isNotBlank()) body.put("name", name)
        request("PATCH", "/me", body)
    }

    /** Registers this phone for push notifications. Call after sign-in and whenever the token changes. */
    suspend fun registerDevice(token: String? = null) {
        request("POST", "/devices", JSONObject().put("token", token ?: pushToken()))
    }

    /** The patient's own case, or for family the newest case they were added to. Null if there is none yet. */
    suspend fun myCaseId(asPatient: Boolean): Int? {
        val cases = JSONArray(request("GET", "/cases?as_patient=$asPatient"))
        return if (cases.length() > 0) cases.getJSONObject(cases.length() - 1).getInt("id") else null
    }

    class RemoteMember(val name: String, val relation: String, val canApprove: Boolean, val phone: String, val you: Boolean)

    /** Everyone on the case, including people invited who have not signed in yet. */
    suspend fun members(caseId: Int): List<RemoteMember> {
        val all = JSONArray(request("GET", "/cases/$caseId/members"))
        return List(all.length()) {
            val m = all.getJSONObject(it)
            RemoteMember(m.optString("name"), m.optString("relation"), m.optBoolean("can_approve"), if (m.isNull("phone")) "" else m.getString("phone"), m.optBoolean("you"))
        }
    }

    /** Shared between the phones on a case: taken (dose id -> true), taken_day, med_change. */
    suspend fun sharedState(caseId: Int): JSONObject = JSONObject(request("GET", "/cases/$caseId/state"))

    suspend fun sendTaken(caseId: Int, taken: Map<String, Boolean>, day: String) {
        request("PATCH", "/cases/$caseId/state", JSONObject().put("taken", JSONObject(taken)).put("taken_day", day))
    }

    suspend fun sendMedChange(caseId: Int, status: String) {
        request("PATCH", "/cases/$caseId/state", JSONObject().put("med_change", status))
    }

    suspend fun createCase(patientName: String, relation: String): Int =
        JSONObject(request("POST", "/cases", JSONObject().put("patient_name", patientName).put("relation", relation)))
            .getInt("id")

    suspend fun addMember(caseId: Int, name: String, relation: String, canApprove: Boolean, phone: String, email: String) {
        val body = JSONObject().put("name", name).put("relation", relation).put("can_approve", canApprove)
        if (phone.isNotBlank()) body.put("phone", phone)
        if (email.isNotBlank()) body.put("email", email)
        request("POST", "/cases/$caseId/members", body)
    }

    /** level: 0 on track, 1 keep watch, 2 needs help now. Family is notified when it is above 0. */
    suspend fun checkin(caseId: Int, levels: List<Int>, note: String): Int {
        val answers = JSONObject().put("level", levels.maxOrNull() ?: 0).put("levels", JSONArray(levels)).put("note", note)
        return JSONObject(request("POST", "/cases/$caseId/checkins", JSONObject().put("answers", answers))).getInt("id")
    }

    /** Attaches or changes the note on a check-in that was already sent. */
    suspend fun updateCheckinNote(checkinId: Int, note: String) {
        request("PATCH", "/checkins/$checkinId", JSONObject().put("note", note))
    }

    /** A check-in as stored on the backend. */
    class RemoteCheckin(val id: Int, val levels: List<Int>, val note: String, val createdAt: String) {
        /** True when it was made today, in this phone's time zone. The server stores UTC. */
        val isToday: Boolean
            get() = runCatching {
                val utc = java.time.LocalDateTime.parse(createdAt.removeSuffix("Z").substringBefore('+'))
                utc.atOffset(java.time.ZoneOffset.UTC).atZoneSameInstant(java.time.ZoneId.systemDefault()).toLocalDate() == java.time.LocalDate.now()
            }.getOrDefault(true)
    }

    /** The most recent check-in on this case, or null if there is none yet. */
    suspend fun latestCheckin(caseId: Int): RemoteCheckin? {
        val all = JSONArray(request("GET", "/cases/$caseId/checkins"))
        if (all.length() == 0) return null
        val last = all.getJSONObject(all.length() - 1)
        val answers = last.getJSONObject("answers")
        val levels = answers.optJSONArray("levels") ?: return null
        return RemoteCheckin(last.getInt("id"), List(levels.length()) { levels.getInt(it) }, answers.optString("note"), last.getString("created_at"))
    }

    /** Sends only text recognized on-device. Original medical files never leave the phone. */
    suspend fun submitRecognizedDocuments(caseId: Int, docs: List<LocalOcrDocumentPayload>): JSONObject {
        require(docs.isNotEmpty()) { "At least one recognized document is required" }
        val documents = JSONArray()
        docs.forEach { doc ->
            val pages = JSONArray()
            doc.pages.forEach { page ->
                val json = JSONObject()
                    .put("page_number", page.pageNumber)
                    .put("text", page.text)
                page.confidence?.let { json.put("confidence", it) }
                pages.put(json)
            }
            val json = JSONObject()
                .put("filename", doc.filename)
                .put("doc_type", doc.docType)
                .put("pages", pages)
                .put("warnings", JSONArray(doc.warnings))
            doc.fileHash?.let { json.put("file_hash", it) }
            documents.put(json)
        }
        return JSONObject(
            request("POST", "/cases/$caseId/documents", JSONObject().put("documents", documents))
        )
    }

    suspend fun jobStatus(jobId: String): JSONObject = JSONObject(request("GET", "/jobs/$jobId"))

    suspend fun caseExtractions(caseId: Int): JSONObject =
        JSONObject(request("GET", "/cases/$caseId/extractions"))

    suspend fun dischargeCard(caseId: Int): JSONObject? = try {
        JSONObject(request("GET", "/cases/$caseId/discharge-card"))
    } catch (e: IOException) {
        if (e.message?.contains("(404)") == true) null else throw e
    }

    suspend fun bill(caseId: Int): JSONObject = JSONObject(request("GET", "/cases/$caseId/bill"))

    suspend fun documents(caseId: Int): JSONArray = JSONArray(request("GET", "/cases/$caseId/documents"))

    private suspend fun pushToken(): String = FirebaseMessaging.getInstance().token.await()

    private var base: String? = null

    /**
     * API_URL may list several addresses separated by commas; the first one that answers is used.
     * That lets one build work on the laptop's hotspot, on shared wifi and against a hosted server.
     */
    private suspend fun baseUrl(): String = base ?: withContext(Dispatchers.IO) {
        val candidates = BuildConfig.API_URL.split(',').map { it.trim().trimEnd('/') }.filter { it.isNotEmpty() }
        candidates.firstOrNull(::reachable) ?: throw IOException("Backend not reachable at any of $candidates")
    }.also { base = it }

    private fun reachable(url: String): Boolean = runCatching {
        val conn = URL("$url/health").openConnection() as HttpURLConnection
        try {
            conn.connectTimeout = 2500
            conn.readTimeout = 2500
            conn.responseCode == 200
        } finally {
            conn.disconnect()
        }
    }.getOrDefault(false)

    private suspend fun request(method: String, path: String, body: JSONObject? = null): String {
        val token = auth.currentUser?.getIdToken(false)?.await()?.token ?: throw IOException("Not signed in")
        val url = baseUrl()
        return withContext(Dispatchers.IO) {
            val conn = URL(url + path).openConnection() as HttpURLConnection
            try {
                conn.requestMethod = method
                conn.connectTimeout = 15_000
                conn.readTimeout = 30_000
                conn.setRequestProperty("Authorization", "Bearer $token")
                if (body != null) {
                    conn.doOutput = true
                    conn.setRequestProperty("Content-Type", "application/json")
                    conn.outputStream.use { it.write(body.toString().toByteArray()) }
                }
                val code = conn.responseCode
                val text = (if (code in 200..299) conn.inputStream else conn.errorStream)
                    ?.bufferedReader()?.use { it.readText() }.orEmpty()
                if (code !in 200..299) throw IOException("$method $path failed ($code): ${text.take(200)}")
                text
            } catch (e: java.net.SocketException) {
                base = null // the network changed; look for the backend again next time
                throw e
            } catch (e: java.net.SocketTimeoutException) {
                base = null
                throw e
            } finally {
                conn.disconnect()
            }
        }
    }
}
