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

    suspend fun saveProfile(name: String, phone: String, email: String) {
        request("PATCH", "/me", JSONObject().put("name", name).put("phone", phone).put("email", email))
    }

    /** Registers this phone for push notifications. Call after sign-in and whenever the token changes. */
    suspend fun registerDevice(token: String? = null) {
        request("POST", "/devices", JSONObject().put("token", token ?: pushToken()))
    }

    /** Id of the first case this user belongs to, or null if they are not on one yet. */
    suspend fun firstCaseId(): Int? {
        val cases = JSONArray(request("GET", "/cases"))
        return if (cases.length() > 0) cases.getJSONObject(0).getInt("id") else null
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
    suspend fun checkin(caseId: Int, levels: List<Int>, note: String) {
        val answers = JSONObject().put("level", levels.maxOrNull() ?: 0).put("levels", JSONArray(levels)).put("note", note)
        request("POST", "/cases/$caseId/checkins", JSONObject().put("answers", answers))
    }

    /** Answer levels of the most recent check-in on this case, or null if there is none yet. */
    suspend fun latestCheckinLevels(caseId: Int): List<Int>? {
        val all = JSONArray(request("GET", "/cases/$caseId/checkins"))
        if (all.length() == 0) return null
        val levels = all.getJSONObject(all.length() - 1).getJSONObject("answers").optJSONArray("levels") ?: return null
        return List(levels.length()) { levels.getInt(it) }
    }

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
