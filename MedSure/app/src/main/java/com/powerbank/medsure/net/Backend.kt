package com.powerbank.medsure.net

import android.content.Context
import android.net.Uri
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.messaging.FirebaseMessaging
import com.powerbank.medsure.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
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

    // ==================== DOCUMENT & LLM API CALLS ====================

    /**
     * Upload a document via multipart/form-data.
     * Either context + uri OR ocrText must be provided.
     */
    suspend fun uploadDocument(
        caseId: Int,
        docType: String,
        context: Context? = null,
        uri: Uri? = null,
        filename: String? = null,
        ocrText: String? = null,
    ): JSONObject {
        val token = auth.currentUser?.getIdToken(false)?.await()?.token ?: throw IOException("Not signed in")
        val url = baseUrl() + "/cases/$caseId/documents"
        val boundary = "==MedSureBoundary" + System.currentTimeMillis() + "=="
        val lineEnd = "\r\n"

        return withContext(Dispatchers.IO) {
            val conn = URL(url).openConnection() as HttpURLConnection
            try {
                conn.requestMethod = "POST"
                conn.connectTimeout = 30_000
                conn.readTimeout = 60_000
                conn.doOutput = true
                conn.setRequestProperty("Authorization", "Bearer $token")
                conn.setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")

                DataOutputStream(conn.outputStream).use { dos ->
                    // Form field: doc_type
                    dos.writeBytes("--$boundary$lineEnd")
                    dos.writeBytes("Content-Disposition: form-data; name=\"doc_type\"$lineEnd$lineEnd")
                    dos.writeBytes(docType + lineEnd)

                    // Optional form field: ocr_text
                    if (!ocrText.isNullOrBlank()) {
                        dos.writeBytes("--$boundary$lineEnd")
                        dos.writeBytes("Content-Disposition: form-data; name=\"ocr_text\"$lineEnd$lineEnd")
                        dos.write(ocrText.toByteArray(Charsets.UTF_8))
                        dos.writeBytes(lineEnd)
                    }

                    // Optional file content
                    if (context != null && uri != null) {
                        val fn = filename ?: "document.pdf"
                        dos.writeBytes("--$boundary$lineEnd")
                        dos.writeBytes("Content-Disposition: form-data; name=\"file\"; filename=\"$fn\"$lineEnd")
                        dos.writeBytes("Content-Type: application/octet-stream$lineEnd$lineEnd")
                        context.contentResolver.openInputStream(uri)?.use { input ->
                            val buffer = ByteArray(8192)
                            var read: Int
                            while (input.read(buffer).also { read = it } != -1) {
                                dos.write(buffer, 0, read)
                            }
                        }
                        dos.writeBytes(lineEnd)
                    }

                    // End of multipart
                    dos.writeBytes("--$boundary--$lineEnd")
                    dos.flush()
                }

                val code = conn.responseCode
                val text = (if (code in 200..299) conn.inputStream else conn.errorStream)
                    ?.bufferedReader()?.use { it.readText() }.orEmpty()
                if (code !in 200..299) throw IOException("Upload failed ($code): ${text.take(200)}")
                JSONObject(text)
            } finally {
                conn.disconnect()
            }
        }
    }

    suspend fun getDocumentStatus(docId: Int): JSONObject {
        return JSONObject(request("GET", "/documents/$docId"))
    }

    suspend fun listDocuments(caseId: Int): JSONArray {
        return JSONArray(request("GET", "/cases/$caseId/documents"))
    }

    suspend fun getDischargeCard(caseId: Int): JSONObject? {
        return try {
            JSONObject(request("GET", "/cases/$caseId/discharge-card"))
        } catch (e: IOException) {
            if (e.message?.contains("404") == true) null else throw e
        }
    }

    suspend fun getBill(caseId: Int): JSONObject {
        return JSONObject(request("GET", "/cases/$caseId/bill"))
    }

    suspend fun askAboutDocuments(caseId: Int, question: String): JSONObject {
        val body = JSONObject().put("question", question)
        return JSONObject(request("POST", "/cases/$caseId/ask", body))
    }

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
        val token = runCatching { auth.currentUser?.getIdToken(false)?.await()?.token }.getOrNull()
        val url = baseUrl()
        return withContext(Dispatchers.IO) {
            val conn = URL(url + path).openConnection() as HttpURLConnection
            try {
                conn.requestMethod = method
                conn.connectTimeout = 15_000
                conn.readTimeout = 30_000
                if (!token.isNullOrBlank()) {
                    conn.setRequestProperty("Authorization", "Bearer $token")
                } else {
                    conn.setRequestProperty("X-User-Id", "android-dev-user")
                }
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

    /**
     * Uploads documents via multipart/form-data to POST /cases/{caseId}/documents.
     * Streams file bytes safely from Android Uri using ContentResolver.
     * Returns the generated job_id for background processing tracking.
     */
    suspend fun uploadDocuments(
        context: android.content.Context,
        caseId: Int,
        docs: List<com.powerbank.medsure.state.UploadedDoc>
    ): String {
        if (docs.isEmpty()) return ""
        val token = runCatching { auth.currentUser?.getIdToken(false)?.await()?.token }.getOrNull()
        val url = baseUrl()
        val boundary = "==MedSureBoundary" + System.currentTimeMillis() + "=="
        val lineEnd = "\r\n"
        val twoHyphens = "--"

        return withContext(Dispatchers.IO) {
            val conn = URL("$url/cases/$caseId/documents").openConnection() as HttpURLConnection
            try {
                conn.requestMethod = "POST"
                conn.connectTimeout = 20_000
                conn.readTimeout = 60_000
                conn.doOutput = true
                conn.doInput = true
                conn.useCaches = false
                conn.setRequestProperty("Connection", "Keep-Alive")
                conn.setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
                if (!token.isNullOrBlank()) {
                    conn.setRequestProperty("Authorization", "Bearer $token")
                } else {
                    conn.setRequestProperty("X-User-Id", "android-dev-user")
                }

                conn.outputStream.use { output ->
                    val writer = output.bufferedWriter(Charsets.UTF_8)
                    for (doc in docs) {
                        writer.write(twoHyphens + boundary + lineEnd)
                        writer.write("Content-Disposition: form-data; name=\"files\"; filename=\"${doc.name}\"$lineEnd")
                        writer.write("Content-Type: ${doc.mimeType.ifBlank { "application/octet-stream" }}$lineEnd")
                        writer.write(lineEnd)
                        writer.flush()

                        // Safely stream file bytes from Android ContentResolver
                        context.contentResolver.openInputStream(doc.uri)?.use { input ->
                            val buffer = ByteArray(16384)
                            var bytesRead: Int
                            while (input.read(buffer).also { bytesRead = it } != -1) {
                                output.write(buffer, 0, bytesRead)
                            }
                            output.flush()
                        }
                        writer.write(lineEnd)
                        writer.flush()
                    }
                    writer.write(twoHyphens + boundary + twoHyphens + lineEnd)
                    writer.flush()
                }

                val code = conn.responseCode
                val text = (if (code in 200..299) conn.inputStream else conn.errorStream)
                    ?.bufferedReader()?.use { it.readText() }.orEmpty()
                if (code !in 200..299) throw IOException("Upload failed ($code): ${text.take(200)}")

                val json = JSONObject(text)
                json.optString("job_id", "")
            } catch (e: java.net.SocketException) {
                base = null
                throw e
            } catch (e: java.net.SocketTimeoutException) {
                base = null
                throw e
            } finally {
                conn.disconnect()
            }
        }
    }

    suspend fun getJobStatus(jobId: String): JSONObject {
        val text = request("GET", "/jobs/$jobId")
        return JSONObject(text)
    }

    suspend fun getCaseExtractions(caseId: Int): JSONObject {
        val text = request("GET", "/cases/$caseId/extractions")
        return JSONObject(text)
    }

    suspend fun getDocumentExtraction(caseId: Int, docId: Int): JSONObject {
        val text = request("GET", "/cases/$caseId/extractions/$docId")
        return JSONObject(text)
    }
}
