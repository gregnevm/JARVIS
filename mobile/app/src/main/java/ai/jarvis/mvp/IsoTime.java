package ai.jarvis.mvp;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

/** ISO-8601 UTC мітка часу (серверний формат event_ts). */
public final class IsoTime {
    private IsoTime() {}

    public static String now() {
        return of(System.currentTimeMillis());
    }

    public static String of(long epochMillis) {
        SimpleDateFormat f = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US);
        f.setTimeZone(TimeZone.getTimeZone("UTC"));
        return f.format(new Date(epochMillis));
    }
}
