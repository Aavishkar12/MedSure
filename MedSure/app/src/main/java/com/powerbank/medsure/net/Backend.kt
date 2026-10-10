package com.powerbank.medsure.net

import android.content.Context
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.messaging.FirebaseMessaging
import com.powerbank.medsure.BuildConfig
import com.powerbank.medsure.state.DocumentInfoModel
import com.powerbank.medsure.state.UploadedDoc
import com.powerbank.medsure.state.parseDocuments
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

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
        /** The day it was made, in this phone's time zone. The server stores UTC. */
        val day: java.time.LocalDate?
            get() = runCatching {
                val utc = java.time.LocalDateTime.parse(createdAt.removeSuffix("Z").substringBefore('+'))
                utc.atOffset(java.time.ZoneOffset.UTC).atZoneSameInstant(java.time.ZoneId.systemDefault()).toLocalDate()
            }.getOrNull()
        val isToday: Boolean get() = (day ?: java.time.LocalDate.now()) == java.time.LocalDate.now()
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

    // ---------- Documents ----------

    /**
     * Uploads one document (multipart) and returns its id. The backend reads it in the background:
     * poll [document] until its status is no longer "processing".
     * docType: discharge_summary, lab_report, prescription, bill, policy, id_proof, or null to let the
     * server decide from the text.
     */
    suspend fun uploadDocument(context: Context, caseId: Int, doc: UploadedDoc, docType: String?): Int {
        val token = idToken()
        val url = baseUrl() + "/cases/$caseId/documents"
        val boundary = "MedSure" + System.nanoTime()
        return withContext(Dispatchers.IO) {
            val conn = URL(url).openConnection() as HttpURLConnection
            try {
                conn.requestMethod = "POST"
                conn.connectTimeout = 30_000
                conn.readTimeout = 120_000
                conn.doOutput = true
                conn.setChunkedStreamingMode(64 * 1024) // large scans are streamed, not held in memory
                conn.setRequestProperty("Authorization", "Bearer $token")
                conn.setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
                conn.outputStream.use { out ->
                    val crlf = "\r\n"
                    fun part(headers: String) = out.write("--$boundary$crlf$headers$crlf$crlf".toByteArray())
                    if (docType != null) {
                        part("Content-Disposition: form-data; name=\"doc_type\"")
                        out.write("$docType$crlf".toByteArray())
                    }
                    val name = doc.name.replace("\"", "'")
                    part("Content-Disposition: form-data; name=\"file\"; filename=\"$name\"${crlf}Content-Type: ${doc.mimeType.ifBlank { "application/octet-stream" }}")
                    val input = context.contentResolver.openInputStream(doc.uri)
                        ?: throw IOException("Cannot open ${doc.name}; pick the file again")
                    input.use { it.copyTo(out) }
                    out.write("$crlf--$boundary--$crlf".toByteArray())
                }
                val code = conn.responseCode
                val text = (if (code in 200..299) conn.inputStream else conn.errorStream)
                    ?.bufferedReader()?.use { it.readText() }.orEmpty()
                if (code !in 200..299) throw IOException("Upload of ${doc.name} failed ($code): ${detail(text)}")
                JSONObject(text).getJSONArray("documents").getJSONObject(0).getInt("id")
            } catch (e: java.net.SocketException) {
                base = null
                throw e
            } finally {
                conn.disconnect()
            }
        }
    }

    suspend fun document(docId: Int): DocumentInfoModel =
        parseDocuments(JSONArray().put(JSONObject(request("GET", "/documents/$docId")))).first()

    /** Reads a failed document again. */
    suspend fun retryDocument(docId: Int) {
        request("POST", "/documents/$docId/retry")
    }

    suspend fun listDocuments(caseId: Int): JSONArray = JSONArray(request("GET", "/cases/$caseId/documents"))

    suspend fun getDischargeCard(caseId: Int): JSONObject? = getOrNull("/cases/$caseId/discharge-card")

    suspend fun getBill(caseId: Int): JSONObject = JSONObject(request("GET", "/cases/$caseId/bill"))

    /** The latest bill-vs-policy comparison, or null before both documents are read. */
    suspend fun getCoverage(caseId: Int): JSONObject? = getOrNull("/cases/$caseId/coverage")

    /** Runs the bill-vs-policy comparison now. */
    suspend fun runCoverage(caseId: Int): JSONObject = JSONObject(request("POST", "/cases/$caseId/coverage"))

    suspend fun getPolicy(caseId: Int): JSONObject? = getOrNull("/cases/$caseId/policy")

    /** The newest AI-drafted claim letter, or null when none has been drafted. */
    suspend fun getClaimDraft(caseId: Int): JSONObject? = getOrNull("/cases/$caseId/claim-draft")

    /** Asks the AI to draft the claim letter from the case's documents. Always a draft until approved. */
    suspend fun prepareClaimDraft(caseId: Int): JSONObject =
        JSONObject(request("POST", "/cases/$caseId/claim-draft", JSONObject().put("kind", "claim_letter")))

    /** A family member who can approve signs off the letter, then it is marked sent. */
    suspend fun approveAndSendDraft(draftId: Int, alreadyApproved: Boolean = false): JSONObject {
        if (!alreadyApproved) request("POST", "/drafts/$draftId/approve")
        return JSONObject(request("POST", "/drafts/$draftId/send"))
    }

    /** Every check-in on the case, oldest first. */
    suspend fun checkins(caseId: Int): List<RemoteCheckin> {
        val all = JSONArray(request("GET", "/cases/$caseId/checkins"))
        return (0 until all.length()).mapNotNull { i ->
            val c = all.getJSONObject(i)
            val answers = c.optJSONObject("answers") ?: return@mapNotNull null
            val levels = answers.optJSONArray("levels")
            RemoteCheckin(
                c.getInt("id"),
                if (levels == null) listOf(answers.optInt("level")) else List(levels.length()) { levels.getInt(it) },
                answers.optString("note"), c.getString("created_at"),
            )
        }
    }

    /** Rule-based extraction of every document, for the debug screen. */
    suspend fun getCaseExtractions(caseId: Int): JSONObject = JSONObject(request("GET", "/cases/$caseId/extractions"))

    private suspend fun getOrNull(path: String): JSONObject? = try {
        JSONObject(request("GET", path))
    } catch (e: HttpError) {
        if (e.code == 404) null else throw e
    }

    /** An error response from the backend. message is safe to show. */
    class HttpError(val code: Int, message: String) : IOException(message)

    /** FastAPI puts the reason in {"detail": "..."}. */
    private fun detail(body: String): String =
        runCatching { JSONObject(body).getString("detail") }.getOrDefault(body.take(200))

    private suspend fun idToken(): String =
        auth.currentUser?.getIdToken(false)?.await()?.token ?: throw IOException("Not signed in")

    // ==================== NETWORKING INTERNALS ====================

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
        val token = idToken()
        val url = baseUrl()
        return withContext(Dispatchers.IO) {
            val conn = URL(url + path).openConnection() as HttpURLConnection
            try {
                conn.requestMethod = method
                conn.connectTimeout = 15_000
                conn.readTimeout = 60_000 // the coverage check waits for the AI
                conn.setRequestProperty("Authorization", "Bearer $token")
                if (body != null) {
                    conn.doOutput = true
                    conn.setRequestProperty("Content-Type", "application/json")
                    conn.outputStream.use { it.write(body.toString().toByteArray()) }
                }
                val code = conn.responseCode
                val text = (if (code in 200..299) conn.inputStream else conn.errorStream)
                    ?.bufferedReader()?.use { it.readText() }.orEmpty()
                if (code !in 200..299) throw HttpError(code, detail(text))
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
