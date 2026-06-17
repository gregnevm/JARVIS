package ai.jarvis.mvp;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.text.TextUtils;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/**
 * F1: UnifiedPush-клієнт через ntfy. Foreground-сервіс тримає JSON-стрім
 * {ntfy_url}/{topic}/json і показує локальні нотифікації (daily-дайджест, пропозиції).
 * Суверенно: ntfy може бути self-hosted (S1). Стартує, лише коли push увімкнено.
 */
public class NtfyService extends Service {
    private static final String CHANNEL = "jarvis_push";
    private static final int ONGOING_ID = 4242;
    private volatile boolean running = true;

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        ensureChannel();
        startForeground(ONGOING_ID, ongoing());
        new Thread(new Runnable() {
            public void run() { loop(); }
        }, "jarvis-ntfy").start();
        return START_STICKY;
    }

    private void loop() {
        long backoff = 2000;
        while (running) {
            String url = Prefs.get(this).getString(Prefs.KEY_NTFY_URL, "https://ntfy.sh");
            String topic = Prefs.get(this).getString(Prefs.KEY_NTFY_TOPIC, "");
            if (TextUtils.isEmpty(topic) || !Prefs.get(this).getBoolean(Prefs.KEY_PUSH_ON, false)) {
                break; // вимкнено — зупиняємось
            }
            HttpURLConnection conn = null;
            try {
                conn = (HttpURLConnection) new URL(url.replaceAll("/$", "") + "/" + topic + "/json").openConnection();
                conn.setConnectTimeout(10000);
                conn.setReadTimeout(0); // стрім — без read-таймауту
                BufferedReader r = new BufferedReader(new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8));
                backoff = 2000;
                String line;
                while (running && (line = r.readLine()) != null) {
                    handleLine(line);
                }
                r.close();
            } catch (Exception e) {
                try { Thread.sleep(backoff); } catch (InterruptedException ignored) {}
                backoff = Math.min(backoff * 2, 60000);
            } finally {
                if (conn != null) conn.disconnect();
            }
        }
        stopSelf();
    }

    private void handleLine(String line) {
        try {
            JSONObject o = new JSONObject(line);
            if (!"message".equals(o.optString("event"))) return; // open/keepalive ігноруємо
            String msg = o.optString("message", "");
            String title = o.optString("title", "JARVIS");
            if (!TextUtils.isEmpty(msg)) notifyUser(title, msg);
        } catch (Exception ignored) {}
    }

    private void ensureChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm != null && nm.getNotificationChannel(CHANNEL) == null) {
                nm.createNotificationChannel(new NotificationChannel(
                        CHANNEL, "JARVIS", NotificationManager.IMPORTANCE_DEFAULT));
            }
        }
    }

    @SuppressWarnings("deprecation")
    private Notification ongoing() {
        Notification.Builder b = (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                ? new Notification.Builder(this, CHANNEL) : new Notification.Builder(this);
        return b.setContentTitle("JARVIS").setContentText("Отримую сповіщення")
                .setSmallIcon(R.drawable.ic_launcher).setOngoing(true).build();
    }

    @SuppressWarnings("deprecation")
    private void notifyUser(String title, String text) {
        NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm == null) return;
        Notification.Builder b = (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                ? new Notification.Builder(this, CHANNEL) : new Notification.Builder(this);
        Notification n = b.setContentTitle(title).setContentText(text)
                .setSmallIcon(R.drawable.ic_launcher).setAutoCancel(true)
                .setStyle(new Notification.BigTextStyle().bigText(text)).build();
        nm.notify((int) (System.currentTimeMillis() % 100000), n);
    }

    @Override
    public void onDestroy() {
        running = false;
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    /** Старт/стоп залежно від налаштувань. */
    public static void apply(Context c) {
        boolean on = Prefs.get(c).getBoolean(Prefs.KEY_PUSH_ON, false)
                && !TextUtils.isEmpty(Prefs.get(c).getString(Prefs.KEY_NTFY_TOPIC, ""));
        Intent i = new Intent(c, NtfyService.class);
        if (on) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) c.startForegroundService(i);
            else c.startService(i);
        } else {
            c.stopService(i);
        }
    }
}
