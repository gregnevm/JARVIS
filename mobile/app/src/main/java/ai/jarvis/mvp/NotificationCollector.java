package ai.jarvis.mvp;

import android.app.Notification;
import android.os.Bundle;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;
import android.text.TextUtils;

import org.json.JSONObject;

/**
 * D2: NotificationListenerService — кожне посте сповіщення → подія-паспорт → черга.
 * Потребує grant у Settings (BIND_NOTIFICATION_LISTENER_SERVICE). За паузи/вимкненого
 * toggle нічого не збирає (S2/приватність).
 */
public class NotificationCollector extends NotificationListenerService {

    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        try {
            if (sbn == null) return;
            if (!Prefs.collect(this, Prefs.KEY_COLLECT_NOTIF) || Prefs.paused(this)) return;
            String pkg = sbn.getPackageName();
            if (pkg == null || pkg.equals(getPackageName())) return; // не збираємо власні

            Notification n = sbn.getNotification();
            if (n == null || n.extras == null) return;
            Bundle ex = n.extras;
            CharSequence titleCs = ex.getCharSequence(Notification.EXTRA_TITLE);
            CharSequence textCs = ex.getCharSequence(Notification.EXTRA_TEXT);
            String title = titleCs == null ? "" : titleCs.toString().trim();
            String text = textCs == null ? "" : textCs.toString().trim();
            if (TextUtils.isEmpty(title) && TextUtils.isEmpty(text)) return;
            if (Prefs.isExcluded(this, pkg, title, text)) return; // E6: per-contact/app exclude

            String summary = TextUtils.isEmpty(title) ? text : (title + ": " + text);
            JSONObject payload = new JSONObject();
            payload.put("app", pkg);
            payload.put("title", title);
            payload.put("text", text);

            String eventId = "notif:" + pkg + ":" + sbn.getPostTime();
            JSONObject ev = EventBuilder.build(
                    "notification", summary, new String[]{"app:" + pkg},
                    pkg, "personal", eventId, payload);
            if (ev != null) {
                new EventQueue(this).enqueue(ev.toString());
            }
        } catch (Exception ignored) {
            // лісенер не має падати на одній події
        }
    }

    @Override
    public void onNotificationRemoved(StatusBarNotification sbn) {
        // dismiss-сигнал — у 1.x (аналіз взаємодії). Поки no-op.
    }
}
