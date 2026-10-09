package com.powerbank.medsure.push

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.net.Uri
import android.util.Log
import androidx.core.app.NotificationCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.powerbank.medsure.MainActivity
import com.powerbank.medsure.R
import com.powerbank.medsure.net.Backend
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.launch

/** Pushes that arrive while the app is open, so screens can refresh. */
object PushBus {
    val events = MutableSharedFlow<Map<String, String>>(extraBufferCapacity = 8)
}

/**
 * Receives pushes from the backend and draws the notification.
 * data: title, body, case_id, kind, ref_id, and for a flagged check-in call_name + call_phone.
 * A push without a body is a silent update: it refreshes the app and shows nothing.
 */
class PushService : FirebaseMessagingService() {

    override fun onNewToken(token: String) {
        if (!Backend.signedIn) return
        CoroutineScope(Dispatchers.IO).launch {
            runCatching { Backend.registerDevice(token) }.onFailure { Log.w("MedSure", "Token refresh not saved", it) }
        }
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val data = message.data
        PushBus.events.tryEmit(data) // open screens refresh on every push, including silent ones
        val body = (data["body"] ?: message.notification?.body).orEmpty()
        if (body.isEmpty()) return // silent update: nothing to show

        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel(CHANNEL, "MedSure updates", NotificationManager.IMPORTANCE_HIGH))

        val flags = PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        val open = Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
        data.forEach { (key, value) -> open.putExtra(key, value) }

        val builder = NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(data["title"] ?: "MedSure")
            .setContentText(body)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)
            .setAutoCancel(true)
            .setContentIntent(PendingIntent.getActivity(this, 0, open, flags))

        val phone = data["call_phone"].orEmpty().filter { it.isDigit() }
        if (phone.isNotEmpty()) {
            val dial = Intent(Intent.ACTION_DIAL, Uri.parse("tel:+91$phone"))
            val who = data["call_name"].orEmpty().ifBlank { "now" }
            builder.addAction(0, "Call $who", PendingIntent.getActivity(this, 1, dial, flags))
        }
        manager.notify(message.messageId.hashCode(), builder.build())
    }

    private companion object {
        const val CHANNEL = "medsure"
    }
}
