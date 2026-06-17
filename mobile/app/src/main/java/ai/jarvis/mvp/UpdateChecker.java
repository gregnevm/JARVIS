package ai.jarvis.mvp;

import android.content.Context;
import android.content.pm.PackageManager;

import org.json.JSONObject;

/**
 * A5: перевірка оновлень. GET /platform/api/apk/info → якщо version != поточної,
 * повертає нову версію (UI пропонує завантажити з /platform/apk). APK не в Play Store.
 */
public final class UpdateChecker {
    private UpdateChecker() {}

    /** Виконувати у фоні. Нова версія (рядок) або null, якщо актуально/недоступно. */
    public static String newerVersion(Context c) {
        String resp = IngestClient.get(c, "/platform/api/apk/info");
        if (resp == null) return null;
        try {
            JSONObject o = new JSONObject(resp);
            if (!o.optBoolean("available", false)) return null;
            String server = o.optString("version", "");
            String local = currentVersion(c);
            if (!server.isEmpty() && !server.equals(local)) return server;
        } catch (Exception ignored) {}
        return null;
    }

    public static String currentVersion(Context c) {
        try {
            return c.getPackageManager().getPackageInfo(c.getPackageName(), 0).versionName;
        } catch (PackageManager.NameNotFoundException e) {
            return "";
        }
    }
}
