package ai.jarvis.mvp;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

import java.util.ArrayList;
import java.util.List;

/**
 * Локальна черга подій (offline-first): подія-паспорт (JSON) лягає сюди, upload-job
 * відправляє батчами й видаляє доставлені. Чистий framework SQLite (без Room).
 */
public final class EventQueue extends SQLiteOpenHelper {
    private static final String DB = "jarvis_ctx.db";
    private static final int VER = 1;
    private static final String TABLE = "pending";

    public EventQueue(Context c) {
        super(c.getApplicationContext(), DB, null, VER);
    }

    @Override
    public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE " + TABLE + " (id INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT NOT NULL)");
    }

    @Override
    public void onUpgrade(SQLiteDatabase db, int oldV, int newV) {
        db.execSQL("DROP TABLE IF EXISTS " + TABLE);
        onCreate(db);
    }

    /** Кладе подію (JSON-рядок) у чергу. */
    public synchronized void enqueue(String body) {
        if (body == null || body.isEmpty()) return;
        ContentValues v = new ContentValues();
        v.put("body", body);
        getWritableDatabase().insert(TABLE, null, v);
    }

    public static final class Row {
        public final long id;
        public final String body;
        Row(long id, String body) { this.id = id; this.body = body; }
    }

    /** До `limit` найстаріших подій (FIFO). */
    public synchronized List<Row> peek(int limit) {
        List<Row> out = new ArrayList<>();
        Cursor cur = getReadableDatabase().query(
                TABLE, new String[]{"id", "body"}, null, null, null, null, "id ASC", String.valueOf(limit));
        try {
            while (cur.moveToNext()) {
                out.add(new Row(cur.getLong(0), cur.getString(1)));
            }
        } finally {
            cur.close();
        }
        return out;
    }

    public synchronized void delete(List<Long> ids) {
        if (ids == null || ids.isEmpty()) return;
        StringBuilder in = new StringBuilder();
        for (int i = 0; i < ids.size(); i++) {
            if (i > 0) in.append(',');
            in.append(ids.get(i).longValue());
        }
        getWritableDatabase().execSQL("DELETE FROM " + TABLE + " WHERE id IN (" + in + ")");
    }

    public synchronized int count() {
        Cursor cur = getReadableDatabase().rawQuery("SELECT count(*) FROM " + TABLE, null);
        try {
            return cur.moveToFirst() ? cur.getInt(0) : 0;
        } finally {
            cur.close();
        }
    }
}
