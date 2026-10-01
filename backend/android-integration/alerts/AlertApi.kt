package com.powerbank.medsure.alerts

import android.content.Context
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Minimal HTTP client (no extra libraries). Call these from a background thread or coroutine, never the main thread.
 * Emulator -> laptop:  http://10.0.2.2:8000     Real phone -> laptop:  http://<laptop-LAN-IP>:8000
 * Production must be https (and then remove usesCleartextTraffic from the manifest).
 */
object AlertApi {
    var BASE_URL = "http://10.0.2.2:8000"

    private fun call(c: Context, method: String, path: String, body: JSONObject? = null): String {
        val conn = (URL(BASE_URL + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 10_000; readTimeout = 15_000
            setRequestProperty("Content-Type", "application/json")
            Session.jwt(c)?.let { setRequestProperty("Authorization", "Bearer $it") }
            if (body != null) { doOutput = true; outputStream.use { it.write(body.toString().toByteArray()) } }
        }
        val stream = if (conn.responseCode in 200..299) conn.inputStream else conn.errorStream
        val text = stream?.bufferedReader()?.readText().orEmpty()
        if (conn.responseCode !in 200..299) throw RuntimeException("HTTP ${conn.responseCode}: $text")
        return text
    }

    /** Step 1 of login: the server texts one code and emails another. */
    fun requestOtp(c: Context, phone: String, email: String) =
        call(c, "POST", "/auth/request-otp", JSONObject().put("phone", phone).put("email", email))

    /** Step 2: send both codes. Saves the JWT and registers this phone for push. Returns role. */
    fun verify(c: Context, phone: String, email: String, otpPhone: String, otpEmail: String, role: String, name: String?, lang: String): String {
        val res = JSONObject(call(c, "POST", "/auth/verify", JSONObject()
            .put("phone", phone).put("email", email).put("otp_phone", otpPhone).put("otp_email", otpEmail)
            .put("role", role).put("name", name ?: JSONObject.NULL).put("language", lang)))
        Session.saveJwt(c, res.getString("token"))
        Session.fcmToken(c)?.let { registerDevice(c, it) }
        return res.getString("role")
    }

    fun registerDevice(c: Context, token: String) =
        call(c, "PUT", "/devices", JSONObject().put("fcm_token", token))

    /** Call on logout so a signed-out phone stops getting alerts. */
    fun unregisterDevice(c: Context) {
        Session.fcmToken(c)?.let { call(c, "DELETE", "/devices", JSONObject().put("fcm_token", it)) }
        Session.saveJwt(c, null)
    }

    /** answers use the server's words: breathing normal|harder|hard_resting, swelling none|same|more, medicine none|dizzy|rash|stomach */
    fun submitCheckin(c: Context, breathing: String, swelling: String, medicine: String, note: String?): JSONObject =
        JSONObject(call(c, "POST", "/checkins", JSONObject()
            .put("breathing", breathing).put("swelling", swelling).put("medicine", medicine)
            .put("note", note ?: JSONObject.NULL)))

    fun cancelAlert(c: Context, alertId: String) = call(c, "POST", "/alerts/$alertId/cancel")
    fun acknowledge(c: Context, alertId: String) = call(c, "POST", "/alerts/$alertId/ack")
    fun getAlert(c: Context, alertId: String): JSONObject = JSONObject(call(c, "GET", "/alerts/$alertId"))
    fun setAlertCalls(c: Context, on: Boolean) =
        call(c, "PATCH", "/me/settings", JSONObject().put("allow_alert_calls", on))
}
