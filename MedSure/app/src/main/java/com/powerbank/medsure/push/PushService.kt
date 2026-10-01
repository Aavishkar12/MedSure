package com.powerbank.medsure.push

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.util.Log
import androidx.core.app.NotificationCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.powerbank.medsure.MainActivity
import com.powerbank.medsure.R
import com.powerbank.medsure.net.Backend
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * Receives pushes from the backend. Android shows them itself while the app is in the background;
 * this draws them when the app is open. data carries case_id, kind and ref_id for deep linking.
 */
class PushService : FirebaseMessagingService() {

    override fun onNewToken(token: String) {
        if (!Backend.signedIn) return
        CoroutineScope(Dispatchers.IO).launch {
            runCatching { Backend.registerDevice(token) }.onFailure { Log.w("MedSure", "Token refresh not saved", it) }
        }
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val shown = message.notification ?: return
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel(CHANNEL, "MedSure updates", NotificationManager.IMPORTANCE_HIGH))

        val open = Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
        message.data.forEach { (key, value) -> open.putExtra(key, value) }
        val tap = PendingIntent.getActivity(this, 0, open, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)

        val notification = NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(shown.title ?: "MedSure")
            .setContentText(shown.body)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(tap)
            .build()
        manager.notify(message.messageId.hashCode(), notification)
    }

    private companion object {
        const val CHANNEL = "medsure"
    }
}
