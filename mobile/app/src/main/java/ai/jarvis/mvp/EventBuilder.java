package ai.jarvis.mvp;

import org.json.JSONArray;
import org.json.JSONObject;

/** Будує подію-паспорт (P9/P10) з on-device редакцією перед чергою. */
public final class EventBuilder {
    private EventBuilder() {}

    public static JSONObject build(String kind, String summary, String[] tags, String source,
                                   String sensitivity, String eventId, JSONObject payload) {
        try {
            JSONObject o = new JSONObject();
            o.put("kind", kind);
            o.put("summary", Redactor.redact(summary == null ? "" : summary));
            JSONArray t = new JSONArray();
            t.put("kind:" + kind);
            if (source != null) t.put("source:" + source);
            if (tags != null) for (String tag : tags) if (tag != null) t.put(tag);
            o.put("tags", t);
            o.put("source", source == null ? "android" : source);
            o.put("sensitivity", sensitivity == null ? "personal" : sensitivity);
            if (eventId != null) o.put("event_id", eventId);
            o.put("event_ts", IsoTime.now());
            o.put("payload", payload == null ? new JSONObject() : payload);
            return o;
        } catch (Exception e) {
            return null;
        }
    }
}
