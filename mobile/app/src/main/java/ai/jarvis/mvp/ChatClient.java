package ai.jarvis.mvp;

import android.content.Context;

import org.json.JSONObject;

/** Один хід чату → /api/v1/chat → текст відповіді (або повідомлення про помилку). */
public final class ChatClient {
    private ChatClient() {}

    public static String send(Context c, String text) {
        try {
            JSONObject body = new JSONObject();
            body.put("text", text);
            body.put("mode", "auto");
            String resp = IngestClient.post(c, "/api/v1/chat", body);
            if (resp == null) return "⚠️ Сервер недоступний або не авторизовано.";
            JSONObject o = new JSONObject(resp);
            String reply = o.optString("reply", "");
            return reply.isEmpty() ? "—" : reply;
        } catch (Exception e) {
            return "⚠️ Помилка: " + e.getMessage();
        }
    }
}
