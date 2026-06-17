package ai.jarvis.mvp;

import android.content.Context;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.net.Uri;
import android.provider.CallLog;

import org.json.JSONObject;

/**
 * D3/D4: інкрементальний збір SMS (READ_SMS) і метаданих дзвінків (READ_CALL_LOG).
 * Курсор останнього часу — у Prefs; вміст редагується on-device у EventBuilder.
 * Без дозволу/toggle/на паузі — no-op (повертає 0).
 */
public final class SmsCallSync {
    private static final int MAX = 200;
    private SmsCallSync() {}

    private static boolean granted(Context c, String perm) {
        return c.checkSelfPermission(perm) == PackageManager.PERMISSION_GRANTED;
    }

    public static int syncSms(Context c, EventQueue q) {
        if (!Prefs.collect(c, Prefs.KEY_COLLECT_SMS) || Prefs.paused(c)) return 0;
        if (!granted(c, "android.permission.READ_SMS")) return 0;
        long last = Prefs.get(c).getLong(Prefs.KEY_SMS_LAST, 0L);
        long maxTs = last;
        int n = 0;
        Cursor cur = c.getContentResolver().query(
                Uri.parse("content://sms/inbox"),
                new String[]{"_id", "address", "body", "date"},
                "date > ?", new String[]{String.valueOf(last)}, "date ASC LIMIT " + MAX);
        if (cur == null) return 0;
        try {
            while (cur.moveToNext()) {
                long id = cur.getLong(0);
                String addr = cur.getString(1);
                String body = cur.getString(2);
                long date = cur.getLong(3);
                if (date > maxTs) maxTs = date;
                if (Prefs.isExcluded(c, addr, body)) continue; // E6
                JSONObject payload = new JSONObject();
                try {
                    payload.put("address", addr);
                    payload.put("body", body);
                } catch (Exception ignored) {}
                String summary = (addr == null ? "SMS" : addr) + ": " + (body == null ? "" : body);
                JSONObject ev = EventBuilder.build("sms", summary,
                        new String[]{"person:" + (addr == null ? "unknown" : addr)},
                        "sms", "personal", "sms:" + id, payload);
                if (ev != null) { q.enqueue(ev.toString()); n++; }
            }
        } finally {
            cur.close();
        }
        if (maxTs > last) Prefs.get(c).edit().putLong(Prefs.KEY_SMS_LAST, maxTs).apply();
        return n;
    }

    public static int syncCalls(Context c, EventQueue q) {
        if (!Prefs.collect(c, Prefs.KEY_COLLECT_CALLS) || Prefs.paused(c)) return 0;
        if (!granted(c, "android.permission.READ_CALL_LOG")) return 0;
        long last = Prefs.get(c).getLong(Prefs.KEY_CALLS_LAST, 0L);
        long maxTs = last;
        int n = 0;
        Cursor cur = c.getContentResolver().query(
                CallLog.Calls.CONTENT_URI,
                new String[]{CallLog.Calls._ID, CallLog.Calls.NUMBER, CallLog.Calls.CACHED_NAME,
                        CallLog.Calls.TYPE, CallLog.Calls.DATE, CallLog.Calls.DURATION},
                CallLog.Calls.DATE + " > ?", new String[]{String.valueOf(last)},
                CallLog.Calls.DATE + " ASC LIMIT " + MAX);
        if (cur == null) return 0;
        try {
            while (cur.moveToNext()) {
                long id = cur.getLong(0);
                String number = cur.getString(1);
                String name = cur.getString(2);
                int type = cur.getInt(3);
                long date = cur.getLong(4);
                long dur = cur.getLong(5);
                if (date > maxTs) maxTs = date;
                if (Prefs.isExcluded(c, number, name)) continue; // E6
                String who = (name != null && !name.isEmpty()) ? name : (number == null ? "невідомий" : number);
                String kindStr = type == CallLog.Calls.INCOMING_TYPE ? "вхідний"
                        : type == CallLog.Calls.OUTGOING_TYPE ? "вихідний"
                        : type == CallLog.Calls.MISSED_TYPE ? "пропущений" : "дзвінок";
                String summary = kindStr + " дзвінок: " + who + " (" + dur + "с)";
                JSONObject payload = new JSONObject();
                try {
                    payload.put("number", number);
                    payload.put("name", name);
                    payload.put("type", kindStr);
                    payload.put("duration_s", dur);
                } catch (Exception ignored) {}
                JSONObject ev = EventBuilder.build("call", summary,
                        new String[]{"person:" + who}, "calllog", "personal", "call:" + id, payload);
                if (ev != null) { q.enqueue(ev.toString()); n++; }
            }
        } finally {
            cur.close();
        }
        if (maxTs > last) Prefs.get(c).edit().putLong(Prefs.KEY_CALLS_LAST, maxTs).apply();
        return n;
    }
}
