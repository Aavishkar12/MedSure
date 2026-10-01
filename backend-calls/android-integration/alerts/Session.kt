package com.powerbank.medsure.alerts

import android.content.Context

/** Tiny token store. Swap for EncryptedSharedPreferences before shipping. */
object Session {
    private fun prefs(c: Context) = c.getSharedPreferences("medsure_session", Context.MODE_PRIVATE)

    fun saveJwt(c: Context, jwt: String?) = prefs(c).edit().putString("jwt", jwt).apply()
    fun jwt(c: Context): String? = prefs(c).getString("jwt", null)

    fun saveFcmToken(c: Context, token: String) = prefs(c).edit().putString("fcm", token).apply()
    fun fcmToken(c: Context): String? = prefs(c).getString("fcm", null)
}
