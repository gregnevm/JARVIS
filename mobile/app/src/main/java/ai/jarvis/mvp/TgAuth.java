package ai.jarvis.mvp;

import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.text.TextUtils;

import org.json.JSONObject;

/**
 * Авторизація через Telegram (нативний логін):
 *   1) start → сервер віддає token + deeplink t.me/<bot>?start=tgauth_<token>
 *   2) відкриваємо Telegram (юзер тапає Start → бот прив'язує token до свого id)
 *   3) poll → коли підтверджено, сервер повертає JWT → зберігаємо access у Prefs.
 */
public final class TgAuth {
    private TgAuth() {}

    public interface Callback {
        void onResult(boolean ok, String message);
    }

    /** Крок 1: створити токен і відкрити Telegram. Повертає token або null. */
    public static String start(Context c) {
        String resp = IngestClient.post(c, "/api/v1/auth/telegram/start", new JSONObject());
        if (resp == null) return null;
        try {
            JSONObject o = new JSONObject(resp);
            String token = o.optString("token", "");
            String deeplink = o.optString("deeplink", "");
            if (TextUtils.isEmpty(token) || TextUtils.isEmpty(deeplink)) return null;
            Intent i = new Intent(Intent.ACTION_VIEW, Uri.parse(deeplink));
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            c.startActivity(i);
            return token;
        } catch (Exception e) {
            return null;
        }
    }

    /** Крок 3: poll до підтвердження (≈90с). true — отримали й зберегли JWT. */
    public static boolean poll(Context c, String token) {
        return poll(c, token, new java.util.concurrent.atomic.AtomicBoolean(false));
    }

    /** Те саме з можливістю скасування ззовні (кнопка «Скасувати» в UI). */
    public static boolean poll(Context c, String token, java.util.concurrent.atomic.AtomicBoolean cancelled) {
        if (TextUtils.isEmpty(token)) return false;
        for (int i = 0; i < 45 && !cancelled.get(); i++) {
            try {
                JSONObject body = new JSONObject();
                body.put("token", token);
                String resp = IngestClient.post(c, "/api/v1/auth/telegram/poll", body);
                if (resp != null) {
                    JSONObject o = new JSONObject(resp);
                    String status = o.optString("status", "");
                    if ("ok".equals(status)) {
                        String access = o.optString("access_token", "");
                        if (!TextUtils.isEmpty(access)) {
                            Prefs.get(c).edit().putString(Prefs.KEY_TOKEN, access).apply();
                            return true;
                        }
                    } else if ("expired".equals(status)) {
                        return false;
                    }
                }
                Thread.sleep(2000);
            } catch (InterruptedException ie) {
                return false;
            } catch (Exception e) {
                // мережевий збій на окремій ітерації — не валимо весь логін, чекаємо далі
                try { Thread.sleep(2000); } catch (InterruptedException ignored) { return false; }
            }
        }
        return false;
    }
}
