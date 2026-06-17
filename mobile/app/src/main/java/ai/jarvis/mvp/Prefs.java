package ai.jarvis.mvp;

import android.content.Context;
import android.content.SharedPreferences;

/** Єдиний доступ до налаштувань клієнта (сервер, auth, per-source toggles, пауза). */
public final class Prefs {
    public static final String PREFS = "jarvis_prefs";
    public static final String KEY_URL = "server_url";
    public static final String KEY_USER = "auth_user";
    public static final String KEY_PASS = "auth_pass";
    public static final String KEY_TOKEN = "auth_token";       // JWT access (пріоритет над Basic)
    public static final String KEY_COLLECT_NOTIF = "collect_notifications";
    public static final String KEY_COLLECT_SMS = "collect_sms";
    public static final String KEY_COLLECT_CALLS = "collect_calls";
    public static final String KEY_PAUSED = "paused";          // пауза-паніка: стоп усього збору
    public static final String KEY_SMS_LAST = "sms_last_ts";    // інкрементальний курсор
    public static final String KEY_CALLS_LAST = "calls_last_ts";
    public static final String KEY_EXCLUDE = "exclude_terms";   // E6: per-contact/app exclude (CSV)
    public static final String KEY_NTFY_URL = "ntfy_url";       // push-клієнт (UnifiedPush)
    public static final String KEY_NTFY_TOPIC = "ntfy_topic";
    public static final String KEY_TP_ACK = "third_party_ack";  // E7: згода щодо третіх сторін
    public static final String KEY_PUSH_ON = "push_on";         // F1: приймати push (ntfy)

    private Prefs() {}

    public static SharedPreferences get(Context c) {
        return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    public static String url(Context c) {
        return get(c).getString(KEY_URL, "");
    }

    public static boolean paused(Context c) {
        return get(c).getBoolean(KEY_PAUSED, false);
    }

    public static boolean collect(Context c, String key) {
        return get(c).getBoolean(key, false); // default OFF (S2/приватність)
    }

    /** Чи увімкнено хоч одне джерело (і не на паузі) — чи варто планувати upload. */
    public static boolean anyCollectorActive(Context c) {
        if (paused(c)) return false;
        return collect(c, KEY_COLLECT_NOTIF) || collect(c, KEY_COLLECT_SMS)
                || collect(c, KEY_COLLECT_CALLS);
    }

    /** E6: чи містить рядок будь-який exclude-термін (нічого від цих людей/застосунків не збираємо). */
    public static boolean isExcluded(Context c, String... fields) {
        String raw = get(c).getString(KEY_EXCLUDE, "");
        if (raw == null || raw.trim().isEmpty()) return false;
        for (String term : raw.split(",")) {
            String t = term.trim().toLowerCase();
            if (t.isEmpty()) continue;
            for (String f : fields) {
                if (f != null && f.toLowerCase().contains(t)) return true;
            }
        }
        return false;
    }
}
