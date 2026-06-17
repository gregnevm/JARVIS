package ai.jarvis.mvp;

import android.content.Context;
import android.text.TextUtils;

import org.json.JSONObject;

/**
 * B2: обробка deeplink jarvis://pair?server=<url>&token=<t> (зі сканованого QR штабу).
 * Зберігає сервер, обмінює one-time токен на JWT через /api/v1/auth/pair, кладе access у Prefs.
 */
public final class Pairing {
    private Pairing() {}

    /** Виконувати у фоні (мережа). true — спарувалися й отримали JWT. */
    public static boolean redeem(Context c, String server, String token) {
        if (TextUtils.isEmpty(server) || TextUtils.isEmpty(token)) return false;
        // Сервер зберігаємо одразу — IngestClient.post бере base() з Prefs.
        Prefs.get(c).edit().putString(Prefs.KEY_URL, server).apply();
        try {
            JSONObject body = new JSONObject();
            body.put("token", token);
            String resp = IngestClient.post(c, "/api/v1/auth/pair", body);
            if (resp == null) return false;
            JSONObject o = new JSONObject(resp);
            String access = o.optString("access_token", "");
            if (TextUtils.isEmpty(access)) return false;
            Prefs.get(c).edit().putString(Prefs.KEY_TOKEN, access).apply();
            return true;
        } catch (Exception e) {
            return false;
        }
    }
}
