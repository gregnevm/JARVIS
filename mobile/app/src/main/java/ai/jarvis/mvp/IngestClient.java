package ai.jarvis.mvp;

import android.content.Context;
import android.text.TextUtils;
import android.util.Base64;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/** HTTP до client-API JARVIS (/api/v1/*). Auth: Bearer JWT або Basic. */
public final class IngestClient {
    private IngestClient() {}

    private static String base(Context c) {
        return originOf(Prefs.url(c));
    }

    /** Origin сервера: відкидає суфікси /app|/platform і кінцевий слеш. */
    public static String originOf(String url) {
        if (url == null) return "";
        String u = url.trim();
        int i = u.indexOf("/app");
        if (i > 0) u = u.substring(0, i);
        int j = u.indexOf("/platform");
        if (j > 0) u = u.substring(0, j);
        if (u.endsWith("/")) u = u.substring(0, u.length() - 1);
        return u;
    }

    /**
     * Швидка перевірка, що сервер живий: GET &lt;origin&gt;/health з короткими
     * таймаутами. true — сервер відповів (будь-який 2xx-4xx; навіть 401 = живий).
     * Викликати у фоні. Прибирає «зберіг URL → білий екран» без зворотного звʼязку.
     */
    public static boolean reachable(String server) {
        String b = originOf(server);
        if (TextUtils.isEmpty(b)) return false;
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(b + "/health").openConnection();
            conn.setConnectTimeout(6000);
            conn.setReadTimeout(6000);
            conn.setRequestMethod("GET");
            int code = conn.getResponseCode();
            return code >= 200 && code < 500;
        } catch (Exception e) {
            return false;
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    private static String authHeader(Context c) {
        String token = Prefs.get(c).getString(Prefs.KEY_TOKEN, "");
        if (!TextUtils.isEmpty(token)) return "Bearer " + token;
        String user = Prefs.get(c).getString(Prefs.KEY_USER, "admin");
        String pass = Prefs.get(c).getString(Prefs.KEY_PASS, "");
        String raw = user + ":" + pass;
        return "Basic " + Base64.encodeToString(raw.getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP);
    }

    /** POST батч подій. true — 2xx. */
    public static boolean postEvents(Context c, JSONArray events) {
        try {
            JSONObject body = new JSONObject();
            body.put("events", events);
            return post(c, "/api/v1/ingest/events", body) != null;
        } catch (Exception e) {
            return false;
        }
    }

    /** GET → тіло відповіді (рядок) або null. */
    public static String get(Context c, String path) {
        String b = base(c);
        if (TextUtils.isEmpty(b)) return null;
        HttpURLConnection conn = null;
        try {
            URL u = new URL(b + path);
            conn = (HttpURLConnection) u.openConnection();
            conn.setConnectTimeout(10000);
            conn.setReadTimeout(20000);
            conn.setRequestMethod("GET");
            conn.setRequestProperty("Authorization", authHeader(c));
            int code = conn.getResponseCode();
            if (code < 200 || code >= 300) return null;
            return readAll(conn.getInputStream());
        } catch (Exception e) {
            return null;
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    /** Загальний POST JSON → тіло відповіді (рядок) або null при не-2xx/помилці. */
    public static String post(Context c, String path, JSONObject body) {
        String b = base(c);
        if (TextUtils.isEmpty(b)) return null;
        HttpURLConnection conn = null;
        try {
            URL u = new URL(b + path);
            conn = (HttpURLConnection) u.openConnection();
            conn.setConnectTimeout(10000);
            conn.setReadTimeout(60000);
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "application/json");
            conn.setRequestProperty("Authorization", authHeader(c));
            conn.setDoOutput(true);
            byte[] payload = (body == null ? "{}" : body.toString()).getBytes(StandardCharsets.UTF_8);
            OutputStream os = conn.getOutputStream();
            os.write(payload);
            os.close();
            int code = conn.getResponseCode();
            if (code < 200 || code >= 300) return null;
            return readAll(conn.getInputStream());
        } catch (Exception e) {
            return null;
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    /** POST сирих байтів (напр. аудіо) → тіло відповіді або null. */
    public static String postRaw(Context c, String path, byte[] data, String contentType) {
        String b = base(c);
        if (TextUtils.isEmpty(b)) return null;
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(b + path).openConnection();
            conn.setConnectTimeout(10000);
            conn.setReadTimeout(120000);
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", contentType);
            conn.setRequestProperty("Authorization", authHeader(c));
            conn.setDoOutput(true);
            OutputStream os = conn.getOutputStream();
            os.write(data);
            os.close();
            int code = conn.getResponseCode();
            if (code < 200 || code >= 300) return null;
            return readAll(conn.getInputStream());
        } catch (Exception e) {
            return null;
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    private static String readAll(InputStream in) throws Exception {
        // try-with-resources: потік закривається навіть якщо readLine кине виняток.
        try (BufferedReader r = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = r.readLine()) != null) sb.append(line);
            return sb.toString();
        }
    }
}
