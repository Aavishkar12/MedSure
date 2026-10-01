package com.powerbank.medsure.alerts

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.RingtoneManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.powerbank.medsure.MainActivity
import com.powerbank.medsure.R

private const val CH_RED = "red_alert"
private const val CH_AMBER = "amber_alert"

/** Receives the server's data messages and turns them into notifications. Works with the app closed. */
class AlertService : FirebaseMessagingService() {

    override fun onNewToken(token: String) {
        Session.saveFcmToken(this, token)
        if (Session.jwt(this) != null) Thread { runCatching { AlertApi.registerDevice(this, token) } }.start()
    }

    override fun onMessageReceived(msg: RemoteMessage) {
        val alertId = msg.data["alert_id"] ?: return
        val patient = msg.data["patient"] ?: "Your family member"
        createChannels(this)
        when (msg.data["type"]) {
            "red_alert" -> show(alertId, CH_RED, "Red alert: $patient",
                "$patient's check-in needs urgent attention. Tap to open.", red = true)
            "amber_alert" -> show(alertId, CH_AMBER, "Check-in flagged: $patient",
                "Their latest check-in needs a look today.", red = false)
            "alert_ack" -> NotificationManagerCompat.from(this).cancel(alertId.hashCode())   // someone else is on it
        }
    }

    private fun show(alertId: String, channel: String, title: String, text: String, red: Boolean) {
        val open = PendingIntent.getActivity(
            this, alertId.hashCode(),
            Intent(this, MainActivity::class.java).putExtra("alert_id", alertId).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val b = NotificationCompat.Builder(this, channel)
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentTitle(title).setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setContentIntent(open).setAutoCancel(!red)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
        if (red) {
            val ack = PendingIntent.getBroadcast(
                this, alertId.hashCode(),
                Intent(this, AckReceiver::class.java).putExtra("alert_id", alertId),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            )
            b.setPriority(NotificationCompat.PRIORITY_MAX).setCategory(NotificationCompat.CATEGORY_ALARM)
                .setOngoing(true)                                    // stays until someone acknowledges
                .setFullScreenIntent(open, true)                     // see note in README: Play restricts this
                .addAction(0, "I'm on it", ack)
        }
        runCatching { NotificationManagerCompat.from(this).notify(alertId.hashCode(), b.build()) }   // throws if permission denied
    }

    companion object {
        fun createChannels(c: Context) {
            val nm = c.getSystemService(NotificationManager::class.java)
            val alarm = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ALARM).build()
            nm.createNotificationChannel(NotificationChannel(CH_RED, "Red alerts", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Urgent alerts about a family member's recovery"
                enableVibration(true); vibrationPattern = longArrayOf(0, 600, 300, 600, 300, 600)
                setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM), alarm)
                setBypassDnd(true)          // only takes effect if the user grants Do Not Disturb access
                lockscreenVisibility = android.app.Notification.VISIBILITY_PUBLIC
            })
            nm.createNotificationChannel(NotificationChannel(CH_AMBER, "Check-in alerts", NotificationManager.IMPORTANCE_DEFAULT))
        }
    }
}

/** Handles the "I'm on it" button on the notification, even from the lock screen. */
class AckReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val alertId = intent.getStringExtra("alert_id") ?: return
        val pending = goAsync()
        Thread {
            try {
                AlertApi.acknowledge(context, alertId)
                NotificationManagerCompat.from(context).cancel(alertId.hashCode())
            } catch (_: Exception) {
                // keep the notification so the user can retry from inside the app
            } finally {
                pending.finish()
            }
        }.start()
    }
}
