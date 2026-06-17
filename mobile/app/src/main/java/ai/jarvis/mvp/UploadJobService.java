package ai.jarvis.mvp;

import android.app.job.JobParameters;
import android.app.job.JobService;

import org.json.JSONArray;

import java.util.ArrayList;
import java.util.List;

/**
 * D7: фоновий upload. Спершу інкрементально тягне SMS/дзвінки в чергу, далі
 * відправляє чергу батчами в /api/v1/ingest/events і видаляє доставлене.
 * JobService методи — на main thread, тож реальна робота в окремому потоці.
 */
public class UploadJobService extends JobService {
    private static final int BATCH = 50;
    private volatile boolean cancelled = false;

    @Override
    public boolean onStartJob(final JobParameters params) {
        final EventQueue q = new EventQueue(this);
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    if (Prefs.anyCollectorActive(UploadJobService.this)) {
                        SmsCallSync.syncSms(UploadJobService.this, q);
                        SmsCallSync.syncCalls(UploadJobService.this, q);
                    }
                    drain(q);
                } catch (Exception ignored) {
                } finally {
                    jobFinished(params, false);
                }
            }
        }, "jarvis-upload").start();
        return true; // робота триває асинхронно
    }

    private void drain(EventQueue q) {
        while (!cancelled) {
            List<EventQueue.Row> rows = q.peek(BATCH);
            if (rows.isEmpty()) break;
            JSONArray events = new JSONArray();
            List<Long> ids = new ArrayList<>();
            for (EventQueue.Row r : rows) {
                try {
                    events.put(new org.json.JSONObject(r.body));
                    ids.add(r.id);
                } catch (Exception e) {
                    ids.add(r.id); // битий рядок — викидаємо, щоб не застрягти
                }
            }
            if (events.length() == 0) { q.delete(ids); continue; }
            boolean ok = IngestClient.postEvents(this, events);
            if (!ok) break;            // сервер недоступний — лишаємо чергу на наступний тік
            q.delete(ids);             // доставлено — видаляємо
            if (rows.size() < BATCH) break;
        }
    }

    @Override
    public boolean onStopJob(JobParameters params) {
        cancelled = true;
        return true; // переплануй, якщо обірвали
    }
}
