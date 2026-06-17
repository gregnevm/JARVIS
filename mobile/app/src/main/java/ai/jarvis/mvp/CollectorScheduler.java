package ai.jarvis.mvp;

import android.app.job.JobInfo;
import android.app.job.JobScheduler;
import android.content.ComponentName;
import android.content.Context;

/** Планування upload-job (періодичний + миттєвий «Синхронізувати зараз»). */
public final class CollectorScheduler {
    private static final int PERIODIC_ID = 1001;
    private static final int ONESHOT_ID = 1002;
    private static final long PERIOD_MS = 30L * 60L * 1000L; // 30 хв

    private CollectorScheduler() {}

    private static JobScheduler js(Context c) {
        return (JobScheduler) c.getSystemService(Context.JOB_SCHEDULER_SERVICE);
    }

    private static ComponentName comp(Context c) {
        return new ComponentName(c, UploadJobService.class);
    }

    /** Періодичний upload, поки активний хоч один колектор; інакше скасовує. */
    public static void ensurePeriodic(Context c) {
        JobScheduler s = js(c);
        if (s == null) return;
        if (!Prefs.anyCollectorActive(c)) {
            s.cancel(PERIODIC_ID);
            return;
        }
        JobInfo job = new JobInfo.Builder(PERIODIC_ID, comp(c))
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setPeriodic(PERIOD_MS)
                .setPersisted(true)
                .build();
        s.schedule(job);
    }

    /** Негайний прогін (кнопка «Синхронізувати зараз»). */
    public static void runNow(Context c) {
        JobScheduler s = js(c);
        if (s == null) return;
        JobInfo job = new JobInfo.Builder(ONESHOT_ID, comp(c))
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setOverrideDeadline(1000)
                .build();
        s.schedule(job);
    }
}
